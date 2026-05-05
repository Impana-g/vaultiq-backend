from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
from PyPDF2 import PdfReader
import os
import logging

load_dotenv()

from database import engine, SessionLocal, Base
from models import UploadSession, UploadedFile, FileProcessingResult, SessionStatus, DDCategory

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="VaultIQ Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Create DB tables ──────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── Settings ──────────────────────────────────────────────────────────────────
MATERIALS_FOLDER = os.getenv("MATERIALS_FOLDER", "./mp_materials")
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Request schemas ───────────────────────────────────────────────────────────
class QuestionRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v):
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Question must be at least 5 characters")
        if len(v) > 500:
            raise ValueError("Question must be under 500 characters")
        return v


class SummariseRequest(BaseModel):
    file_name: str
    style: str = "executive"

    @field_validator("style")
    @classmethod
    def validate_style(cls, v):
        allowed = ["executive", "bullet_points", "detailed"]
        if v not in allowed:
            raise ValueError(f"style must be one of {allowed}")
        return v


# ── DB dependency ─────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Groq client ───────────────────────────────────────────────────────────────
def get_groq_client():
    if not GROQ_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )


# ── PDF helpers ───────────────────────────────────────────────────────────────
def extract_text_from_pdf(file_path: str, max_chars: int = 4000) -> str:
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return ""
    if not file_path.lower().endswith(".pdf"):
        return ""
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
            if len(text) >= max_chars:
                break
        return text[:max_chars].strip()
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return ""


def extract_text_by_pages(file_path: str) -> list:
    try:
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append({"page": i + 1, "text": text})
        return pages
    except Exception as e:
        logger.error(f"Page extraction failed: {e}")
        return []


# ── Classification ────────────────────────────────────────────────────────────
FINANCIAL_KEYWORDS = [
    "balance sheet", "revenue", "profit", "loss", "audit", "tax",
    "invoice", "cash flow", "equity", "dividend", "capital", "earnings",
    "budget", "ebitda", "income statement", "financial", "p&l"
]
LEGAL_KEYWORDS = [
    "agreement", "contract", "nda", "non-disclosure", "clause",
    "jurisdiction", "liability", "arbitration", "intellectual property",
    "compliance", "regulatory", "obligation", "legal", "law", "attorney"
]


def keyword_classify(text: str) -> str:
    text_lower = text.lower()
    fin_score = sum(1 for kw in FINANCIAL_KEYWORDS if kw in text_lower)
    leg_score = sum(1 for kw in LEGAL_KEYWORDS if kw in text_lower)
    if fin_score == 0 and leg_score == 0:
        return "general"
    return "financial" if fin_score >= leg_score else "legal"


def llm_classify(text: str) -> str | None:
    client = get_groq_client()
    if not client:
        return None
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a document classification expert. "
                        "Classify the document into exactly one of: financial, legal, general. "
                        "Reply with ONLY one word. No punctuation. No explanation."
                    )
                },
                {
                    "role": "user",
                    "content": f"Classify this document:\n\n{text[:1500]}"
                }
            ],
            max_tokens=10,
            temperature=0,
        )
        result = response.choices[0].message.content.strip().lower().strip(".,!?")
        return result if result in ("financial", "legal", "general") else None
    except Exception as e:
        logger.error(f"Groq classification failed: {e}")
        return None


def classify_document(text: str, file_name: str = "") -> tuple[str, str]:
    # Strategy 1: LLM (best quality)
    if text.strip():
        result = llm_classify(text)
        if result:
            return result, "llm"

    # Strategy 2: Keywords (free fallback)
    if len(text.strip()) >= 30:
        return keyword_classify(text), "keyword"

    # Strategy 3: Filename (last resort)
    name = file_name.lower()
    if any(w in name for w in ["financial", "finance", "audit", "tax", "invoice"]):
        return "financial", "filename"
    if any(w in name for w in ["contract", "agreement", "legal", "nda"]):
        return "legal", "filename"
    return "general", "filename"


# ── Groq Q&A ──────────────────────────────────────────────────────────────────
def ask_groq(question: str, context: str) -> tuple[str, int]:
    client = get_groq_client()
    if not client:
        return "Groq not configured. Add GROQ_API_KEY to your .env file.", 0
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise document analyst. "
                        "Answer the question using ONLY the provided document text. "
                        "If the answer is not in the document, say exactly: "
                        "'Not found in this document.' "
                        "Never guess or use outside knowledge."
                    )
                },
                {
                    "role": "user",
                    "content": f"Document:\n{context}\n\nQuestion: {question}"
                }
            ],
            max_tokens=400,
            temperature=0.1,
        )
        tokens = response.usage.total_tokens if response.usage else 0
        return response.choices[0].message.content.strip(), tokens
    except Exception as e:
        logger.error(f"Groq Q&A failed: {e}")
        return f"AI error: {str(e)}", 0


# ── Groq Summarise ────────────────────────────────────────────────────────────
def summarise_groq(text: str, style: str) -> tuple[str, int]:
    client = get_groq_client()
    if not client:
        return "Groq not configured. Add GROQ_API_KEY to your .env file.", 0

    style_instructions = {
        "executive": (
            "Write a 3-5 sentence executive summary covering: "
            "document type, key parties involved, main figures or obligations, and any risks."
        ),
        "bullet_points": (
            "Write exactly 5-8 bullet points. Each bullet must be one clear, "
            "specific sentence covering the most important facts, figures, and obligations."
        ),
        "detailed": (
            "Write a detailed 2-3 paragraph analysis covering: "
            "(1) what the document is and who the parties are, "
            "(2) the main terms, figures, or obligations, "
            "(3) any important conditions, risks, or notable clauses."
        ),
    }

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior analyst at a top investment bank. "
                        "You write precise, professional document summaries. "
                        "Use formal language. Never add information not in the document."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"{style_instructions[style]}\n\n"
                        f"Document:\n{text[:5000]}"
                    )
                }
            ],
            max_tokens=500,
            temperature=0.3,
        )
        tokens = response.usage.total_tokens if response.usage else 0
        return response.choices[0].message.content.strip(), tokens
    except Exception as e:
        logger.error(f"Groq summarise failed: {e}")
        return f"AI error: {str(e)}", 0


# ── Background worker ─────────────────────────────────────────────────────────
def process_files_background(session_id: str, pdf_paths: list[str]):
    db = SessionLocal()
    try:
        session = db.query(UploadSession).filter(
            UploadSession.id == session_id
        ).first()
        if not session:
            return

        session.status = SessionStatus.processing
        db.commit()

        for pdf_path in pdf_paths:
            file_name = os.path.basename(pdf_path)
            try:
                text = extract_text_from_pdf(pdf_path)
                category_str, method = classify_document(text, file_name)

                try:
                    category = DDCategory(category_str)
                except ValueError:
                    category = DDCategory.uncategorized

                new_file = UploadedFile(
                    session_id=session_id,
                    file_name=file_name,
                    category=category,
                )
                db.add(new_file)
                session.categorized_count += 1
                db.commit()
                logger.info(f"✓ {file_name} → {category_str} (via {method})")

            except Exception as e:
                logger.error(f"Failed: {file_name}: {e}")
                failed = UploadedFile(
                    session_id=session_id,
                    file_name=file_name,
                    category=DDCategory.uncategorized,
                    error_message=str(e),
                )
                db.add(failed)
                session.failed_count += 1
                db.commit()

        session.status = SessionStatus.completed
        db.commit()
        logger.info(f"Session {session_id[:8]} complete")

    except Exception as e:
        logger.error(f"Background worker crashed: {e}")
        try:
            session = db.query(UploadSession).filter(
                UploadSession.id == session_id
            ).first()
            if session:
                session.status = SessionStatus.failed
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def home():
    return {"message": "VaultIQ Backend Running", "version": "1.0.0"}


# ── 1. Process documents ──────────────────────────────────────────────────────
@app.post("/api/v1/dev/process", status_code=202)
def dev_process(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    folder = MATERIALS_FOLDER

    if not os.path.exists(folder):
        raise HTTPException(
            status_code=400,
            detail=f"Folder '{folder}' not found. Check MATERIALS_FOLDER in .env"
        )

    pdf_paths = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_paths:
        raise HTTPException(
            status_code=400,
            detail="No PDF files found in folder"
        )

    session = UploadSession(
        file_count=len(pdf_paths),
        status=SessionStatus.pending,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    background_tasks.add_task(
        process_files_background,
        session.id,
        pdf_paths
    )

    return {
        "session_id": session.id,
        "total_files": len(pdf_paths),
        "message": (
            f"Processing started for {len(pdf_paths)} files. "
            f"Poll /api/v1/process/{session.id}/status to track."
        )
    }


# ── 2. Check status ───────────────────────────────────────────────────────────
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

    return {
        "session_id": session_id,
        "status": session.status,
        "total_files": session.file_count,
        "categorized_files": session.categorized_count,
        "failed_files": session.failed_count,
        "files": [
            {
                "file_name": f.file_name,
                "category": f.category,
                "error": f.error_message,
            }
            for f in files
        ]
    }


# ── 3. Ask a question (Map-Reduce Q&A) ───────────────────────────────────────
@app.post("/api/v1/ask")
def ask(req: QuestionRequest, db: Session = Depends(get_db)):
    folder = MATERIALS_FOLDER

    if not os.path.exists(folder):
        raise HTTPException(status_code=400, detail="Materials folder not found")

    results = []

    for file_name in os.listdir(folder):
        if not file_name.lower().endswith(".pdf"):
            continue

        file_path = os.path.join(folder, file_name)
        pages = extract_text_by_pages(file_path)

        if not pages:
            continue

        # MAP: ask each page separately
        chunk_answers = []
        citations = []

        for page_data in pages[:6]:
            context = page_data["text"][:1000]
            answer, _ = ask_groq(req.question, context)

            if "not found" not in answer.lower():
                chunk_answers.append(answer)

            citations.append({
                "page": page_data["page"],
                "excerpt": page_data["text"][:120]
            })

        # REDUCE: combine all page answers into one final answer
        if chunk_answers:
            combined = "\n\n".join(chunk_answers)
            final_answer, tokens = ask_groq(
                f"Synthesise these findings into one clear answer to: {req.question}",
                combined
            )
        else:
            final_answer = "Answer not found in this document."
            tokens = 0

        # Save result to DB
        db_file = db.query(UploadedFile).filter(
            UploadedFile.file_name == file_name
        ).first()

        if db_file:
            result_record = FileProcessingResult(
                file_id=db_file.id,
                result_type="qa",
                question=req.question,
                answer=final_answer,
                ai_model_used=GROQ_MODEL,
                tokens_used=tokens,
            )
            db.add(result_record)
            db.commit()

        results.append({
            "file": file_name,
            "answer": final_answer,
            "citations": citations,
            "tokens_used": tokens,
        })

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No PDF files found to query"
        )

    return {"question": req.question, "answers": results}


# ── 4. Summarise a document ───────────────────────────────────────────────────
@app.post("/api/v1/summarise")
def summarise(req: SummariseRequest, db: Session = Depends(get_db)):
    file_path = os.path.join(MATERIALS_FOLDER, req.file_name)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"File '{req.file_name}' not found"
        )

    text = extract_text_from_pdf(file_path, max_chars=6000)

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from this PDF"
        )

    summary, tokens = summarise_groq(text, req.style)

    # Save to DB
    db_file = db.query(UploadedFile).filter(
        UploadedFile.file_name == req.file_name
    ).first()

    if db_file:
        result_record = FileProcessingResult(
            file_id=db_file.id,
            result_type="summary",
            question=None,
            answer=summary,
            ai_model_used=GROQ_MODEL,
            tokens_used=tokens,
        )
        db.add(result_record)
        db.commit()

    return {
        "file_name": req.file_name,
        "style": req.style,
        "summary": summary,
        "tokens_used": tokens,
    }


# ── 5. Get all past results for a file ───────────────────────────────────────
@app.get("/api/v1/results/{file_name}")
def get_results(file_name: str, db: Session = Depends(get_db)):
    db_file = db.query(UploadedFile).filter(
        UploadedFile.file_name == file_name
    ).first()

    if not db_file:
        raise HTTPException(
            status_code=404,
            detail=f"File '{file_name}' not found in database"
        )

    results = (
        db.query(FileProcessingResult)
        .filter(FileProcessingResult.file_id == db_file.id)
        .order_by(FileProcessingResult.created_at.desc())
        .all()
    )

    return {
        "file_name": file_name,
        "category": db_file.category,
        "result_count": len(results),
        "results": [
            {
                "type":          r.result_type,
                "question":      r.question,
                "answer":        r.answer,
                "ai_model_used": r.ai_model_used,
                "tokens_used":   r.tokens_used,
                "created_at":    r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ]
    }