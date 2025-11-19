# /database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables (especially for local dev)
load_dotenv()

# --- UPDATED DATABASE URL LOGIC ---
# Use the cloud DATABASE_URL if it's set (in AWS).
# Otherwise, fall back to the local SQLite file for development.
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres"):
    # We are in production on AWS
    SQLALCHEMY_DATABASE_URL = DATABASE_URL
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
else:
    # We are running locally
    print("DATABASE_URL not found, falling back to local sqlite...")
    SQLALCHEMY_DATABASE_URL = "sqlite:///./travel_app.db"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
# --- END OF UPDATE ---

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()