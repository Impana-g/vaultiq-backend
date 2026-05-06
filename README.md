# VaultIQ Backend 🔐

> AI-powered Due Diligence document intelligence platform — classify, query, and summarise financial & legal PDFs using LLMs.

---

## What is VaultIQ?

VaultIQ is a FastAPI backend that automates the most time-consuming parts of due diligence:

- **Classifies** PDF documents into Financial, Legal, or General categories using a 3-strategy pipeline (LLM → Keywords → Filename)
- **Answers questions** across multiple documents using a Map-Reduce Q&A pattern with page-level citations
- **Summarises** documents in three styles: Executive, Bullet Points, or Detailed Analysis
- **Secures** all AI endpoints with JWT authentication

Built for M&A analysts, legal teams, and investors who need to process large document sets quickly.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| AI / LLM | Groq (llama-3.3-70b-versatile) |
| Database | SQLite (PostgreSQL-ready) |
| ORM | SQLAlchemy |
| Auth | JWT (python-jose) + bcrypt |
| PDF Parsing | PyPDF2 |
| Validation | Pydantic v2 |
| Server | Uvicorn |

---

## Project Structure

```
vaultiq-backend/
├── main.py               # FastAPI app + all core endpoints
├── models.py             # SQLAlchemy models (4 tables)
├── database.py           # DB engine + session
├── auth.py               # JWT logic + password hashing
├── schemas.py            # Pydantic request/response schemas
├── routers/
│   └── auth_router.py    # Auth endpoints (register, login, me)
├── mp_materials/         # Drop PDFs here for processing
├── requirements.txt
└── .env
```

---

## API Endpoints

### Auth
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Register a new user | ❌ |
| POST | `/api/v1/auth/login` | Login and get JWT token | ❌ |
| GET | `/api/v1/auth/me` | Get current user info | ✅ |

### Documents
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| POST | `/api/v1/dev/process` | Classify all PDFs in folder | ❌ |
| GET | `/api/v1/process/{session_id}/status` | Poll processing status | ❌ |
| POST | `/api/v1/ask` | Ask a question across all documents | ✅ |
| POST | `/api/v1/summarise` | Summarise a specific document | ❌ |
| GET | `/api/v1/results/{file_name}` | Get all past results for a file | ❌ |

---

## Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/Impana-g/vaultiq-backend.git
cd vaultiq-backend
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create `.env` file
```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=sqlite:///./vaultiq.db
MATERIALS_FOLDER=./mp_materials
SECRET_KEY=your_random_secret_key_minimum_32_chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Generate a secure `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Add PDFs
```bash
mkdir mp_materials
# Drop your PDF files into the mp_materials/ folder
```

### 5. Start the server
```bash
uvicorn main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for the interactive Swagger UI.

---

## How to Use

### Step 1 — Register & Login
```bash
# Register
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "yourname", "email": "you@example.com", "password": "yourpassword"}'

# Login → copy the access_token from response
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -d "username=yourname&password=yourpassword"
```

### Step 2 — Process Documents
```bash
curl -X POST http://127.0.0.1:8000/api/v1/dev/process
```

### Step 3 — Ask a Question (requires token)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ask \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the total revenue mentioned?"}'
```

### Step 4 — Summarise a Document
```bash
curl -X POST http://127.0.0.1:8000/api/v1/summarise \
  -H "Content-Type: application/json" \
  -d '{"file_name": "report.pdf", "style": "executive"}'
```

---

## Document Classification Pipeline

VaultIQ uses a 3-strategy fallback system to classify every document:

```
PDF Text Extracted
       │
       ▼
 [Strategy 1] LLM Classification (Groq)
       │ if LLM unavailable or fails
       ▼
 [Strategy 2] Keyword Scoring
       │ financial keywords vs legal keywords
       │ if text too short
       ▼
 [Strategy 3] Filename Matching
       │
       ▼
  financial / legal / general
```

---

## Map-Reduce Q&A Architecture

For each question asked across documents:

```
Question
   │
   ▼ (for each PDF)
[MAP] Ask each page separately → collect non-empty answers
   │
   ▼
[REDUCE] Synthesise all page answers into one final answer
   │
   ▼
Return answer + page citations
```

---

## Database Schema

```
users                    upload_sessions
─────────────────        ───────────────────────
id (PK)                  id (PK)
username (unique)        status
email (unique)           file_count
hashed_password          categorized_count
is_active                failed_count
created_at               created_at

uploaded_files           file_processing_results
──────────────────       ───────────────────────
id (PK)                  id (PK)
session_id (FK)          file_id (FK)
file_name                result_type
category                 question
error_message            answer
created_at               ai_model_used
                         tokens_used
                         created_at
```

---

## Pending / Roadmap

- [ ] Switch to PostgreSQL for production
- [ ] Unit tests (pytest)
- [ ] File upload endpoint (instead of folder-based)
- [ ] Rate limiting per user
- [ ] Frontend dashboard

---

## Author

Built by **Impana G** — MCA Student, REVA University  
GitHub: [@Impana-g](https://github.com/Impana-g)
