# AI-Powered Customer Complaint Management System

A pharmaceutical Quality Management System for handling customer complaints from
intake through investigation, root cause, CAPA, QA review and closure — built
around an **AI-first intake** model where complaints are described in natural
language or uploaded as documents rather than typed into a form.

> **AI outputs in this system are recommendations for qualified QA review.**
> They are never confirmed root causes or regulatory determinations.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 · Vite 8 · TypeScript · Redux Toolkit + RTK Query |
| Styling | Tailwind CSS v4 · Google Inter |
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic |
| AI agent | LangGraph 1.2 |
| Database | PostgreSQL 17 |
| Providers | Gemini (free tier, primary) · OpenAI `gpt-5-nano` (fallback) · mock (tests) |

## Architecture: one contract, three consumers

The single most important property of this codebase is that the complaint shape
is defined **once**, in Python, and flows outward by generation:

```
backend/app/schemas/complaint.py
        │
        ├─────────────> SQLAlchemy models        (what the database stores)
        ├─────────────> LangGraph output schema  (what the AI may return)
        └─ OpenAPI ───> frontend/src/types/api.ts (what the UI consumes)
                                                   ^ GENERATED, never hand-edited
```

Because the AI binds to the same enums the database enforces, the model
physically cannot return a value that fails to store. Because the frontend types
are generated, they cannot drift from the backend. CI fails the build if the
committed types differ from a fresh generation.

---

## Quick start

**Prerequisites:** Docker Desktop running, Python 3.12+, Node 22+.

```bash
# 1. Configuration
cp .env.example .env          # works as-is for local development

# 2. Database
docker compose up -d          # Postgres on :5432, Adminer on :8080

# 3. Backend
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/uvicorn app.main:app --reload        # http://localhost:8000/docs

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev                                       # http://localhost:5173
```

## AI configuration

The system runs against three interchangeable providers, selected by
`AI_PROVIDER` in `.env`:

| Provider | Model | Cost | Use |
|---|---|---|---|
| `gemini` | `gemini-2.5-flash` | **Free tier**, text + image | Development and demo |
| `openai` | `gpt-5-nano` | $0.05/1M in · $0.40/1M out | Paid fallback |
| `mock` | recorded fixtures | **Free** | Tests and CI, always |

Get a free Gemini key at [aistudio.google.com](https://aistudio.google.com) — no
card required, and the free tier accepts image input, so scanned complaint photos
are handled without a separate OCR stack.

**Spend is governed, not trusted.** `app/ai/budget.py` records every call and
enforces `AI_BUDGET_USD` as a hard ceiling *before* contacting a provider, so a
runaway agent loop cannot drain the budget. Current spend is visible at
`GET /api/v1/ai/budget`.

## Verification

```bash
cd backend
./.venv/bin/ruff check . && ./.venv/bin/mypy app && ./.venv/bin/python -m pytest -q

cd ../frontend
npm run lint && npm run typecheck && npm run build

# contract drift
npm run gen:types && git diff --exit-code -- src/types/api.ts
```

## Project status

Built in phases; each lands as its own pull request.

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundation, domain contract, CI, subagents | ✅ Complete |
| 1 | Data model, JWT auth, RBAC, audit trail | ⏳ Next |
| 2 | Complaint CRUD, filters, workflow engine, seed data | ⏳ |
| 3 | LangGraph AI layer + cost governor | ⏳ |
| 4 | AI-first intake screen | ⏳ |
| 5 | Complaint list + investigation workspace | ⏳ |
| 6 | Dashboard + AI intelligence | ⏳ |
| 7 | Hardening and demo preparation | ⏳ |

## Complaint lifecycle

```
New → Under Review → Investigation → Root Cause Identified
    → CAPA Required → QA Review → Closed
```

Transitions are defined in one table and validated server-side; illegal
transitions are rejected with 409, unauthorised ones with 403.

## Roles

`admin` · `qa_manager` · `complaint_officer` · `investigator` · `viewer`
