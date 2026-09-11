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
| 1 | Data model, JWT auth, RBAC, audit trail | ✅ Complete |
| 2 | Complaint CRUD, filters, workflow engine, seed data | ✅ Complete |
| 3 | LangGraph AI layer + cost governor | ⏳ Next |
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

## Roles and demo accounts

Run `python -m seeds.run` to create one account per role. All share the password
`Demo@12345` — acceptable for a demo system, and nowhere near acceptable for production.

| Role | Email | May do |
|---|---|---|
| `admin` | admin@pharmaco.com | Everything, including user management |
| `qa_manager` | qa.manager@pharmaco.com | Approve root causes and CAPAs; **only role besides admin that can close a complaint** |
| `complaint_officer` | complaint.officer@pharmaco.com | Log and triage complaints, run AI extraction, assign investigators |
| `investigator` | investigator@pharmaco.com | Investigate and **propose** root causes — cannot approve their own findings |
| `viewer` | viewer@pharmaco.com | Read-only |

Segregation of duties is enforced in the API, not just the UI: the person who
performs the work is never the person who approves it.

## Audit trail

Every change to a complaint, investigation, root cause, CAPA or user is recorded
automatically by SQLAlchemy event listeners — **no endpoint writes audit entries**,
so none can forget to. Password hashes are redacted, and entries survive deletion
of the row they describe.

## Complaints API

`/api/v1/complaints` is a full CRUD surface plus the workflow:

| | |
|---|---|
| `GET /complaints` | Search — free text, status/severity/priority/type/source (repeatable, OR'd), customer/product/batch substring, unassigned-only, overdue-only, a date range, six sort orders, paginated |
| `POST /complaints` | Log a complaint. Allocates its reference code (`CMP-2026-0042`) and opens the timeline |
| `GET /complaints/{id}` · `PATCH /complaints/{id}` · `DELETE /complaints/{id}` | `PATCH` is a true partial update (`exclude_unset=True`); `DELETE` only works while a complaint is still `new` — anything further along is closed with a reason instead |
| `POST /complaints/{id}/transition` · `GET /complaints/{id}/transitions` | Move the complaint and read its timeline |
| `GET /meta/workflow` | The transition table itself, so the UI's buttons are derived from the same rule the server enforces, never a second copy of it |

`batch_number` is the recall question — every complaint logged against a given
lot, across every customer that reported it. Two things happen automatically on
every write: the free-text customer/product/batch a complainant gave are
resolved to reference-data rows when a confident match exists (the text is kept
either way, so nothing is lost when nothing matches yet), and the merged result
is re-validated against the full contract, so a partial edit can never leave a
complaint in a state the create path would have rejected.

Demo data — ten customers, twelve products, twenty-six batches and twenty-six
complaints spanning every lifecycle status — loads via `python -m seeds.run`,
safe to re-run.
