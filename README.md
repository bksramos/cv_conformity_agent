# 🤖 CV Conformity Agent

> Multi-agent AI system for automated CV × Job Description conformity analysis.  
> Built with **LangGraph**, **Llama 3** (local), **FastAPI** and **Streamlit**.

---

## 📋 Overview

CV Conformity Agent automatically matches candidate resumes against job descriptions, delivering a bilingual verdict (PT/EN) with a 0–100 score and structured feedback across skills, experience, education, and languages.

The system scrapes job descriptions daily from public sources, structures them via LLM, and exposes two analysis modes:
- **1×1** — one CV against one specific JD
- **Batch Match** — one CV ranked against all JDs in the database

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (LangGraph)               │
│  check_cache → extract_cv → extract_jd → validate       │
│             → generate_report → save_result              │
└─────────────────────────────────────────────────────────┘
         │                              │
   ┌─────┴──────┐                ┌──────┴─────┐
   │ CV Agent   │                │  JD Agent  │
   │ PDF→struct │                │ DB / text  │
   └─────┬──────┘                └──────┬─────┘
         └──────────────┬───────────────┘
                        │
              ┌─────────┴──────────┐
              │ Conformity         │
              │ Validator          │
              │ (deterministic)    │
              └─────────┬──────────┘
                        │
              ┌─────────┴──────────┐
              │ Report Generator   │
              │ (LLM — PT + EN)    │
              └─────────┬──────────┘
                        │
              ┌─────────┴──────────┐
              │ FastAPI + Streamlit │
              └────────────────────┘

JD SCRAPER (APScheduler — daily)
  Gupy API → RemoteOK API → Normalizer → Deduplicator → LLM → PostgreSQL
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| LLM | Llama 3.1:8b via Ollama (local, GPU) |
| Multi-Agent | LangGraph |
| API | FastAPI |
| UI | Streamlit |
| Database | PostgreSQL 16 |
| Cache L1/L2 | Memory + Redis |
| Vector Store | ChromaDB |
| Scheduler | APScheduler |
| PDF Extraction | PyMuPDF + pdfplumber |

---

## ⚙️ Requirements

- Python 3.12+
- Docker + Docker Compose
- [Ollama](https://ollama.com) installed natively on Windows (for GPU support)
- NVIDIA GPU recommended (RTX 3060+ with 6GB+ VRAM)

---

## 🚀 Setup

### 1. Clone and create virtual environment
```bash
git clone <repo-url>
cd cv_conformity_agent
python -m venv venv
source venv/Scripts/activate  # Windows/WSL
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your settings
```

Key variables in `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://cva_user:cva_pass@localhost:5432/cv_conformity
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://<windows-ip>:11434   # get with: ip route show | grep default
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TIMEOUT=300
```

### 3. Install dependencies
```bash
bash update_deps.sh
```

### 4. Start infrastructure
```bash
docker compose up -d
```

### 5. Initialize database
```bash
python -c "import asyncio; from database.connection import init_db; asyncio.run(init_db())"
```

### 6. Start Ollama (Windows PowerShell — Admin)
```powershell
$env:OLLAMA_HOST = "0.0.0.0:11434"
ollama serve
```

### 7. Pull the model (first time only)
```powershell
ollama pull llama3.1:8b
```

### 8. Update Ollama IP (run every time Windows restarts)
```bash
bash update_ollama_ip.sh
```

### 9. Validate environment
```bash
python bootstrap.py
```
Expected output: all services ✅

---

## 📦 Project Structure

```
cv_conformity_agent/
│
├── agents/
│   ├── orchestrator.py          # LangGraph StateGraph
│   ├── cv_extraction_agent.py   # PDF → CVProfile
│   ├── jd_extraction_agent.py   # text → JobDescription
│   ├── conformity_validator.py  # CV × JD scoring
│   └── report_generator.py      # Bilingual report (LLM)
│
├── scraper/
│   ├── runner.py                # Scraping pipeline orchestrator
│   ├── scheduler.py             # APScheduler (daily)
│   ├── base_scraper.py          # Abstract base class
│   ├── normalizer.py            # Text normalization
│   ├── deduplicator.py          # Duplicate prevention
│   └── sources/
│       ├── gupy_scraper.py      # Gupy public API
│       └── remoteok_scraper.py  # Remote OK JSON API
│
├── extractors/
│   ├── pdf_extractor.py         # PyMuPDF + pdfplumber
│   ├── text_cleaner.py          # PDF artifact removal
│   └── section_detector.py      # CV section labeling
│
├── validators/
│   ├── skills_validator.py      # Hard skills (exact/partial/inferred)
│   ├── experience_validator.py  # Years + seniority
│   ├── education_validator.py   # Degree + certifications
│   └── language_validator.py    # Languages + proficiency
│
├── scoring/
│   └── matching_score.py        # Weighted score (0–100)
│
├── cache/
│   ├── validation_cache.py      # L1 (memory) + L2 (Redis)
│   └── embedding_cache.py       # ChromaDB vector store
│
├── models/
│   ├── cv_model.py              # CVProfile Pydantic model
│   ├── jd_model.py              # JobDescription Pydantic model
│   ├── conformity_result.py     # ConformityResult Pydantic model
│   ├── verdict.py               # Enums (Verdict, Seniority, etc.)
│   └── agent_state.py           # LangGraph state schema
│
├── api/
│   ├── main.py                  # FastAPI app
│   ├── schemas.py               # Request/Response schemas
│   ├── dependencies.py          # DI (orchestrator singleton)
│   └── routes/
│       ├── analyze.py           # POST /analyze, /analyze/batch
│       ├── jobs.py              # GET /jobs
│       ├── results.py           # GET /results/{cv_hash}
│       └── health.py            # GET /health
│
├── database/
│   ├── connection.py            # SQLAlchemy async engine
│   ├── models.py                # ORM models
│   └── repositories/
│       ├── jd_repository.py
│       └── result_repository.py
│
├── config/
│   ├── settings.py              # Pydantic settings (from .env)
│   ├── feature_flags.py         # Feature toggles
│   └── prompts/
│       ├── cv_extraction.py
│       ├── jd_extraction.py
│       └── report.py
│
├── ui/
│   └── app.py                   # Streamlit (4 pages)
│
├── tests/
│   ├── conftest.py
│   ├── test_scraper.py
│   ├── test_jd_extraction.py
│   └── test_cv_extraction.py
│
├── bootstrap.py                 # Environment health check
├── run_scraper.py               # Manual scraper trigger
├── run_match.py                 # CLI: 1 CV × 1 JD
├── run_batch_match.py           # CLI: 1 CV × N JDs
├── update_ollama_ip.sh          # Update Ollama IP in .env
├── update_deps.sh               # Compile requirements.in → requirements.txt
├── docker-compose.yml
├── requirements.in
├── requirements.txt
└── .env.example
```

---

## 🔄 Daily Workflow

```bash
# 1. Windows PowerShell — start Ollama with GPU
$env:OLLAMA_HOST = "0.0.0.0:11434"
ollama serve

# 2. WSL — update IP and start services
bash update_ollama_ip.sh
docker compose up -d
python bootstrap.py        # confirm all green

# 3. Start API and UI (two terminals)
make api                   # http://localhost:8000/docs
make ui                    # http://localhost:8501
```

---

## 🎯 Usage

### Web UI (Streamlit)
Access `http://localhost:8501` and use the 4 pages:

| Page | Description |
|---|---|
| 🔍 **Análise 1×1** | Upload CV + select/paste JD → full bilingual verdict |
| 🏆 **Batch Match** | Upload CV → ranked list of best matching jobs from DB |
| 📋 **Vagas Disponíveis** | Browse all scraped JDs with domain/seniority filters |
| ❤️ **Health** | Real-time status of all services |

### CLI
```bash
# Scrape jobs manually
python run_scraper.py --source gupy --limit 5

# Analyze 1 CV × 1 JD (by JD UUID from DB)
python run_match.py curriculo.pdf --jd-id <uuid>

# Analyze 1 CV × 1 JD (by text)
python run_match.py curriculo.pdf --jd-text "Dev Python Sênior. Req: Python, FastAPI, Docker."

# Batch match: rank all jobs in DB for this CV
python run_batch_match.py curriculo.pdf --top 10 --domain TECH --seniority SENIOR
```

### API (REST)
Full docs at `http://localhost:8000/docs`

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Analyze 1×1
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "pdf=@curriculo.pdf" \
  -F "jd_text=Dev Python Sênior. Req: Python, FastAPI."

# List jobs
curl "http://localhost:8000/api/v1/jobs?domain=TECH&seniority=SENIOR&limit=20"
```

---

## 📊 Scoring Model

| Dimension | Weight | Description |
|---|---|---|
| 🔧 Hard Skills | 40% | Exact / partial / inferred match against required + desired skills |
| ⏱ Experience | 30% | Total years + seniority level alignment |
| 🎓 Education | 15% | Academic degree + certifications |
| 🌐 Languages | 10% | Required languages + proficiency level |
| 🤝 Soft Skills | 5% | Mentioned soft skills (Phase 2) |

### Verdict Thresholds
| Score | Verdict |
|---|---|
| ≥ 70 | ✅ APROVADO |
| 50–69 | ⚠️ APROVADO_COM_RESSALVAS |
| < 50 | ❌ REPROVADO |

> **Absolute blocker**: if `ENFORCE_REQUIRED_SKILLS=True` and any mandatory skill is missing, verdict is REPROVADO regardless of score.

---

## ⚙️ Feature Flags

Key flags in `config/feature_flags.py`:

```python
ENFORCE_REQUIRED_SKILLS      = True   # missing required skill = instant REPROVADO
ALLOW_PARTIAL_SKILL_MATCH    = True   # correlated tech counts as 50% match
INFER_SKILLS_FROM_EXPERIENCE = True   # skills mentioned in exp descriptions count
VALIDATE_SOFT_SKILLS         = False  # Phase 2
USE_DOMAIN_SPECIALIST_AGENT  = False  # Phase 2
GENERATE_BILINGUAL_REPORT    = True
USE_VALIDATION_CACHE         = True
CACHE_TTL_SECONDS            = 86400  # 24h
```

---

## 🧪 Tests

```bash
pytest tests/ -v
pytest tests/test_scraper.py -v
pytest tests/test_cv_extraction.py -v
pytest tests/test_jd_extraction.py -v
```

---

## 🗺️ Roadmap

- [x] **Phase 0** — Infrastructure (Docker, PostgreSQL, Redis, ChromaDB)
- [x] **Phase 1** — JD Scraper (Gupy + RemoteOK + daily scheduler)
- [x] **Phase 2** — CV Extraction Pipeline (PDF → CVProfile via Llama 3)
- [x] **Phase 3** — Conformity Core (validators + scoring + bilingual report)
- [x] **Phase 4** — LangGraph Orchestration + Cache (L1/L2 + batch match)
- [x] **Phase 5** — FastAPI + Streamlit UI
- [ ] **Phase 6** — Ground Truth & Quality Metrics
- [ ] **Phase 7** — Domain Specialist Sub-Agents (Tech / Data / Business / Creative)
