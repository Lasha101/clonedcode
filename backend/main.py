import os
import pandas as pd
from contextlib import asynccontextmanager
from pydantic import ValidationError
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query, Form, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import io
from datetime import datetime, timezone
import crud, models, schemas, auth
from database import SessionLocal, engine, get_db
from typing import Optional, List, Dict, Any
import ocr_service
import logging # Added for better logging
import uuid # <-- NEW: For Job IDs

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Initialize the rate limiter
limiter = Limiter(key_func=get_remote_address)

# --- NEW: In-Memory Job Database ---
# This will store all OCR jobs. For real persistence, replace this
# with a new table in your SQL database.
OCR_JOBS: Dict[str, Dict[str, Any]] = {}


# --- NEW: Background Task Function ---
async def run_ocr_extraction_task(
    job_id: str,
    file_content: bytes,
    content_type: str,
    destination: Optional[str],
    user_id: int,
    db: Session # We need to pass a session here
):
    """
    This function runs in the background.
    It performs the full OCR extraction and DB write.
    """
    global OCR_JOBS
    job = OCR_JOBS.get(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in task runner.")
        db.close() # Close session
        return

    try:
        # 1. Call the OCR service (long-running step)
        extraction_results = await ocr_service.extract_data_page_by_page(
            file_content=file_content,
            content_type=content_type
        )
    except Exception as e:
        logger.error(f"Error during page-by-page extraction for job {job_id}: {e}", exc_info=True)
        job["status"] = "failed"
        job["finished_at"] = datetime.now()
        job["failures"] = [{"page_number": 1, "detail": f"Traitement global du document échoué: {str(e)}"}]
        db.close() # Close session on failure too
        return

    successes = []
    failures = []
    
    # 2. Process results and save to DB
    for result in extraction_results:
        page_number = result.get("page_number")

        if "error" in result:
            failures.append({"page_number": page_number, "detail": result["error"]})
            continue

        if "data" in result:
            passport_data = result["data"]
            try:
                if destination:
                    passport_data["destination"] = destination
                
                # We validate the data using the schema
                passport_create_schema = schemas.PassportCreate(**passport_data)
                
                # We save the validated data to the DB
                # IMPORTANT: We use the `db` session passed into this task
                created_passport_model = crud.create_user_passport(
                    db=db, passport=passport_create_schema, user_id=user_id
                )
                
                # --- FIX from last time ---
                # Convert the live SQLAlchemy model to a Pydantic schema *while the session is active*.
                created_passport_schema = schemas.Passport.model_validate(created_passport_model)
                
                # Add the *Pydantic schema* (which is just data) to the success list.
                successes.append({"page_number": page_number, "data": created_passport_schema})
                # --- END OF FIX ---

            except ValidationError as e:
                first_error = e.errors()[0]
                error_message = f"Validation Error on field '{first_error['loc'][0]}': {first_error['msg']}"
                failures.append({"page_number": page_number, "detail": error_message})
            except HTTPException as e:
                # Catch duplicate errors from crud
                failures.append({"page_number": page_number, "detail": e.detail})
            except Exception as e:
                detail = getattr(e, 'detail', f"A database error occurred: {str(e)}")
                failures.append({"page_number": page_number, "detail": detail})
    
    # --- NEW: Increment User's Page Count ---
    # We do this after processing all pages, based on the *total number of pages returned by the OCR service*.
    page_count = len(extraction_results)
    if page_count > 0:
        try:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                if user.uploaded_pages_count is None: # Handle null values just in case
                    user.uploaded_pages_count = 0
                user.uploaded_pages_count += page_count
                db.commit()
                logger.info(f"Incremented page count for user {user_id} by {page_count}. New total: {user.uploaded_pages_count}")
            else:
                logger.warning(f"Could not find user {user_id} to increment page count.")
        except Exception as e:
            logger.error(f"Failed to increment page count for user {user_id}: {e}", exc_info=True)
            db.rollback() # Rollback this specific error, but let the task complete
    # --- END OF NEW LOGIC ---

    # 3. Update the job in our in-memory DB
    job["status"] = "complete"
    job["finished_at"] = datetime.now()
    job["successes"] = successes
    job["failures"] = failures
    
    logger.info(f"Job {job_id} completed. {len(successes)} successes, {len(failures)} failures.")
    
    # 4. Close the database session
    db.close()


# --- Lifespan for application startup/shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    # Create a default admin user on startup if one doesn't exist
    admin_user = crud.get_user_by_username(db, username="admin")
    if not admin_user:
        ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
        if not ADMIN_PASSWORD:
            print("WARNING: ADMIN_PASSWORD environment variable not set. Admin user not created.")
        else:
            admin = schemas.UserCreate(
                first_name="Admin",
                last_name="User",
                email="admin@example.com",
                phone_number="1234567890",
                user_name="admin",
                password=ADMIN_PASSWORD
            )
            crud.create_user(db=db, user=admin, role="admin", token=None)
    db.close()
    yield
    # Code to run on shutdown can go here

# --- FastAPI App Initialization ---
app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS Middleware Configuration ---
origins = ["*"] # Allow all origins for simplicity
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# --- Authentication Routes ---
@app.post("/token", response_model=schemas.Token)
@limiter.limit("5/minute")
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.user_name})
    return {"access_token": access_token, "token_type": "bearer"}

# --- User Routes ---
@app.post("/users/", response_model=schemas.User)
def register_user(user: schemas.UserCreate, token: str = Query(...), db: Session = Depends(get_db)):
    invitation = crud.get_invitation_by_token(db, token)
    if not invitation or invitation.is_used or invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Jeton d'inscription invalide ou expiré.")
    if invitation.email != user.email:
        raise HTTPException(status_code=400, detail="L'email d'inscription ne correspond pas à l'email de l'invitation.")
    db_user_by_email = crud.get_user_by_email(db, email=user.email)
    if db_user_by_email:
        raise HTTPException(status_code=400, detail="Email déjà enregistré")
    db_user_by_username = crud.get_user_by_username(db, username=user.user_name)
    if db_user_by_username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur déjà enregistré")
    created_user = crud.create_user(db=db, user=user, role="user")
    db.delete(invitation)
    db.commit()
    return created_user

@app.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    return current_user

@app.put("/users/me", response_model=schemas.User)
def update_user_me(user_update: schemas.UserUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    # User cannot update their own page count
    if user_update.uploaded_pages_count is not None:
        user_update.uploaded_pages_count = None
    return crud.update_user(db=db, user_id=current_user.id, user_update=user_update)

# --- Admin User Management Routes ---
@app.get("/admin/users/", response_model=list[schemas.User], dependencies=[Depends(auth.require_admin)])
def read_users(skip: int = 0, limit: int = 100, name_filter: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return crud.get_users(db, skip=skip, limit=limit, name_filter=name_filter)

@app.delete("/admin/users/{user_id}", response_model=schemas.User, dependencies=[Depends(auth.require_admin)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.delete_user(db=db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return db_user

@app.get("/admin/users/{user_id}", response_model=schemas.User, dependencies=[Depends(auth.require_admin)])
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return db_user

@app.put("/admin/users/{user_id}", response_model=schemas.User, dependencies=[Depends(auth.require_admin)])
def update_user_admin(user_id: int, user_update: schemas.UserUpdate, db: Session = Depends(get_db)):
    # Admin can update page count
    db_user = crud.update_user(db=db, user_id=user_id, user_update=user_update)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return db_user

@app.post("/admin/users/", response_model=schemas.User, dependencies=[Depends(auth.require_admin)])
def create_user_by_admin(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user_by_email = crud.get_user_by_email(db, email=user.email)
    if db_user_by_email:
        raise HTTPException(status_code=400, detail="Email déjà enregistré")
    db_user_by_username = crud.get_user_by_username(db, username=user.user_name)
    if db_user_by_username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur déjà enregistré")
    return crud.create_user(db=db, user=user, role=user.role if hasattr(user, 'role') else 'user')

# --- Passport Routes ---
@app.post("/passports/", response_model=schemas.Passport)
def create_passport(passport: schemas.PassportCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    return crud.create_user_passport(db=db, passport=passport, user_id=current_user.id)

# --- OCR UPLOAD AND EXTRACTION ROUTE (MODIFIED) ---
@app.post("/passports/upload-and-extract/", response_model=schemas.OcrJob)
async def upload_and_extract_passport(
    background_tasks: BackgroundTasks, # <-- NEW
    destination: Optional[str] = Form(None),
    file: UploadFile = File(...),
    # db: Session = Depends(get_db), <-- We get a new session for the task
    current_user: models.User = Depends(auth.get_current_active_user)
):
    global OCR_JOBS
    
    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    # 1. Create a new Job ID
    job_id = str(uuid.uuid4())
    
    # 2. Create the job object
    job = {
        "id": job_id,
        "user_id": current_user.id,
        "file_name": file.filename,
        "status": "processing", # Start as "processing"
        "created_at": datetime.now(),
        "finished_at": None,
        "successes": [],
        "failures": [],
    }
    
    # 3. Save job to our in-memory DB
    OCR_JOBS[job_id] = job

    # 4. Create a new DB session for the background task
    db_task = SessionLocal()

    # 5. Add the *real* work to a background task
    background_tasks.add_task(
        run_ocr_extraction_task,
        job_id=job_id,
        file_content=file_content,
        content_type=file.content_type,
        destination=destination,
        user_id=current_user.id,
        db=db_task # Pass the new session
    )
    
    # 6. Return the job object to the frontend IMMEDIATELY
    return job


# --- NEW OCR JOB ROUTES ---

@app.get("/ocr/jobs/", response_model=List[schemas.OcrJob])
async def get_ocr_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Get all OCR jobs for the current user.
    """
    global OCR_JOBS
    # Filter in-memory dict for jobs belonging to the current user
    user_jobs = [
        job for job in OCR_JOBS.values() if job["user_id"] == current_user.id
    ]
    # Sort by creation date, newest first
    user_jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return user_jobs

@app.get("/ocr/jobs/{job_id}", response_model=schemas.OcrJob)
async def get_ocr_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Get the status of a single OCR job.
    """
    global OCR_JOBS
    job = OCR_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job.")
    return job

# --- THIS IS THE NEW DELETE ROUTE ---
@app.delete("/ocr/jobs/{job_id}", response_model=schemas.OcrJob)
async def delete_ocr_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Deletes a job notification from the in-memory store.
    """
    global OCR_JOBS
    job = OCR_JOBS.get(job_id)
    
    # Check if job exists
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    # Check if the user is authorized to delete this job
    if job["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this job.")
    
    # Pop the job from the dictionary
    deleted_job = OCR_JOBS.pop(job_id, None)
    
    if deleted_job is None:
        # This might happen in a race condition, though unlikely
        raise HTTPException(status_code=404, detail="Job not found during deletion.")
        
    return deleted_job
# --- END OF NEW DELETE ROUTE ---


@app.get("/export/data")
def export_data(
    destination: Optional[str] = None, user_id: Optional[int] = None,
    first_name: Optional[str] = None, last_name: Optional[str] = None,
    db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)
):
    effective_user_id = current_user.id
    if current_user.role == "admin":
        effective_user_id = user_id
    
    filtered_data = crud.filter_data(db, destination, effective_user_id, first_name, last_name)
    if not filtered_data:
        raise HTTPException(status_code=404, detail="Aucune donnée de passeport trouvée pour les critères donnés")
    
    df = pd.DataFrame(filtered_data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    
    filename_parts = ["passeports"]
    if destination: filename_parts.append(destination.replace(' ', '_').lower())

    if current_user.role == 'admin':
        if user_id:
            filtered_user = crud.get_user(db, user_id)
            if filtered_user: filename_parts.append(f"pour_{filtered_user.user_name.lower()}")
            else: filename_parts.append(f"pour_utilisateur_{user_id}")
        else:
            filename_parts.append("rapport_complet")
    else:
        filename_parts.append(f"pour_{current_user.user_name.lower()}")

    filename = f"{'_'.join(filename_parts)}.csv"
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

@app.get("/passports/", response_model=list[schemas.Passport])
def read_passports(
    db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user),
    user_filter: Optional[str] = None, voyage_filter: Optional[str] = None
):
    if current_user.role == "admin":
        return crud.get_passports(db=db, user_filter=user_filter, voyage_filter=voyage_filter)
    return crud.get_passports_by_user(db=db, user_id=current_user.id)

@app.put("/passports/{passport_id}", response_model=schemas.Passport)
def update_passport(passport_id: int, passport_update: schemas.PassportCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    db_passport = crud.get_passport(db, passport_id=passport_id)
    if db_passport is None:
        raise HTTPException(status_code=404, detail="Passeport non trouvé")
    if current_user.role != "admin" and db_passport.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé à mettre à jour ce passeport")
    return crud.update_passport(db=db, passport_id=passport_id, passport_update=passport_update)

@app.delete("/passports/{passport_id}", response_model=schemas.Passport)
def delete_passport(passport_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    db_passport = crud.get_passport(db, passport_id=passport_id)
    if db_passport is None:
        raise HTTPException(status_code=404, detail="Passeport non trouvé")
    if current_user.role != "admin" and db_passport.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé à supprimer ce passeport")
    return crud.delete_passport(db=db, passport_id=passport_id)

# --- NEW: MULTI-DELETE ENDPOINT ---
@app.post("/passports/delete-multiple", response_model=dict)
def delete_multiple_passports(
    payload: schemas.PassportDeleteMultiple,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not payload.passport_ids:
        return {"deleted_count": 0}
    
    deleted_count = crud.delete_multiple_passports(
        db=db,
        passport_ids=payload.passport_ids,
        user_id=current_user.id,
        role=current_user.role
    )
    return {"deleted_count": deleted_count}
# --- END OF NEW MULTI-DELETE ENDPOINT ---


# --- Voyage and Destination Routes ---
@app.post("/voyages/", response_model=schemas.Voyage)
def create_voyage(voyage: schemas.VoyageCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    return crud.create_user_voyage(db=db, voyage=voyage, user_id=current_user.id, passport_ids=voyage.passport_ids)

@app.get("/voyages/", response_model=list[schemas.Voyage])
def read_voyages(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user), user_filter: Optional[str] = None):
    if current_user.role == "admin":
        return crud.get_voyages(db=db, user_filter=user_filter)
    return crud.get_voyages_by_user(db=db, user_id=current_user.id)

@app.put("/voyages/{voyage_id}", response_model=schemas.Voyage)
def update_voyage(voyage_id: int, voyage_update: schemas.VoyageCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    db_voyage = crud.get_voyage(db, voyage_id=voyage_id)
    if db_voyage is None:
        raise HTTPException(status_code=404, detail="Voyage non trouvé")
    if current_user.role != "admin" and db_voyage.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé à mettre à jour ce voyage")
    return crud.update_voyage(db=db, voyage_id=voyage_id, voyage_update=voyage_update)

@app.delete("/voyages/{voyage_id}", response_model=schemas.Voyage)
def delete_voyage(voyage_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    db_voyage = crud.get_voyage(db, voyage_id=voyage_id)
    if db_voyage is None:
        raise HTTPException(status_code=404, detail="Voyage non trouvé")
    if current_user.role != "admin" and db_voyage.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé à supprimer ce voyage")
    return crud.delete_voyage(db=db, voyage_id=voyage_id)

@app.get("/destinations/", response_model=List[str])
def get_unique_destinations(user_id: Optional[int] = Query(None), db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    target_user_id = current_user.id
    if current_user.role == "admin":
        target_user_id = user_id
    return crud.get_destinations_by_user_id(db, user_id=target_user_id)

# --- Invitation Routes ---
@app.get("/invitations/{token}", response_model=schemas.Invitation)
def get_invitation(token: str, db: Session = Depends(get_db)):
    invitation = crud.get_invitation_by_token(db, token)
    if not invitation or invitation.is_used or invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=404, detail="Invitation non trouvée ou invalide.")
    return invitation

@app.post("/admin/invitations", response_model=schemas.Invitation, dependencies=[Depends(auth.require_admin)])
def create_invitation(invitation: schemas.InvitationCreate, db: Session = Depends(get_db)):
    existing_user = crud.get_user_by_email(db, email=invitation.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Un utilisateur avec cet email existe déjà.")
    existing_invitation = crud.get_invitation_by_email(db, email=invitation.email)
    if existing_invitation and not existing_invitation.is_used and not (existing_invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)):
        raise HTTPException(status_code=400, detail="Une invitation active pour cet email existe déjà.")
    return crud.create_invitation(db=db, email=invitation.email)

@app.get("/admin/invitations/", response_model=list[schemas.Invitation], dependencies=[Depends(auth.require_admin)])
def read_invitations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_invitations(db, skip=skip, limit=limit)

@app.put("/admin/invitations/{invitation_id}", response_model=schemas.Invitation, dependencies=[Depends(auth.require_admin)])
def update_invitation(invitation_id: int, invitation_update: schemas.InvitationUpdate, db: Session = Depends(get_db)):
    db_invitation = crud.update_invitation(db=db, invitation_id=invitation_id, invitation_update=invitation_update)
    if db_invitation is None:
        raise HTTPException(status_code=404, detail="Invitation non trouvée")
    return db_invitation

@app.delete("/admin/invitations/{invitation_id}", response_model=schemas.Invitation, dependencies=[Depends(auth.require_admin)])
def delete_invitation(invitation_id: int, db: Session = Depends(get_db)):
    db_invitation = crud.delete_invitation(db=db, invitation_id=invitation_id)
    if db_invitation is None:
        raise HTTPException(status_code=404, detail="Invitation non trouvée")
    return db_invitation

@app.get("/admin/filterable-users", response_model=list[schemas.User], dependencies=[Depends(auth.require_admin)])
def read_filterable_users(db: Session = Depends(get_db)):
    return crud.get_all_users_for_filtering(db)