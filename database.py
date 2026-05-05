from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Read from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vaultiq.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # only for SQLite
)

# Proper session config
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

# FastAPI dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()