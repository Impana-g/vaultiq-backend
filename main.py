from fastapi import FastAPI, Depends
import os

from database import engine, SessionLocal
import models
from models import UploadSession, UploadedFile
from sqlalchemy.orm import Session

# 📄 PDF Reader
from PyPDF2 import PdfReader

# 🔐 API Key (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        print("OpenAI init error:", e)

# ✅ Create app
app = FastAPI()

# ✅ Create tables
models.Base.metadata.create_all(bind=engine)

# ✅ DB dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 📄 Extract text from PDF
def extract_text_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""

        for page in reader.pages:
            text += page.extract_text() or ""

        return text[:1000]
    except Exception as e:
        print("PDF ERROR:", e)
        return ""

# ✅ Categorisation (Balanced fallback)
def classify_document(text):
    text_lower = text.lower()

    def fallback():
        # ✅ STRICT financial keywords
        if any(word in text_lower for word in [
            "finance", "financial", "balance sheet", "invoice", "tax", "revenue"
        ]):
            return "financial"

        # ✅ legal keywords
        elif any(word in text_lower for word in [
            "agreement", "contract", "law", "legal"
        ]):
            return "legal"

        else:
            return "general"

    # 🤖 AI (optional)
    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": f"Classify into: financial, legal, or general.\n\n{text[:500]}"
                }]
            )
            return response.choices[0].message.content.strip().lower()
        except Exception as e:
            print("AI ERROR:", e)
            return fallback()

    return fallback()

# ✅ Home API
@app.get("/")
def home():
    return {"message": "VaultIQ Backend Running"}

# ✅ Upload + Process API
@app.post("/api/v1/dev/process")
def dev_upload():
    db = SessionLocal()

    folder = r"C:\Users\Impana\OneDrive\Desktop\vaultiq-backend\mp_materials"

    if not os.path.exists(folder):
        return {"error": "Folder not found"}

    files = os.listdir(folder)

    # Create session
    session = UploadSession(file_count=len(files))
    db.add(session)
    db.commit()
    db.refresh(session)

    result = []

    for file in files:
        file_path = os.path.join(folder, file)

        # 📄 Extract text
        text = extract_text_from_pdf(file_path)

        print("EXTRACTED TEXT:", text[:200])

        # ✅ SMART INPUT SELECTION (NO OVER-COMBINE)
        if text.strip() == "" or len(text.strip()) < 30:
            final_text = file.lower()
        else:
            final_text = text.lower()

        # Categorise
        category = classify_document(final_text)

        new_file = UploadedFile(
            session_id=session.id,
            file_name=file,
            category=category
        )

        db.add(new_file)

        result.append({
            "file_name": file,
            "category": category
        })

    db.commit()

    return {
        "session_id": session.id,
        "files": result
    }

# ✅ Status API
@app.get("/api/v1/process/{session_id}/status")
def get_status(session_id: str, db: Session = Depends(get_db)):

    session = db.query(UploadSession).filter(
        UploadSession.id == session_id
    ).first()

    if not session:
        return {"error": "Session not found"}

    total_files = session.file_count

    categorized_files = db.query(UploadedFile).filter(
        UploadedFile.session_id == session_id
    ).count()

    return {
        "session_id": session_id,
        "total_files": total_files,
        "categorized_files": categorized_files,
        "status": "completed"
    }