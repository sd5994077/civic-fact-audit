# Civic Fact Audit

A standalone project to track political candidate claims, verify them against credible evidence, and publish transparent fact-consistency scores.

> This project is intentionally separate from `realty-ai-crm`.

## Project Goals
- Collect candidate statements and extract factual claims.
- Verify claims with primary and independent sources.
- Publish transparent scoring and source citations.
- Keep AI in a supporting role (extraction/summarization), not final truth authority.

## Verification Model
- Candidate-controlled channels can be used to capture what was said.
- Factual verdicts must rely on verification sources, not campaign content alone.
- Published fact reviews should be human reviewed and citation-backed.
- Attached sources are labeled as candidate-originated or verification-originated in the API/UI.
- See [VERIFICATION_POLICY.md](docs/VERIFICATION_POLICY.md).
- See [MODERATION_POLICY.md](docs/MODERATION_POLICY.md).

## Tech Stack
- **Backend:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL
- **Frontend:** HTML/CSS/JS admin console at `/admin/`
- **Worker:** Background job thread with queue + retry logic
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
   python -m venv backend/.venv
   source backend/.venv/bin/activate
   pip install -r backend/requirements.txt
   ```
4. Run API from repository root:
   ```bash
   uvicorn app.main:app --reload --port 8000 --app-dir backend
   ```
5. Run migrations from repository root:
   ```bash
   alembic -c backend/alembic.ini upgrade head
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
3. Bootstrap admin account for authenticated adjudication:
   ```bash
   docker compose run --rm api python -m app.scripts.bootstrap_reviewer_user
   ```
   Creates or updates the account configured by `REVIEWER_BOOTSTRAP_*` env vars (default role: `admin`).
   To create a second account for dual-control approvals:
   ```bash
   docker compose run --rm api python -m app.scripts.create_reviewer \
     --email approver@local --password "..." --name "Approver" --role reviewer
   ```
4. Seed example comparison data:
   ```bash
   docker compose run --rm api python -m app.scripts.seed_tx_us_senate_example
   ```
5. Ingest Texas 2026 roster snapshot:
   ```bash
   docker compose run --rm api python -m app.scripts.ingest_tx_2026_senate_roster
   ```
6. Ingest first Texas 2026 statement batch:
   ```bash
   docker compose run --rm api python -m app.scripts.ingest_tx_2026_statement_batch
   ```
7. Ingest second Texas 2026 statement batch (social/interview/debate):
   ```bash
   docker compose run --rm api python -m app.scripts.ingest_tx_2026_statement_batch_round2
   ```
8. Ingest third Texas 2026 statement batch (narrower factual claims from official candidate pages):
   ```bash
   docker compose run --rm api python -m app.scripts.ingest_tx_2026_statement_batch_round3
   ```
9. Run Texas 2026 claim extraction batch:
   ```bash
   docker compose run --rm api python -m app.scripts.extract_tx_2026_claims_batch
   ```
10. Generate Texas 2026 evidence queue report:
    ```bash
    docker compose run --rm api python -m app.scripts.generate_tx_2026_evidence_queue_report
    ```
11. Attach first-pass Texas 2026 evidence sources for missing claims:
    ```bash
    docker compose run --rm api python -m app.scripts.attach_tx_2026_evidence_batch
    ```
12. Generate the Texas 2026 human review queue report:
    ```bash
    docker compose run --rm api python -m app.scripts.generate_tx_2026_review_queue_report
    ```
13. Backfill Texas 2026 claim reviewability metadata so slogans stay out of the review pipeline:
    ```bash
    docker compose run --rm api python -m app.scripts.backfill_tx_2026_claim_reviewability
    ```
14. Generate a balanced adjudication packet (1 claim per candidate by default):
    ```bash
    docker compose run --rm api python -m app.scripts.generate_tx_2026_adjudication_packet
    ```
15. Open:
    - API: `http://localhost:8000/health`
    - Admin console: `http://localhost:3001/admin/`

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
│   ├── alembic/          # Alembic migrations
│   ├── tests/            # pytest test suite
│   └── app/
│       ├── main.py
│       ├── core/         # config, errors, rate_limiter
│       ├── models/       # SQLAlchemy entities + enums
│       ├── schemas/      # Pydantic request/response schemas
│       ├── services/     # business logic
│       ├── scripts/      # bootstrap, ingest, seed scripts
│       └── api/v1/       # versioned route handlers
├── frontend/             # admin console (HTML/CSS/JS)
└── docs/
    ├── ARCHITECTURE.md
    ├── DATA_MODEL.md
    ├── SCORING.md
    └── MODERATION_POLICY.md
```

## What's Included Right Now
- FastAPI backend with versioned `v1` routes for candidates, statements, claims, evidence, evaluations, scores, and comparison.
- PostgreSQL schema with Alembic migrations (through `20260513_04`).
- Structured error responses across all endpoints.
- Reviewer authentication with signed bearer tokens (`POST /v1/auth/login`, `GET /v1/auth/me`).
- Dual-control approval tokens required for candidate mutations and sensitive overrides.
- Per-IP sliding-window rate limiting on all write endpoints with `Retry-After` headers.
- Admin console at `/admin/` — candidate lifecycle, review-queue adjudication, evidence triage, bulk source attach, proposal triage, publish/unpublish controls, audit-event inspection, and worker health monitoring.
- Background job worker with queue + retry logic and worker-health endpoint (`GET /v1/admin/jobs/worker-health`).
- Full-text claim search (`GET /v1/claims/search`) with PostgreSQL GIN index, ILIKE fallback, and relevance ranking.
- Public read-only API tier with API key authentication — admin-issued `X-API-Key` keys for external consumers; exposes published claim verdicts at `GET /v1/public/claims`.
- Admin API key management (`POST/GET/DELETE /v1/admin/api-keys`).
- Claim reviewability heuristics to exclude rhetorical slogans from evidence/review/compare workflows.
- Scoring service with transparent numerators/denominators and formula versioning.
- Moderation policy enforcement with boundary phrase detection.
- Audit event log for all admin/reviewer actions.
- Texas 2026 U.S. Senate race data: roster ingest, statement batches, evidence attachment, and adjudication packet scripts.
- 296 automated tests covering scoring, rate limiting, search, API key service, and core business logic.

## Next Steps
- Reviewer notification workflow (email or webhook on queue events and proposal triage).
- Source quality scoring automation.
- Caching and query optimization for high-traffic public endpoints.
- Expand to additional 2026 priority races.
