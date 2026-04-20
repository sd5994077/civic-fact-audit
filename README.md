# Civic Fact Audit

A standalone project to track political candidate claims, verify them against credible evidence, and publish transparent fact-consistency scores.

> This project is intentionally separate from `realty-ai-crm`.

## Project Goals
- Collect candidate statements and extract factual claims.
- Verify claims with primary and independent sources.
- Publish transparent scoring and source citations.
- Keep AI in a supporting role (extraction/summarization), not final truth authority.

## Tech Stack (MVP)
- **Backend:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL
- **Frontend:** Next.js (planned)
- **Worker:** Python scripts / cron jobs
- **AI:** OpenAI API for claim extraction and evidence summarization

## Quick Start
1. Copy env file:
   ```bash
   cp .env.example .env
   ```
2. Start local services:
   ```bash
   docker compose up -d db
   ```
3. Create Python environment and install deps:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run API:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
5. Run migrations:
   ```bash
   alembic upgrade head
   ```
6. Open health endpoint:
   - `http://localhost:8000/health`

## Container Run (API + DB)
```bash
docker compose up --build api db
```

## Recommended First Codex CLI Prompt
Use this as your first line in Codex CLI:

```text
Create a production-ready FastAPI + Postgres MVP for this repo using README.md, PLAN.md, and docs/SCORING.md as the source of truth.
```

## Repository Layout
```text
civic-fact-audit/
├── AGENTS.md
├── README.md
├── ROADMAP.md
├── PLAN.md
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── core/config.py
│       ├── models/
│       ├── schemas/
│       ├── services/
│       └── api/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   └── SCORING.md
└── scripts/
    └── bootstrap.sh
```

## What’s Included Right Now
- FastAPI MVP with versioned `v1` routes for candidates, statements, claims, evidence, evaluations, and scores.
- Postgres schema + Alembic migration for the MVP entities.
- Structured error responses across endpoints.
- Scoring service with transparent numerators/denominators and formula versioning.
- Unit tests for score calculations and denominator policy behavior.

## Next Steps
- Implement SQLAlchemy models + Alembic migrations.
- Add claim extraction worker and source ingestion connectors.
- Add evaluation workflow and reviewer UI.
- Build frontend dashboard for claim transparency.
