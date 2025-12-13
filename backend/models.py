# --------------- START OF FILE: models.py ---------------

# /models.py
from sqlalchemy import Boolean, Column, Integer, Float, String, Date, ForeignKey, Table, DateTime, JSON
from sqlalchemy.orm import relationship
from database import Base

voyage_passport_association = Table('voyage_passport_association', Base.metadata,
    Column('voyage_id', Integer, ForeignKey('voyages.id'), primary_key=True),
    Column('passport_id', Integer, ForeignKey('passports.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone_number = Column(String)
    user_name = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    
    # --- EXISTING FIELD ---
    uploaded_pages_count = Column(Integer, default=0, nullable=False)
    
    # --- NEW FIELD (CREDITS) ---
    page_credits = Column(Integer, default=0, nullable=False)
    
    passports = relationship("Passport", back_populates="owner", cascade="all, delete-orphan")
    voyages = relationship("Voyage", back_populates="user", cascade="all, delete-orphan")
    # Relation to OCR Jobs
    ocr_jobs = relationship("OcrJob", back_populates="user", cascade="all, delete-orphan")

class Passport(Base):
    __tablename__ = "passports"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    birth_date = Column(Date)
    delivery_date = Column(Date, nullable=True) 
    expiration_date = Column(Date)
    nationality = Column(String, index=True)
    passport_number = Column(String, index=True, nullable=False) 
    confidence_score = Column(Float)
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="passports")
    voyages = relationship("Voyage", secondary=voyage_passport_association, back_populates="passports")

class Voyage(Base):
    __tablename__ = "voyages"
    id = Column(Integer, primary_key=True, index=True)
    destination = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="voyages")
    passports = relationship("Passport", secondary=voyage_passport_association, back_populates="voyages")

class Invitation(Base):
    __tablename__ = "invitations"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)

# --- NEW TABLE FOR OCR JOBS (PERSISTENT) ---
class OcrJob(Base):
    __tablename__ = "ocr_jobs"
    
    id = Column(String, primary_key=True, index=True) # UUID
    user_id = Column(Integer, ForeignKey("users.id"))
    file_name = Column(String, nullable=False)
    status = Column(String, default="processing") # processing, complete, failed
    progress = Column(Integer, default=0) # 0 to 100
    created_at = Column(DateTime)
    finished_at = Column(DateTime, nullable=True)
    
    # JSON columns for storing lists of results
    # SQLAlchemy handles serialization/deserialization automatically
    successes = Column(JSON, default=list) 
    failures = Column(JSON, default=list)

    user = relationship("User", back_populates="ocr_jobs")

# --------------- END OF FILE: models.py ---------------