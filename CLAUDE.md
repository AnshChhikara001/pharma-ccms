# CCMS — Working Agreement

AI-powered Customer Complaint Management System for pharmaceutical manufacturing.

## The one rule that matters

**The complaint shape is defined once, in Python, and everything else is generated.**

```
backend/app/schemas/complaint.py   ← the ONLY hand-written definition
  └─ FastAPI OpenAPI
      └─ backend/openapi.json
          └─ frontend/src/types/api.ts   ← GENERATED. Never hand-edit.
```

If a type looks wrong in the frontend, the Pydantic schema is wrong. Fix it
there and run `npm run gen:types`. Never patch the generated file.

## Stack

React 19 + Vite 8 + Redux Toolkit · FastAPI + SQLAlchemy 2 + Alembic ·
PostgreSQL 17 (Docker) · LangGraph 1.2 · Inter.

## Commands

```bash
# Backend (from backend/)
./.venv/bin/uvicorn app.main:app --reload      # dev server :8000
./.venv/bin/python -m pytest -q                # tests
./.venv/bin/ruff check . && ./.venv/bin/mypy app
./.venv/bin/python -m scripts.export_openapi   # refresh the contract

# Frontend (from frontend/)
npm run dev            # :5173, proxies /api to :8000
npm run gen:types      # regenerate from backend/openapi.json
npm run build          # tsc --noEmit && vite build

# Database
docker compose up -d   # Postgres :5432, Adminer :8080
```

## Non-negotiables

1. **AI spend is governed.** Every model call goes through `app/ai/budget.py`,
   which enforces a hard cap *before* calling out. Never call a provider SDK
   directly. Every LangGraph invocation passes an explicit `recursion_limit`.
2. **Tests never hit a live model.** `tests/conftest.py` forces
   `AI_PROVIDER=mock` before the app is imported. CI sets it too. A test that
   can reach a live provider is a bug.
3. **AI output is advisory.** Assessments are recommendations for qualified QA
   review — never confirmed root causes or regulatory decisions. Every AI panel
   renders a visible disclaimer.
4. **Partial updates must be non-destructive.** Serialise `ComplaintUpdate` with
   `exclude_unset=True`. This is what lets "the batch number is BMX 240602"
   change one field and leave the rest alone. There is a regression test; do not
   weaken it.
5. **Never use passlib.** It is unmaintained and breaks against bcrypt ≥ 4.1.
   Use the `bcrypt` package directly.
6. **Tailwind v4 has no config file.** Configuration lives in the `@theme` block
   in `src/styles/index.css`. A `tailwind.config.js` would be silently ignored.
7. **Audit trail is automatic.** Written by SQLAlchemy event listeners, not by
   hand at call sites — so it cannot be forgotten.

## Subagents

Defined in `.claude/agents/`. Use them.

| Agent | When |
|---|---|
| `qa-verifier` | End of every phase. Nothing merges without its PASS. |
| `contract-guardian` | After any change to `app/schemas/` or an endpoint. |
| `pharma-domain-validator` | After touching enums, seed data, prompts or UI copy. |
| `ai-tool-smith` | Building or debugging LangGraph tools and prompts. |
| `seed-data-smith` | Generating or refreshing demo data. |
| `git-phase-manager` | Branching, committing, PRs, merges. |

## Workflow

One phase = one branch (`phase/<N>-<slug>`) = one PR. Conventional Commits.
Never push to `main` directly. Never merge on a red gate.
