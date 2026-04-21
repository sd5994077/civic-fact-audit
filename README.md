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

## Container Run (DB + API + Web)
1. Start everything:
   ```bash
   docker compose up -d --build
   ```
2. Run migrations:
   ```bash
   docker compose run --rm api alembic upgrade head
   ```
3. Seed example comparison data:
   ```bash
   docker compose run --rm api python -m app.scripts.seed_tx_us_senate_example
   ```
4. Ingest Texas 2026 roster snapshot:
   ```bash
   docker compose run --rm api python -m app.scripts.ingest_tx_2026_senate_roster
   ```
5. Ingest first Texas 2026 statement batch:
   ```bash
   docker compose run --rm api python -m app.scripts.ingest_tx_2026_statement_batch
   ```
6. Ingest second Texas 2026 statement batch (social/interview/debate):
   ```bash
   docker compose run --rm api python -m app.scripts.ingest_tx_2026_statement_batch_round2
   ```
7. Run Texas 2026 claim extraction batch:
   ```bash
   docker compose run --rm api python -m app.scripts.extract_tx_2026_claims_batch
   ```
8. Generate Texas 2026 evidence queue report:
   ```bash
   docker compose run --rm api python -m app.scripts.generate_tx_2026_evidence_queue_report
   ```
9. Attach first-pass Texas 2026 evidence sources for missing claims:
   ```bash
   docker compose run --rm api python -m app.scripts.attach_tx_2026_evidence_batch
   ```
10. Open:
   - API: `http://localhost:8000/health`
   - Web UI: `http://localhost:3001`

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
- Candidate race context (`election_cycle`, `race_stage`) and race-aware candidate listing endpoint (`GET /v1/candidates` filters).
- Texas 2026 U.S. Senate roster ingest script for repeatable race setup.
- Texas 2026 statement batch ingest script to seed traceable source-backed statement records.
- Texas 2026 second statement batch and batch claim extraction runner for repeatable intake progression.
- Evidence queue endpoint (`GET /v1/claims/evidence-queue`) and Texas queue report script for source-attachment triage.
- Bulk source attach endpoint (`POST /v1/claims/sources/bulk`) for reviewer batch operations.
- Texas 2026 evidence attachment batch script to reduce missing-source queue items.
- Scoring service with transparent numerators/denominators and formula versioning.
- Unit tests for score calculations and denominator policy behavior.

## Next Steps
- Implement SQLAlchemy models + Alembic migrations.
- Add claim extraction worker and source ingestion connectors.
- Add evaluation workflow and reviewer UI.
- Build frontend dashboard for claim transparency.
