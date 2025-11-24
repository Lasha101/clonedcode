# --------------- START OF FILE: main.py ---------------

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
import logging
import uuid
import json 

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables (including the new ocr_jobs table)
models.Base.metadata.create_all(bind=engine)

# Initialize the rate limiter
limiter = Limiter(key_func=get_remote_address)

# --- Background Task Function ---
async def run_ocr_extraction_task(
    job_id: str,
    file_content: bytes,
    content_type: str,
    destination: Optional[str],
    user_id: int
):
    """
    Background task that writes DIRECTLY to the DB table 'ocr_jobs'.
    This solves the Gunicorn/Worker memory isolation issue.
    """
    # Create a new independent database session for this thread
    db = SessionLocal()
    
    try:
        # Retrieve the job created in the API endpoint
        job = db.query(models.OcrJob).filter(models.OcrJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in DB task runner.")
            return

        # STEP 1: Uploading/Pre-processing (10%)
        job.progress = 10 
        db.commit() 
        
        # Call the OCR service (Heavy lifting)
        try:
            extraction_results = await ocr_service.extract_data_page_by_page(
                file_content=file_content,
                content_type=content_type
            )
        except Exception as e:
            logger.error(f"OCR Service failed for job {job_id}: {e}")
            job.status = "failed"
            job.progress = 0
            job.finished_at = datetime.now()
            job.failures = [{"page_number": 0, "detail": f"Traitement global échoué: {str(e)}"}]
            db.commit()
            return
        
        # STEP 2: OCR Done, Starting Database Writes (75%)
        job.progress = 75 
        db.commit()

        successes_list = []
        failures_list = []
        
        # STEP 3: Process results and save passports to DB
        total_items = len(extraction_results)
        
        for index, result in enumerate(extraction_results):
            page_number = result.get("page_number")

            if "error" in result:
                failures_list.append({"page_number": page_number, "detail": result["error"]})
            elif "data" in result:
                passport_data = result["data"]
                try:
                    if destination:
                        passport_data["destination"] = destination
                    
                    # Validate
                    passport_create_schema = schemas.PassportCreate(**passport_data)
                    
                    # Create Passport in DB
                    created_passport_model = crud.create_user_passport(
                        db=db, passport=passport_create_schema, user_id=user_id
                    )
                    
                    # Convert to Schema to store in the JSON log
                    created_passport_schema = schemas.Passport.model_validate(created_passport_model)
                    
                    # Append as dict for JSON column
                    successes_list.append({"page_number": page_number, "data": created_passport_schema.model_dump()})

                except ValidationError as e:
                    first_error = e.errors()[0]
                    failures_list.append({"page_number": page_number, "detail": f"Validation: {first_error['msg']}"})
                except HTTPException as e:
                    failures_list.append({"page_number": page_number, "detail": e.detail})
                except Exception as e:
                    detail = getattr(e, 'detail', f"Database Error: {str(e)}")
                    failures_list.append({"page_number": page_number, "detail": detail})
            
            # Update progress incrementally (75% -> 95%)
            if total_items > 0:
                current_progress = 75 + int((index + 1) / total_items * 20)
                # Only commit if progress changed significantly to reduce DB load
                if current_progress > job.progress:
                    job.progress = current_progress
                    db.commit()

        # STEP 4: Update User Stats
        page_count = len(extraction_results)
        if page_count > 0:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                user.uploaded_pages_count += page_count
                # db.commit() called at end

        # STEP 5: Completion (100%)
        job.status = "complete"
        job.progress = 100
        job.finished_at = datetime.now()
        
        # Re-assign lists to ensure SQLAlchemy detects changes in JSON column
        job.successes = successes_list
        job.failures = failures_list
        
        db.commit()
        logger.info(f"Job {job_id} completed successfully.")

    except Exception as e:
        logger.error(f"CRITICAL SYSTEM ERROR Job {job_id}: {e}", exc_info=True)
        try:
            job.status = "failed"
            job.failures = [{"page_number": 0, "detail": f"System error: {str(e)}"}]
            db.commit()
        except:
            pass
    finally:
        db.close()


# --- Lifespan for application startup/shutdown ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    admin_user = crud.get_user_by_username(db, username="admin")
    if not admin_user:
        ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
        if ADMIN_PASSWORD:
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

# --- FastAPI App Initialization ---
app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS Middleware Configuration ---
origins = ["*"]
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

# --- OCR UPLOAD AND EXTRACTION ROUTE ---
@app.post("/passports/upload-and-extract/", response_model=schemas.OcrJob)
async def upload_and_extract_passport(
    background_tasks: BackgroundTasks,
    destination: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db), # Injected to create the initial Job record
    current_user: models.User = Depends(auth.get_current_active_user)
):
    
    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    job_id = str(uuid.uuid4())
    
    # Create Job record in the database immediately
    new_job = models.OcrJob(
        id=job_id,
        user_id=current_user.id,
        file_name=file.filename,
        status="processing",
        progress=0,
        successes=[],
        failures=[]
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Pass the job_id to the background task
    background_tasks.add_task(
        run_ocr_extraction_task,
        job_id=job_id,
        file_content=file_content,
        content_type=file.content_type,
        destination=destination,
        user_id=current_user.id
    )
    
    return new_job

# --- OCR JOB ROUTES (DB Driven) ---

@app.get("/ocr/jobs/", response_model=List[schemas.OcrJob])
async def get_ocr_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    # Query database for persistence across workers/restarts
    jobs = db.query(models.OcrJob).filter(
        models.OcrJob.user_id == current_user.id
    ).order_by(models.OcrJob.created_at.desc()).all()
    return jobs

@app.get("/ocr/jobs/{job_id}", response_model=schemas.OcrJob)
async def get_ocr_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    job = db.query(models.OcrJob).filter(models.OcrJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized.")
    return job

@app.delete("/ocr/jobs/{job_id}", response_model=schemas.OcrJob)
async def delete_ocr_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    job = db.query(models.OcrJob).filter(models.OcrJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized.")
    
    db.delete(job)
    db.commit()
    return job

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
    user_filter: Optional[str] = Query(None), 
    voyage_filter: Optional[str] = Query(None),
    destination_filter: Optional[str] = Query(None)
):
    if current_user.role == "admin":
        return crud.get_passports(db=db, user_filter=user_filter, voyage_filter=voyage_filter)
    
    return crud.get_passports_by_user(
        db=db, user_id=current_user.id, destination=destination_filter
    )

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

# --------------- END OF FILE: main.py ---------------