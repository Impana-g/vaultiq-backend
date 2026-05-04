from sqlalchemy import Column, String, Integer
from database import Base
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    status = Column(String, default="pending")
    file_count = Column(Integer, default=0)
    categorized_count = Column(Integer, default=0)

class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String)
    file_name = Column(String)
    category = Column(String, default="uncategorized")