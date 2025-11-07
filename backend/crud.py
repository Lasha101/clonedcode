# --------------- START OF FILE: crud.py ---------------

# /crud.py

from sqlalchemy.orm import Session, joinedload, outerjoin
import models, schemas, auth
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import HTTPException
from http import HTTPStatus

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()
def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.user_name == username).first()
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()
def get_users(db: Session, skip: int = 0, limit: int = 100, name_filter: Optional[str] = None):
    # Exclude the admin user from the list of manageable users
    query = db.query(models.User).filter(models.User.user_name != "admin")
    if name_filter:
        search = f"%{name_filter}%"
        query = query.filter(
            models.User.first_name.ilike(search) |
            models.User.last_name.ilike(search) |
            models.User.user_name.ilike(search) |
            models.User.email.ilike(search)
        )
    return query.offset(skip).limit(limit).all()

def get_all_users_for_filtering(db: Session):
    # Return all users, including the admin, for filtering purposes
    return db.query(models.User).all()



def create_user(db: Session, user: schemas.UserCreate, token: Optional[str] = None, role: str = "user"):
    # If a token is provided, validate it (for public registration)
    if token:
        invitation = get_invitation_by_token(db, token)
        if not invitation or invitation.is_used or invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return None # Invalid token
        db.delete(invitation)

    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        **user.model_dump(exclude={"password"}),
        hashed_password=hashed_password,
        role=role # Assign role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user: return None
    update_data = user_update.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        hashed_password = auth.get_password_hash(update_data["password"])
        db_user.hashed_password = hashed_password
    update_data.pop("password", None)
    for key, value in update_data.items():
        setattr(db_user, key, value)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    db_user = get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user

def get_passport(db: Session, passport_id: int):
    return db.query(models.Passport).filter(models.Passport.id == passport_id).first()

def get_passports(db: Session, skip: int = 0, limit: int = 100, user_filter: Optional[str] = None, voyage_filter: Optional[str] = None):
    query = db.query(models.Passport)
    if user_filter:
        if user_filter.isdigit():
            query = query.filter(models.Passport.owner_id == int(user_filter))
        else:
            query = query.join(models.User).filter(
                models.User.first_name.ilike(f"%{user_filter}%") |
                models.User.last_name.ilike(f"%{user_filter}%") |
                models.User.user_name.ilike(f"%{user_filter}%")
            )
    if voyage_filter:
        query = query.join(models.Passport.voyages)
        if voyage_filter.isdigit():
            query = query.filter(models.Voyage.id == int(voyage_filter))
        else:
            query = query.filter(models.Voyage.destination.ilike(f"%{voyage_filter}%"))
    return query.offset(skip).limit(limit).all()

def get_passports_by_user(db: Session, user_id: int):
    return db.query(models.Passport).filter(models.Passport.owner_id == user_id).all()

def create_user_passport(db: Session, passport: schemas.PassportCreate, user_id: int):
    if passport.destination:
        existing_association = db.query(models.Passport).join(models.Passport.voyages).filter(
            models.Passport.owner_id == user_id,
            models.Passport.passport_number == passport.passport_number,
            models.Voyage.destination == passport.destination
        ).first()

        if existing_association:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=f"Le passeport numéro '{passport.passport_number}' est déjà enregistré pour la destination '{passport.destination}'.",
            )

    passport_data = passport.model_dump(exclude={"destination", "confidence_score"})
    db_passport = models.Passport(**passport_data, owner_id=user_id, confidence_score=passport.confidence_score)
    db.add(db_passport)
    db.commit()
    db.refresh(db_passport)

    if passport.destination:
        db_voyage = db.query(models.Voyage).filter(
            models.Voyage.user_id == user_id,
            models.Voyage.destination == passport.destination
        ).first()

        if not db_voyage:
            db_voyage = models.Voyage(destination=passport.destination, user_id=user_id)
            db.add(db_voyage)

        db_passport.voyages.append(db_voyage)

    db.commit()
    db.refresh(db_passport)
    return db_passport

def update_passport(db: Session, passport_id: int, passport_update: schemas.PassportCreate):
    db_passport = get_passport(db, passport_id)
    if not db_passport:
        return None

    if passport_update.destination:
        existing_association = db.query(models.Passport).join(models.Passport.voyages).filter(
            models.Passport.owner_id == db_passport.owner_id,
            models.Passport.passport_number == passport_update.passport_number,
            models.Voyage.destination == passport_update.destination,
            models.Passport.id != passport_id
        ).first()
        if existing_association:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=f"Le passeport numéro '{passport_update.passport_number}' est déjà enregistré pour la destination '{passport_update.destination}'.",
            )

    update_data = passport_update.model_dump(exclude={"destination"})
    for key, value in update_data.items():
        setattr(db_passport, key, value)

    db_passport.voyages.clear()

    if passport_update.destination:
        db_voyage = db.query(models.Voyage).filter(
            models.Voyage.user_id == db_passport.owner_id,
            models.Voyage.destination == passport_update.destination
        ).first()
        if not db_voyage:
            db_voyage = models.Voyage(destination=passport_update.destination, user_id=db_passport.owner_id)
            db.add(db_voyage)
        db_passport.voyages.append(db_voyage)

    db.commit()
    db.refresh(db_passport)
    return db_passport

def delete_passport(db: Session, passport_id: int):
    db_passport = get_passport(db, passport_id)
    if db_passport:
        db.delete(db_passport)
        db.commit()
    return db_passport

def get_voyage(db: Session, voyage_id: int):
    return db.query(models.Voyage).filter(models.Voyage.id == voyage_id).first()

def get_voyages(db: Session, skip: int = 0, limit: int = 100, user_filter: Optional[str] = None):
    query = db.query(models.Voyage)
    if user_filter:
        if user_filter.isdigit():
            query = query.filter(models.Voyage.user_id == int(user_filter))
        else:
            query = query.join(models.User).filter(
                models.User.first_name.ilike(f"%{user_filter}%") |
                models.User.last_name.ilike(f"%{user_filter}%") |
                models.User.user_name.ilike(f"%{user_filter}%")
            )
    return query.offset(skip).limit(limit).all()

def get_voyages_by_user(db: Session, user_id: int):
    return db.query(models.Voyage).filter(models.Voyage.user_id == user_id).all()

def create_user_voyage(db: Session, voyage: schemas.VoyageCreate, user_id: int, passport_ids: list[int]):
    db_voyage = models.Voyage(destination=voyage.destination, user_id=user_id)
    if passport_ids:
        passports = db.query(models.Passport).filter(models.Passport.id.in_(passport_ids)).all()
        db_voyage.passports.extend(passports)
    db.add(db_voyage)
    db.commit()
    db.refresh(db_voyage)
    return db_voyage

def update_voyage(db: Session, voyage_id: int, voyage_update: schemas.VoyageCreate):
    db_voyage = get_voyage(db, voyage_id)
    if not db_voyage: return None
    db_voyage.destination = voyage_update.destination
    if voyage_update.passport_ids is not None:
        passports = db.query(models.Passport).filter(models.Passport.id.in_(voyage_update.passport_ids)).all()
        db_voyage.passports = passports
    db.commit()
    db.refresh(db_voyage)
    return db_voyage

def delete_voyage(db: Session, voyage_id: int):
    db_voyage = get_voyage(db, voyage_id)
    if db_voyage:
        db.delete(db_voyage)
        db.commit()
    return db_voyage

def filter_data(db: Session, destination: Optional[str], user_id: Optional[int], first_name: Optional[str], last_name: Optional[str]):
    query = db.query(models.Passport)

    if user_id is not None:
        query = query.filter(models.Passport.owner_id == user_id)

    if destination:
        query = query.join(models.Passport.voyages).filter(models.Voyage.destination.ilike(f"%{destination}%"))

    if first_name:
        query = query.filter(models.Passport.first_name.ilike(f"%{first_name}%"))
    if last_name:
        query = query.filter(models.Passport.last_name.ilike(f"%{last_name}%"))

    query = query.options(joinedload(models.Passport.voyages))
    
    results = query.all()
    
    data_list = []
    processed_passport_ids = set()

    for passport in results:
        if passport.id in processed_passport_ids:
            continue
        
        destinations = [v.destination for v in passport.voyages]
        if destination:
            dest_str = destination
        elif destinations:
            dest_str = ", ".join(sorted(list(set(destinations))))
        else:
            dest_str = "N/A"

        data_list.append({
            "id": passport.id, "first_name": passport.first_name, "last_name": passport.last_name,
            "birth_date": passport.birth_date, "delivery_date": passport.delivery_date,
            "expiration_date": passport.expiration_date, "nationality": passport.nationality,
            "passport_number": passport.passport_number, "owner_id": passport.owner_id,
            "destination": dest_str
        })
        processed_passport_ids.add(passport.id)
        
    return data_list

def create_invitation(db: Session, email: str):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db_invitation = models.Invitation(email=email, token=token, expires_at=expires_at)
    db.add(db_invitation)
    db.commit()
    db.refresh(db_invitation)
    return db_invitation




def get_invitation_by_token(db: Session, token: str):
    return db.query(models.Invitation).filter(models.Invitation.token == token).first()

def get_invitation_by_email(db: Session, email: str):
    return db.query(models.Invitation).filter(models.Invitation.email == email).first()

def get_invitation(db: Session, invitation_id: int):
    return db.query(models.Invitation).filter(models.Invitation.id == invitation_id).first()

def get_invitations(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Invitation).offset(skip).limit(limit).all()

def update_invitation(db: Session, invitation_id: int, invitation_update: schemas.InvitationUpdate):
    db_invitation = get_invitation(db, invitation_id)
    if not db_invitation:
        return None
    update_data = invitation_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_invitation, key, value)
    db.commit()
    db.refresh(db_invitation)
    return db_invitation

def delete_invitation(db: Session, invitation_id: int):
    db_invitation = get_invitation(db, invitation_id)
    if db_invitation:
        db.delete(db_invitation)
        db.commit()
    return db_invitation

def get_destinations_by_user_id(db: Session, user_id: int) -> List[str]:
    query = db.query(models.Voyage.destination).filter(models.Voyage.user_id == user_id).distinct()
    destinations = [item[0] for item in query.all()]
    return destinations

# --- NEW FUNCTION FOR MULTI-DELETE ---
def delete_multiple_passports(db: Session, passport_ids: List[int], user_id: int, role: str) -> int:
    """
    Deletes multiple passports.
    If the user is not an admin, it only deletes passports they own.
    """
    query = db.query(models.Passport).filter(models.Passport.id.in_(passport_ids))
    
    # Security check: Non-admins can only delete their own passports
    if role != "admin":
        query = query.filter(models.Passport.owner_id == user_id)
    
    # Get the actual list of passports that will be deleted
    passports_to_delete = query.all()
    ids_to_delete = [p.id for p in passports_to_delete]
    
    if not ids_to_delete:
        return 0
        
    # Perform the bulk delete on the verified IDs
    deleted_count = db.query(models.Passport).filter(
        models.Passport.id.in_(ids_to_delete)
    ).delete(synchronize_session=False)
    
    db.commit()
    
    return deleted_count
# --- END OF NEW FUNCTION ---

# --------------- END OF FILE: crud.py ---------------