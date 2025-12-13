# --------------- START OF FILE: schemas.py ---------------

from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any, Dict
from datetime import date, datetime

class VoyageBase(BaseModel):
    destination: str

class VoyageCreate(VoyageBase):
    passport_ids: List[int] = []
    
class Voyage(VoyageBase):
    id: int
    user_id: int
    class Config:
        from_attributes = True

class PassportBase(BaseModel):
    first_name: str
    last_name: str
    birth_date: date
    expiration_date: date
    delivery_date: Optional[date] = None
    nationality: str
    passport_number: str
    confidence_score: Optional[float] = None

class PassportCreate(PassportBase):
    destination: Optional[str] = None

class Passport(PassportBase):
    id: int
    owner_id: Optional[int] = None
    voyages: List[Voyage] = []
    class Config:
        from_attributes = True

class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    user_name: str

class UserCreate(UserBase):
    password: str
    page_credits: Optional[int] = 0 # Default to 0 credits on creation

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    uploaded_pages_count: Optional[int] = None
    page_credits: Optional[int] = None # Allow admin to update credits

class User(UserBase):
    id: int
    role: str
    uploaded_pages_count: int
    page_credits: int # Include in response
    passports: List["Passport"] = []
    voyages: List[Voyage] = []
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class InvitationCreate(BaseModel):
    email: EmailStr

class Invitation(InvitationCreate):
    id: int
    token: str
    expires_at: datetime
    is_used: bool
    class Config:
        from_attributes = True

class InvitationUpdate(BaseModel):
    expires_at: Optional[datetime] = None
    is_used: Optional[bool] = None

# --- OCR SCHEMAS ---

class OcrJob(BaseModel):
    id: str
    user_id: int
    file_name: str
    status: str 
    progress: int
    created_at: datetime
    finished_at: Optional[datetime] = None
    successes: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    
    class Config:
        from_attributes = True

# --- SCHEMA FOR MULTI-DELETE ---
class PassportDeleteMultiple(BaseModel):
    passport_ids: List[int]

# This line is needed at the end of the file to resolve the forward reference
User.model_rebuild()

# --------------- END OF FILE: schemas.py ---------------