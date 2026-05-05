from sqlalchemy import Column, String, Integer
from database import Base
import uuid

def generate_uuid():
    return str(uuid.uuid4())


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    file_count = Column(Integer)
    status = Column(String, default="pending")   # NEW


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String)
    file_name = Column(String)
    category = Column(String, default="uncategorized")
    status = Column(String, default="pending")   # NEW