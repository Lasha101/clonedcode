from pydantic import BaseModel, EmailStr
from typing import List, Optional
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
    owner_id: int
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

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    # --- NEW FIELD ---
    uploaded_pages_count: Optional[int] = None
    # --- END OF NEW FIELD ---

class User(UserBase):
    id: int
    role: str
    # --- NEW FIELD ---
    uploaded_pages_count: int
    # --- END OF NEW FIELD ---
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

# --- NEW/UPDATED OCR SCHEMAS ---

class OcrJobFailure(BaseModel):
    page_number: int
    detail: str

class OcrJobSuccess(BaseModel):
    page_number: int
    data: Passport # <-- Changed from Any to Passport

class OcrJob(BaseModel):
    id: str
    user_id: int
    file_name: str
    status: str # e.g., "processing", "complete", "failed"
    created_at: datetime
    finished_at: Optional[datetime] = None
    successes: List[OcrJobSuccess] = []
    failures: List[OcrJobFailure] = []
    
    class Config:
        from_attributes = True # for in-memory dict

# --- NEW SCHEMA FOR MULTI-DELETE ---
class PassportDeleteMultiple(BaseModel):
    passport_ids: List[int]

# This line is needed at the end of the file to resolve the forward reference
User.model_rebuild()