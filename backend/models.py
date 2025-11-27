# /models.py
from sqlalchemy import Boolean, Column, Integer, Float, String, Date, ForeignKey, Table, DateTime
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
    
    # --- NEW FIELD ---
    uploaded_pages_count = Column(Integer, default=0, nullable=False)
    # --- END OF NEW FIELD ---

    passports = relationship("Passport", back_populates="owner", cascade="all, delete-orphan")
    voyages = relationship("Voyage", back_populates="user", cascade="all, delete-orphan")

class Passport(Base):
    __tablename__ = "passports"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    birth_date = Column(Date)
    delivery_date = Column(Date, nullable=True) # <-- This was the change from last time
    expiration_date = Column(Date)
    nationality = Column(String, index=True)
    passport_number = Column(String, index=True, nullable=False) # Removed unique=True
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