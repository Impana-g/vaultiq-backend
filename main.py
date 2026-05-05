from fastapi import FastAPI, Depends, HTTPException
import os
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import engine, SessionLocal, Base
from models import UploadSession, UploadedFile

from PyPDF2 import PdfReader
from openai import OpenAI
from transformers import pipeline

# Load model (runs once)
classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli"
)

# Load environment variables
load_dotenv()
print("API KEY:", os.getenv("OPENAI_API_KEY"))  

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Create FastAPI app
app = FastAPI(title="VaultIQ Backend")

# Create DB tables
Base.metadata.create_all(bind=engine)



# DB Dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



# PDF TEXT EXTRACTION

def extract_text_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)

        if len(reader.pages) == 0:
            return ""

        text = reader.pages[0].extract_text() or ""
        return text[:2000]

    except Exception as e:
        print("PDF ERROR:", e)
        return ""

# GENAI CLASSIFICATION
def classify_document(text, filename):
    combined = (text + " " + filename)

    labels = ["financial", "legal", "general"]

    try:
        # 🔹 Try GenAI (transformers)
        result = classifier(combined[:1000], labels)
        predicted = result["labels"][0]
        print("AI RESULT:", predicted)
        return predicted

    except Exception as e:
        print("AI failed, using fallback:", e)

        # 🔹 Fallback to keyword logic
        combined = combined.lower()

        financial_keywords = [
            "invoice", "payment", "amount", "balance", "bank",
            "transaction", "bill", "salary", "profit", "loss"
        ]

        legal_keywords = [
            "agreement", "contract", "law", "legal",
            "compliance", "terms", "nda", "policy"
        ]

        f_score = sum(word in combined for word in financial_keywords)
        l_score = sum(word in combined for word in legal_keywords)

        if f_score > l_score and f_score > 0:
            return "financial"
        elif l_score > f_score and l_score > 0:
            return "legal"
        else:
            return "general"

# HOME API
@app.get("/")
def home():
    return {"message": "VaultIQ Backend Running"}


# MAIN PROCESS API

@app.post("/api/v1/dev/process")
def dev_process(db: Session = Depends(get_db)):

    folder = os.getenv("MATERIALS_FOLDER", "./mp_materials")

    if not os.path.exists(folder):
        raise HTTPException(status_code=400, detail="Folder not found")

    files = [f for f in os.listdir(folder) if f.endswith(".pdf")]

    if not files:
        raise HTTPException(status_code=400, detail="No PDF files found")

    # Create session
    session = UploadSession(
        file_count=len(files),
        status="processing"
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    result = []

    for file in files:
        try:
            file_path = os.path.join(folder, file)

            # Extract text
            text = extract_text_from_pdf(file_path)

            if len(text.strip()) < 20:
                text = file.lower()

            # Classify (GenAI)
            category = classify_document(text, file)

            new_file = UploadedFile(
                session_id=session.id,
                file_name=file,
                category=category,
                status="completed"
            )

            db.add(new_file)

            result.append({
                "file_name": file,
                "category": category
            })

        except Exception as file_error:
            print("File Error:", file_error)

    db.commit()

    session.status = "completed"
    db.commit()

    return {
        "session_id": session.id,
        "files": result
    }



# STATUS API

@app.get("/api/v1/process/{session_id}/status")
def get_status(session_id: str, db: Session = Depends(get_db)):

    session = db.query(UploadSession).filter(
        UploadSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    files = db.query(UploadedFile).filter(
        UploadedFile.session_id == session_id
    ).all()

    processed = sum(1 for f in files if f.status == "completed")

    total = session.file_count

    if processed == 0:
        status = "pending"
    elif processed < total:
        status = "processing"
    else:
        status = "completed"

    return {
        "session_id": session_id,
        "total_files": total,
        "processed_files": processed,
        "status": status
    }