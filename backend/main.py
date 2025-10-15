import os
import pandas as pd
from contextlib import asynccontextmanager
import tempfile
from fastapi import BackgroundTasks
from pydantic import ValidationError
# --> IMPORT Request
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query, Form, Request 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import io
from datetime import datetime, timezone
import crud, models, schemas, auth
from database import SessionLocal, engine, get_db
from typing import Optional, List
import ocr_service # Import the new service

# --> IMPORT everything needed from slowapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from dotenv import load_dotenv # You'll need to install this library


# Load environment variables from a .env file (for local development)
load_dotenv()

# Create all database tables
models.Base.metadata.create_all(bind=engine)

# --> INITIALIZE the limiter to identify users by their IP address
limiter = Limiter(key_func=get_remote_address)

# --- Lifespan Context Manager (Modern way for startup/shutdown events) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    db = SessionLocal()
    # Check if admin user exists and create one if not
    admin_user = crud.get_user_by_username(db, username="admin")
    if not admin_user:
        # Get the admin password from an environment variable
        ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
        if not ADMIN_PASSWORD:
            # Handle the case where the password isn't set, maybe log a warning
            print("WARNING: ADMIN_PASSWORD environment variable not set. Admin user not created.")
        else:
            admin = schemas.UserCreate(
                first_name="Admin",
                last_name="User",
                email="admin@example.com",
                phone_number="1234567890",
                user_name="admin",
                password=ADMIN_PASSWORD # Use the variable here
            )
            # Admin is created without an invitation token
            crud.create_user(db=db, user=admin, role="admin", token=None)
    db.close()
    yield
    # Code to run on shutdown (if any)


app = FastAPI(lifespan=lifespan)

# --> SET the limiter on the app state and add the exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- CORS Middleware ---
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
# --> APPLY the rate limit decorator. This allows 5 attempts per minute.
@limiter.limit("2/minute")
# --> ADD 'request: Request' to the function signature
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
    # 1. Get and validate the invitation first.
    invitation = crud.get_invitation_by_token(db, token)
    if not invitation or invitation.is_used or invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Jeton d'inscription invalide ou expiré.")

    # 2. Check if the email from the invitation matches the one in the form.
    if invitation.email != user.email:
        raise HTTPException(status_code=400, detail="L'email d'inscription ne correspond pas à l'email de l'invitation.")

    # 3. Now, check for existing users.
    db_user_by_email = crud.get_user_by_email(db, email=user.email)
    if db_user_by_email:
        raise HTTPException(status_code=400, detail="Email déjà enregistré")

    db_user_by_username = crud.get_user_by_username(db, username=user.user_name)
    if db_user_by_username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur déjà enregistré")

    # 4. Create the user.
    created_user = crud.create_user(db=db, user=user, role="user")
    
    # 5. Delete the invitation now that the user is created.
    db.delete(invitation)
    db.commit()

    return created_user

@app.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    return current_user

@app.put("/users/me", response_model=schemas.User)
def update_user_me(user_update: schemas.UserUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    return crud.update_user(db=db, user_id=current_user.id, user_update=user_update)

@app.get("/admin/users/", response_model=list[schemas.User], dependencies=[Depends(auth.require_admin)])
def read_users(
    skip: int = 0,
    limit: int = 100,
    name_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    users = crud.get_users(db, skip=skip, limit=limit, name_filter=name_filter)
    return users

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
def update_user(user_id: int, user_update: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = crud.update_user(db=db, user_id=user_id, user_update=user_update)
    if db_user is None:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return db_user

@app.post("/admin/users/", response_model=schemas.User, dependencies=[Depends(auth.require_admin)])
def create_user_by_admin(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # This endpoint is protected and can only be accessed by an admin.
    # It does not require an invitation token.
    db_user_by_email = crud.get_user_by_email(db, email=user.email)
    if db_user_by_email:
        raise HTTPException(status_code=400, detail="Email déjà enregistré")

    db_user_by_username = crud.get_user_by_username(db, username=user.user_name)
    if db_user_by_username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur déjà enregistré")

    # The 'role' can be passed in the user object if you want admins to create other admins
    return crud.create_user(db=db, user=user, role=user.role if hasattr(user, 'role') else 'user')

# --- Passport Routes ---
@app.post("/passports/", response_model=schemas.Passport)
def create_passport(passport: schemas.PassportCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    return crud.create_user_passport(db=db, passport=passport, user_id=current_user.id)

# # /passports/upload-and-extract/ endpoint
# @app.post("/passports/upload-and-extract/", response_model=schemas.OcrUploadResponse)
# async def upload_and_extract_passport(
#     destination: Optional[str] = Form(None),
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(auth.get_current_active_user)
# ):
#     """
#     Receives a passport image or a single/multi-page PDF, extracts data from
#     each page, and creates new passport records for each successful extraction.
#     Returns a summary of successful and failed pages.
#     """
#     contents = await file.read()
    
#     extraction_results = ocr_service.extract_passport_data(
#         file_content=contents,
#         content_type=file.content_type
#     )

#     successes = []
#     failures = []

#     for result in extraction_results:
#         page_number = result.get("page_number")
#         if "data" in result:
#             passport_data = result["data"]
            
#             if destination:
#                 passport_data["destination"] = destination
            
#             passport_create_schema = schemas.PassportCreate(**passport_data)
#             try:
#                 created_passport = crud.create_user_passport(db=db, passport=passport_create_schema, user_id=current_user.id)
#                 successes.append(created_passport)
#             except HTTPException as e:
#                 failures.append({"page_number": page_number, "detail": e.detail})
#         elif "error" in result:
#             failures.append({"page_number": page_number, "detail": result["error"]})

#     return {"successes": successes, "failures": failures}



















@app.post("/passports/upload-and-extract/", response_model=schemas.OcrUploadResponse)
async def upload_and_extract_passport(
    background_tasks: BackgroundTasks,
    destination: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Receives a passport image or a multi-page PDF, streams it to a temporary file,
    extracts data from each page, and creates new passport records.
    
    This function handles errors on a per-page basis:
    - Successful extractions are saved to the database.
    - Pages with OCR errors or data validation errors are rejected and reported.
    The entire operation does not crash if some pages are invalid.
    """
    # 1. Stream the uploaded file to a temporary file on disk to save memory.
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as temp_file:
            while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                temp_file.write(content)
            temp_file_path = temp_file.name
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save uploaded file to disk.")

    # 2. Schedule the temporary file to be deleted after the response is sent.
    background_tasks.add_task(os.unlink, temp_file_path)

    # 3. Call the OCR service to process the file from its disk path.
    extraction_results = ocr_service.extract_passport_data(
        file_path=temp_file_path,
        content_type=file.content_type
    )

    successes = []
    failures = []

    # 4. Loop through results and handle each page individually.
    for result in extraction_results:
        page_number = result.get("page_number")

        # Handle pages where the OCR service itself reported an error.
        if "error" in result:
            failures.append({"page_number": page_number, "detail": result["error"]})
            continue  # Skip to the next page

        if "data" in result:
            passport_data = result["data"]
            
            # Use a try/except block to isolate validation and database errors.
            try:
                # Add the optional destination if provided.
                if destination:
                    passport_data["destination"] = destination
                
                # a. Attempt to validate the data using your Pydantic schema.
                passport_create_schema = schemas.PassportCreate(**passport_data)

                # b. If validation succeeds, create the passport in the database.
                created_passport = crud.create_user_passport(
                    db=db, passport=passport_create_schema, user_id=current_user.id
                )
                successes.append(created_passport)

            except ValidationError as e:
                # c. If Pydantic validation fails, record it as a failure.
                # We extract the first, most relevant error message.
                first_error = e.errors()[0]
                error_message = f"Validation Error on field '{first_error['loc'][0]}': {first_error['msg']}"
                failures.append({"page_number": page_number, "detail": error_message})
            
            except Exception as e:
                # d. Catch any other unexpected errors during DB creation.
                failures.append({"page_number": page_number, "detail": f"A database error occurred: {str(e)}"})
    
    # 5. Return a successful response with lists of successes and failures.
    return {"successes": successes, "failures": failures}





















# @app.post("/passports/upload-and-extract/", response_model=schemas.OcrUploadResponse)
# async def upload_and_extract_passport(
#     background_tasks: BackgroundTasks,
#     destination: Optional[str] = Form(None),
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(auth.get_current_active_user)
# ):
#     """
#     Receives a passport image or a multi-page PDF, streams it to a temporary file,
#     extracts data from each page, and creates new passport records.
    
#     This function handles errors on a per-page basis:
#     - Successful extractions are saved to the database.
#     - Pages with OCR errors or data validation errors are rejected and reported.
#     The entire operation does not crash if some pages are invalid.
#     """
#     # 1. Stream the uploaded file to a temporary file on disk to save memory.
#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as temp_file:
#             while content := await file.read(1024 * 1024):  # Read in 1MB chunks
#                 temp_file.write(content)
#             temp_file_path = temp_file.name
#     except Exception:
#         raise HTTPException(status_code=500, detail="Could not save uploaded file to disk.")

#     # 2. Schedule the temporary file to be deleted after the response is sent.
#     background_tasks.add_task(os.unlink, temp_file_path)

#     # 3. Call the OCR service to process the file from its disk path.
#     extraction_results = ocr_service.extract_passport_data(
#         file_path=temp_file_path,
#         content_type=file.content_type
#     )

#     successes = []
#     failures = []

#     # 4. Loop through results and handle each page individually.
#     for result in extraction_results:
#         page_number = result.get("page_number")

#         # Handle pages where the OCR service itself reported an error.
#         if "error" in result:
#             failures.append({"page_number": page_number, "detail": result["error"]})
#             continue  # Skip to the next page

#         if "data" in result:
#             passport_data = result["data"]
            
#             # Use a try/except block to isolate validation and database errors.
#             try:
#                 # Add the optional destination if provided.
#                 if destination:
#                     passport_data["destination"] = destination
                
#                 # a. Attempt to validate the data using your Pydantic schema.
#                 passport_create_schema = schemas.PassportCreate(**passport_data)

#                 # b. If validation succeeds, create the passport in the database.
#                 created_passport = crud.create_user_passport(
#                     db=db, passport=passport_create_schema, user_id=current_user.id
#                 )
                
#                 # --- THIS IS THE MODIFIED LINE ---
#                 # We now append a dictionary to include the page number with the success data.
#                 successes.append({"page_number": page_number, "data": created_passport})

#             except ValidationError as e:
#                 # c. If Pydantic validation fails, record it as a failure.
#                 # We extract the first, most relevant error message.
#                 first_error = e.errors()[0]
#                 error_message = f"Validation Error on field '{first_error['loc'][0]}': {first_error['msg']}"
#                 failures.append({"page_number": page_number, "detail": error_message})
            
#             except Exception as e:
#                 # d. Catch any other unexpected errors during DB creation.
#                 failures.append({"page_number": page_number, "detail": f"A database error occurred: {str(e)}"})
    
#     # 5. Return a successful response with lists of successes and failures.
#     return {"successes": successes, "failures": failures}



# /export/data endpoint
@app.get("/export/data")
def export_data(
    destination: Optional[str] = None,
    user_id: Optional[int] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    effective_user_id = current_user.id
    if current_user.role == "admin":
        # If admin provides a user_id, use it. Otherwise, it will be None (all users).
        effective_user_id = user_id
    
    filtered_data = crud.filter_data(db, destination, effective_user_id, first_name, last_name)
    
    if not filtered_data:
        raise HTTPException(status_code=404, detail="Aucune donnée de passeport trouvée pour les critères donnés")
    
    df = pd.DataFrame(filtered_data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    
    filename_parts = ["passeports"]
    if destination:
        filename_parts.append(destination.replace(' ', '_').lower())

    if current_user.role == 'admin':
        if user_id:
            filtered_user = crud.get_user(db, user_id)
            if filtered_user:
                filename_parts.append(f"pour_{filtered_user.user_name.lower()}")
            else:
                filename_parts.append(f"pour_utilisateur_{user_id}")
        else:
            filename_parts.append("rapport")
    else:
        filename_parts.append(f"pour_{current_user.user_name.lower()}")

    filename = f"{'_'.join(filename_parts)}.csv"
        
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

@app.get("/passports/", response_model=list[schemas.Passport])
def read_passports(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    user_filter: Optional[str] = None,
    voyage_filter: Optional[str] = None
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

# --- Voyage Routes ---
@app.post("/voyages/", response_model=schemas.Voyage)
def create_voyage(voyage: schemas.VoyageCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    return crud.create_user_voyage(db=db, voyage=voyage, user_id=current_user.id, passport_ids=voyage.passport_ids)

@app.get("/voyages/", response_model=list[schemas.Voyage])
def read_voyages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
    user_filter: Optional[str] = None
):
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
def get_unique_destinations(
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    target_user_id = current_user.id
    if current_user.role == "admin" and user_id is not None:
        target_user_id = user_id
    
    return crud.get_destinations_by_user_id(db, user_id=target_user_id)


# --- File Upload Route ---
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_active_user)):
    file_location = os.path.join(UPLOAD_DIR, f"{current_user.user_name}_{file.filename}")
    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())
    return {"info": f"fichier '{file.filename}' sauvegardé à '{file_location}'"}


@app.get("/invitations/{token}", response_model=schemas.Invitation)
def get_invitation(token: str, db: Session = Depends(get_db)):
    invitation = crud.get_invitation_by_token(db, token)
    if not invitation or invitation.is_used or invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=404, detail="Invitation non trouvée ou invalide.")
    return invitation

# --- Admin-specific Routes ---
@app.post("/admin/invitations", response_model=schemas.Invitation, dependencies=[Depends(auth.require_admin)])
def create_invitation(invitation: schemas.InvitationCreate, db: Session = Depends(get_db)):
    existing_user = crud.get_user_by_email(db, email=invitation.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Un utilisateur avec cet email existe déjà.")

    existing_invitation = crud.get_invitation_by_email(db, email=invitation.email)
    if existing_invitation and not existing_invitation.is_used:
        raise HTTPException(status_code=400, detail="Une invitation active pour cet email existe déjà.")
    
    return crud.create_invitation(db=db, email=invitation.email)


@app.get("/admin/invitations/", response_model=list[schemas.Invitation], dependencies=[Depends(auth.require_admin)])
def read_invitations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    invitations = crud.get_invitations(db, skip=skip, limit=limit)
    return invitations

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
