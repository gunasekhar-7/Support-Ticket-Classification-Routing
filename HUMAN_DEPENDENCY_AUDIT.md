# Human Dependency Audit Report
## Support Ticket Classification & Routing System

*Generated: 2026-10-28 | Stack: Python 3.11 / FastAPI / DistilBERT / SQLite / Redis / Prometheus+Grafana*

---

## 1. PROJECT X-RAY (Plain English Summary)

**What this project actually is:**
A **FastAPI-based REST API** that classifies incoming support tickets using a **DistilBERT transformer model** (via Hugging Face `transformers` + PyTorch) and routes them to appropriate support teams with priority/SLA logic.

| Layer | Technology | Purpose |
|-------|------------|---------|
| **API Framework** | FastAPI 0.110+ (Python 3.11) | Async REST endpoints with OpenAPI docs |
| **ML Model** | DistilBERT (`transformers>=4.40` + `torch>=2.3`) | Ticket classification into 7 categories |
| **Database** | SQLAlchemy 2.0 + SQLite (dev) / PostgreSQL (prod) | Persistence for tickets, users, audit logs |
| **Cache/Queue** | Redis 7 + `slowapi` | Rate limiting, routing metrics, circuit breaker state |
| **Auth** | JWT (HS256) via `python-jose[cryptography]` | Stateless authentication with access/refresh tokens |
| **Observability** | Prometheus Client + Grafana | Metrics (`/metrics`), dashboards, alerting |
| **Model Storage** | S3 (`boto3`) or GCS (`google-cloud-storage`) | Optional: download model artifacts on startup |
| **Containerization** | Docker + Docker Compose | Multi-service deployment (API, Redis, Prometheus, Grafana) |
| **CI/CD** | GitHub Actions | Lint, type-check, test, load-test, deploy |

**No frontend** — this is a pure backend API service.

---

## 2. MISSING ENVIRONMENT VARIABLES & SECRETS (.env Audit)

The codebase uses **Pydantic Settings v2** with `.env` file support. You **already have a `.env` file** (32 lines). Below is the complete inventory of every variable the code expects, with what's missing or needs attention:

| Variable Name | What It Is | How to Get It | Where to Put It |
|---------------|------------|---------------|-----------------|
| `ENVIRONMENT` | App tier: `development` / `staging` / `production` | Choose one | `.env` line 1 |
| `DEBUG` | Enable debug mode | `true` or `false` | `.env` line 2 |
| `LOG_LEVEL` | Log verbosity | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `.env` line 3 |
| `LOG_FORMAT` | Log output format | `json` (prod) or `console` (dev) | `.env` line 4 |
| `HOST` | Bind address | `0.0.0.0` | `.env` line 5 |
| `PORT` | HTTP port | `8000` | `.env` line 6 |
| `WORKERS` | Uvicorn workers | `1` (dev), `4+` (prod) | `.env` line 7 |
| `API_PREFIX` | API version prefix | `/api/v1` | `.env` line 8 |
| `MODEL_PATH` | Local model directory | `models/distilbert` (relative to CWD) | `.env` line 9 |
| `BASELINE_MODEL_PATH` | Baseline model file | `models/baseline.joblib` | `.env` line 10 |
| `MODEL_DEVICE` | Torch device | `cpu`, `cuda`, or `mps` (Mac) | `.env` line 11 |
| `MAX_BATCH_SIZE` | Inference batch size | `32` (adjust for GPU memory) | `.env` line 12 |
| `INFERENCE_TIMEOUT` | Max inference wait (sec) | `30.0` | `.env` line 13 |
| **`MODEL_S3_BUCKET`** | S3 bucket for model artifacts | **AWS Console → S3 → Create bucket** | `.env` line 14 |
| **`MODEL_S3_KEY`** | S3 object key (path) | e.g., `models/distilbert-v1.tar.gz` | `.env` line 15 |
| **`MODEL_GCS_BUCKET`** | GCS bucket for model artifacts | **GCP Console → Cloud Storage → Create bucket** | `.env` line 16 |
| **`MODEL_GCS_PATH`** | GCS object path | e.g., `models/distilbert-v1.tar.gz` | `.env` line 17 |
| **`MODEL_CHECKSUM`** | SHA256 of model archive | `sha256sum distilbert.tar.gz` (see below) | `.env` line 18 |
| `MODEL_DOWNLOAD_TIMEOUT` | Download timeout (sec) | `300.0` | `.env` line 19 |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` (local) or `redis://redis:6379/0` (Docker) | `.env` line 20 |
| `REDIS_MAX_CONNECTIONS` | Redis connection pool size | `10` | `.env` line 21 |
| `DATABASE_URL` | SQLAlchemy DB URL | **See Database Setup below** | `.env` line 22 |
| `RATE_LIMIT_REQUESTS` | Requests per window | `100` | `.env` line 23 |
| `RATE_LIMIT_WINDOW` | Rate limit window (sec) | `60` | `.env` line 24 |
| `CORS_ORIGINS` | Allowed CORS origins | `["*"]` or `["https://yourdomain.com"]` | `.env` line 25 |
| **`JWT_SECRET_KEY`** | **CRITICAL: JWT signing key** | `openssl rand -base64 32` → **COPY OUTPUT** | `.env` line 26 |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` (don't change) | `.env` line 27 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL | `30` | `.env` line 28 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL | `7` | `.env` line 29 |
| `PII_REDACTION_ENABLED` | Enable PII scrubbing in logs | `true` | `.env` line 30 |
| `HEALTH_CHECK_INTERVAL` | Health check interval (sec) | `30` | `.env` line 31 |
| `HEALTH_CHECK_TIMEOUT` | Health check timeout (sec) | `5.0` | `.env` line 32 |

#### ⚠️ Critical Secrets You MUST Generate

```bash
# 1. JWT Secret (run ONCE, save output)
openssl rand -base64 32
# Example output: "k8s9dJf7sK2mN4pQ6rT8vW0xY2zA4bC6dE8fG0hI2jK4lM6nO8pQ0rS2tU4vW6xY8z"

# 2. Model Checksum (run AFTER you have model.tar.gz)
sha256sum models/distilbert.tar.gz
# Example output: "a1b2c3d4e5f6...  models/distilbert.tar.gz"
```

> **Your current `.env` line 26 has a JWT secret** (`hFCOWDf04+dtkCHHl8X4u2mzrLu8jQcl9Z74IhB+ujI=`). **Regenerate it** for production use — the default in code is `"dev-secret-change-in-production"`.

---

## 3. EXTERNAL DASHBOARD & CLOUD CONFIGURATIONS

### A. Database Setup — **REQUIRED CHOICE**

| Option | Setup Required | When to Use |
|--------|----------------|-------------|
| **SQLite (current)** | **Zero** — `sqlite+aiosqlite:///./dev.db` creates file automatically | Local dev only |
| **PostgreSQL (production)** | **Manual** — see below | Production deployment |

**PostgreSQL Setup (if needed):**
```bash
# 1. Provision a PostgreSQL instance (options:)
#    - Local: `winget install PostgreSQL.PostgreSQL` (Windows) / `brew install postgresql` (Mac)
#    - Cloud: Supabase, Neon, Railway, AWS RDS, GCP Cloud SQL, Azure Database
# 2. Create database & user:
psql -U postgres -c "CREATE DATABASE ticket_classifier;"
psql -U postgres -c "CREATE USER ticket_user WITH PASSWORD 'secure_password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE ticket_classifier TO ticket_user;"
# 3. Update .env:
DATABASE_URL=postgresql+asyncpg://ticket_user:secure_password@host:5432/ticket_classifier
```
- **Tables are auto-created** on startup via `Base.metadata.create_all()` (no manual migrations needed)
- CI/CD workflow expects PostgreSQL on port 5432 for integration tests

### B. Redis — **REQUIRED (provided by docker-compose)**
- **Docker Compose handles this** (`redis:7-alpine` service on port 6379)
- **Local without Docker:** Install Redis (`winget install Redis` / `brew install redis` / `apt install redis`)
- Verify: `redis-cli ping` → should return `PONG`

### C. Model Artifacts (DistilBERT) — **OPTIONAL but RECOMMENDED**

**Without this: API runs with dummy keyword-based classifier (low accuracy)**

| Step | Action |
|------|--------|
| 1. Train/Obtain Model | Fine-tune DistilBERT on your ticket data OR download pre-trained from HuggingFace Hub |
| 2. Package Model | `tar -czf distilbert.tar.gz models/distilbert/` (must contain `config.json`, `pytorch_model.bin`, `tokenizer.json`, etc.) |
| 3. Compute Checksum | `sha256sum distilbert.tar.gz` → copy hash to `MODEL_CHECKSUM` |
| 4. Upload to Cloud | **AWS S3:** `aws s3 cp distilbert.tar.gz s3://your-bucket/models/`<br>**GCP GCS:** `gsutil cp distilbert.tar.gz gs://your-bucket/models/` |
| 5. Set IAM Permissions | **AWS:** Bucket policy allowing `s3:GetObject` from your EC2/ECS role<br>**GCP:** Storage Object Viewer role on bucket |
| 6. Update .env | Fill `MODEL_S3_BUCKET`, `MODEL_S3_KEY`, `MODEL_CHECKSUM` (or GCS equivalents) |

### D. Authentication / OAuth
- **No external OAuth providers** (Clerk, Auth0, Firebase Auth, Google Login) — uses **local JWT with in-memory user store**
- **Default users (dev only):**
  - `admin` / any password → `admin` role
  - `service` / any password → `service` role
- **For production:** Replace in-memory store in `app/auth/jwt.py` with real database users + bcrypt password hashing

### E. CORS / Whitelisting
- **Default:** `CORS_ORIGINS=["*"]` (allows all origins)
- **Production:** Change to `CORS_ORIGINS=["https://your-frontend.com"]` in `.env`

### F. Billing / Quotas — **NONE REQUIRED**
- No OpenAI, Anthropic, AWS Bedrock, or paid API calls
- All ML runs locally via PyTorch (CPU by default)
- Only costs: Cloud hosting (EC2, Cloud Run, etc.), S3/GCS storage for model artifacts

---

## 4. LOCAL SYSTEM PREREQUISITES

| Tool | Version | Verify Command | Install Command (Windows) |
|------|---------|----------------|---------------------------|
| **Python** | 3.11+ | `python --version` | `winget install Python.Python.3.11` |
| **pip** | latest | `pip --version` | Included with Python |
| **Docker Desktop** | 4.x+ | `docker --version` && `docker compose version` | `winget install Docker.DockerDesktop` |
| **Git** | 2.x+ | `git --version` | `winget install Git.Git` |
| **Redis** | 7.x+ | `redis-cli ping` | `winget install Redis` (or use Docker) |
| **PostgreSQL** | 15+ (optional) | `psql --version` | `winget install PostgreSQL.PostgreSQL` |

**For GPU Acceleration (optional):**
| Tool | Version | Verify Command |
|------|---------|----------------|
| **NVIDIA Driver** | 535+ | `nvidia-smi` |
| **CUDA Toolkit** | 12.1+ | `nvcc --version` |
| **PyTorch CUDA** | Match CUDA | `python -c "import torch; print(torch.cuda.is_available())"` |

**Quick Verification Script:**
```powershell
# Run in PowerShell
python --version
pip --version
docker --version
docker compose version
redis-cli ping
# If PostgreSQL: psql --version
```

---

## 5. EXACT IGNITION SEQUENCE

### Option A: Docker Compose (Easiest — Includes Redis, Prometheus, Grafana)

```powershell
cd "C:\Projects\Support Ticket Classification & Routing"

# 1. Ensure .env exists with REAL JWT secret (see Section 2)
#    EDIT: Set JWT_SECRET_KEY = output of `openssl rand -base64 32`

# 2. Start all services
docker compose up --build -d

# 3. Verify health
curl http://localhost:8000/api/v1/health/live
# Should return: {"status":"alive","timestamp":...,"version":"0.1.0","environment":"development"}

# 4. Check logs
docker compose logs -f api

# 5. Access monitoring
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin/admin)
```

### Option B: Local Development (No Docker)

```powershell
cd "C:\Projects\Support Ticket Classification & Routing"

# 1. Ensure .env exists (see Section 2)
#    Ensure Redis is running locally: redis-cli ping

# 2. Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install --upgrade pip
pip install -e ".[dev]"

# 4. Initialize database (auto-creates tables)
python -c "import asyncio; from app.db import init_db; asyncio.run(init_db())"

# 5. Start API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. In another terminal, verify
curl http://localhost:8000/api/v1/health/live
```

### Option C: Run Tests (Verify Everything Works)

```powershell
cd "C:\Projects\Support Ticket Classification & Routing"
.\.venv\Scripts\Activate.ps1
pytest tests -v --tb=short
# Should show: 24 passed
```

### Option D: Load Testing (After API is Running)

```powershell
# Locust (Python-based)
cd tests\load
locust -f locustfile.py --host=http://localhost:8000

# k6 (Separate install required)
k6 run tests\load\k6-script.js -e BASE_URL=http://localhost:8000
```

---

## 🚨 COMMON FAILURE POINTS & FIXES

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'app'` | Not installed in editable mode | `pip install -e .` |
| `sqlalchemy.exc.OperationalError: database is locked` | SQLite + concurrent workers | Use `WORKERS=1` or switch to PostgreSQL |
| `redis.exceptions.ConnectionError` | Redis not running | `docker compose up -d redis` or start local Redis |
| `JWT_SECRET_KEY` validation error | Using default dev secret in production | Generate real secret: `openssl rand -base64 32` |
| `ModelDownloadError: S3 download failed` | Missing AWS credentials | `aws configure` or set `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env vars |
| `CUDA out of memory` | Batch size too large for GPU | Reduce `MAX_BATCH_SIZE` in `.env` (try 8, 16) |
| `port 8000 already in use` | Another process on 8000 | `netstat -ano | findstr :8000` → `taskkill /PID <pid> /F` |

---

## 📞 NEED HELP?

Run this and paste output:
```powershell
cd "C:\Projects\Support Ticket Classification & Routing"
.\.venv\Scripts\Activate.ps1
python -c "from app.core.config import get_settings; s=get_settings(); print(f'ENV={s.environment} DB={s.database_url} REDIS={s.redis_url} JWT_SET={bool(s.jwt_secret_key != \"dev-secret-change-in-production\")}')"
pytest tests -v --tb=short 2>&1 | tail -30
```

This will show your exact config state and any test failures.

---

## Appendix: Project File Inventory

### Configuration Files
- `pyproject.toml` — Python dependencies, build config, linting rules
- `docker-compose.yml` — Multi-service orchestration (API, Redis, Prometheus, Grafana)
- `Dockerfile` — API container definition (CPU-only PyTorch)
- `.env` — Environment variables (32 lines)
- `.github/workflows/ci-cd.yml` — GitHub Actions pipeline

### Application Code Structure
```
app/
├── main.py                 # FastAPI app factory, lifespan, middleware
├── __init__.py
├── auth/                   # JWT authentication (access/refresh tokens, RBAC)
│   ├── jwt.py
│   ├── dependencies.py
│   ├── router.py
│   └── __init__.py
├── core/                   # Configuration, logging, circuit breaker, metrics, rate limiter
│   ├── config.py
│   ├── logging.py
│   ├── circuit_breaker.py
│   ├── metrics.py
│   ├── rate_limiter.py
│   └── __init__.py
├── db/                     # SQLAlchemy models & async session
│   ├── models.py
│   ├── session.py
│   └── __init__.py
├── middleware/             # Request ID, error handling, security (body size, sanitization)
│   ├── errors.py
│   ├── request_id.py
│   ├── security.py
│   └── __init__.py
├── routes/
│   ├── v1/                 # Legacy API endpoints
│   │   ├── classify.py
│   │   ├── health.py
│   │   ├── metrics.py
│   │   └── __init__.py
│   ├── v2/                 # Enhanced API endpoints
│   │   ├── classify.py
│   │   ├── health.py
│   │   ├── metrics.py
│   │   └── __init__.py
│   └── __init__.py
├── schemas/
│   ├── ticket.py           # Pydantic models for requests/responses
│   └── __init__.py
└── services/
    ├── inference.py        # DistilBERT async inference with circuit breaker
    ├── routing.py          # Team/priority/SLA routing logic
    └── __init__.py
```

### Monitoring
- `monitoring/prometheus.yml` — Prometheus scrape config
- `monitoring/grafana/dashboards/ticket-classifier.json` — Grafana dashboard
- `monitoring/grafana/datasources/prometheus.yml` — Grafana datasource config

### Tests
- `tests/test_api.py` — API integration tests (17 tests)
- `tests/test_services.py` — Service unit tests (7 tests)
- `tests/conftest.py` — Pytest fixtures
- `tests/load/locustfile.py` — Locust load test scenarios
- `tests/load/k6-script.js` — k6 load test script

### Documentation
- `README.md` — Quick start guide
- `HUMAN_DEPENDENCY_AUDIT.md` — This file