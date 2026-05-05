import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base


def _uuid():
    return str(uuid.uuid4())


class SessionStatus(str, enum.Enum):
    pending    = "pending"
    processing = "processing"
    completed  = "completed"
    failed     = "failed"


class DDCategory(str, enum.Enum):
    financial     = "financial"
    legal         = "legal"
    general       = "general"
    uncategorized = "uncategorized"


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id                = Column(String, primary_key=True, default=_uuid)
    status            = Column(SAEnum(SessionStatus), default=SessionStatus.pending)
    file_count        = Column(Integer, default=0)
    categorized_count = Column(Integer, default=0)
    failed_count      = Column(Integer, default=0)
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    files = relationship("UploadedFile", back_populates="session")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id            = Column(String, primary_key=True, default=_uuid)
    session_id    = Column(String, ForeignKey("upload_sessions.id"), nullable=False)
    file_name     = Column(String, nullable=False)
    category      = Column(SAEnum(DDCategory), default=DDCategory.uncategorized)
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    session = relationship("UploadSession", back_populates="files")
    results = relationship("FileProcessingResult", back_populates="file")


class FileProcessingResult(Base):
    __tablename__ = "file_processing_results"

    id            = Column(String, primary_key=True, default=_uuid)
    file_id       = Column(String, ForeignKey("uploaded_files.id"), nullable=False)
    result_type   = Column(String, nullable=False)
    question      = Column(Text, nullable=True)
    answer        = Column(Text, nullable=False)
    ai_model_used = Column(String, nullable=True)
    tokens_used   = Column(Integer, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    file = relationship("UploadedFile", back_populates="results")