# Civic Fact Audit

A workbench for capturing political candidate claims, linking verification evidence, and publishing human-reviewed, citation-backed explanations. It is an internal-development project, not a production fact-checking service or a source of voting recommendations.

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
- **AI:** OpenAI review drafts (default `gpt-5-mini`) with optional Anthropic escalation; all output remains advisory to a human reviewer.

## Quick Start
1. Copy the environment template and set the local database port to the Compose host port:
   ```bash
   cp .env.example .env
   ```
   PowerShell: `Copy-Item .env.example .env`. In `.env`, use `POSTGRES_PORT=5433` when connecting to the Compose database from the host machine.
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

## AI Review Draft Pipeline

The Claim Workbench generates an AI-assisted draft evaluation via `POST /v1/claims/{claim_id}/review-draft`. The draft is advisory only — a human reviewer must confirm before any claim is published. Every generated draft is persisted (`GET /v1/claims/{claim_id}/review-drafts`) and can be diffed against the claim's latest submitted evaluation (`GET /v1/claims/{claim_id}/review-draft-diff`) to see whether the reviewer changed the verdict, confidence, rationale, or citation notes before submitting.

### Review-Draft Model Routing

| Route | Default model | Trigger | Notes |
|---|---|---|---|
| Primary | `gpt-5-mini` | Every eligible draft | Configurable with `OPENAI_REVIEW_DRAFT_MODEL` |
| Escalation | `claude-sonnet-4-6` | Only when the deterministic escalation guard requires it | Requires `ANTHROPIC_API_KEY` |
| Degraded mode | `claude-sonnet-4-6` | `CIVIC_AI_DEGRADED_MODE=true` | Bypasses OpenAI and disables green-lane output |

### Deterministic Safety Guardrail (`_enforce_green_lane`)
After every model call, the service applies a server-side override that forces `green_lane_ready=False` if the output contains any unsafe signal: non-supported verdict, non-empty warnings, non-empty missing_evidence, or any subclaim judgment that is not supported. The model cannot self-certify green-lane status.

### Circuit Breaker
Set `CIVIC_AI_DEGRADED_MODE=true` in `.env` and restart the API to:
- Bypass the primary OpenAI model entirely
- Route all claims directly to `claude-sonnet-4-6`
- Hard-disable green-lane auto-publishing for every response

Use this when the weekly regression health check detects a primary model regression.

### AI Scripts

**Weekly regression health check:**
```bash
cd backend
python -m app.scripts.health_check                  # run and compare to baseline
python -m app.scripts.health_check --threshold 5    # allow up to 5% score drop
python -m app.scripts.health_check --save-baseline  # save current run as new baseline
python -m app.scripts.health_check --primary-only   # only test the configured primary model (faster)
```
Exits `0` on pass, `1` on regression. Prints per-model scores with delta from baseline and remediation steps.

**Full 12-scenario stress test (all models):**
```bash
cd backend
python -m app.scripts.stress_test_models
```
Tests 12 scenarios across false/misleading/truthful/mixed claim types at easy/medium/hard difficulty. Saves `stress_test_results.json` and `stress_test_report.md`.

### Key Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | _(required for primary drafts)_ | Primary model access |
| `ANTHROPIC_API_KEY` | _(required for escalation/degraded mode)_ | Escalation and degraded-mode access |
| `OPENAI_REVIEW_DRAFT_MODEL` | `gpt-5-mini` | Primary model ID |
| `CIVIC_AI_DEGRADED_MODE` | `false` | Circuit breaker — set `true` after regression |

---

## What's Included Right Now
- FastAPI backend with versioned `v1` routes for candidates, statements, claims, evidence, evaluations, scores, and comparison.
- PostgreSQL schema with Alembic migrations (through `20260710_01`).
- Structured error responses across all endpoints.
- Reviewer authentication with signed bearer tokens (`POST /v1/auth/login`, `GET /v1/auth/me`).
- Dual-control approval tokens required for candidate mutations and sensitive overrides.
- Per-IP sliding-window rate limiting on all write endpoints with `Retry-After` headers.
- Admin console at `/admin/` — Claim Workbench-first adjudication plus candidate lifecycle, queue/regression tabs, proposal triage, publish/unpublish controls, audit-event inspection, and worker health monitoring. See `docs/CLAIM_WORKBENCH_WORKFLOW.md`.
- AI review draft pipeline with deterministic guardrails, escalation guard, and `CIVIC_AI_DEGRADED_MODE` circuit breaker. Every draft is persisted with history/diff views (`GET /v1/claims/{id}/review-drafts`, `GET /v1/claims/{id}/review-draft-diff`).
- Source integrity checks at attach time: reviewer-facing URL reachability probe, persisted `fetch_status`, and reviewer-supplied `content_excerpt` fallback for paywalled or JS-rendered pages.
- Claim-type evidence anchors for source recommendations — funding/reimbursement claims (amount/program/state/funding-context) and numeric voting-record claims (claimed-stat/denominator/methodology) — gating one-click Workbench attach on anchor sufficiency, with a page-level re-check against real fetched content for resolved Federal Register records.
- Weekly AI regression health check script with baseline comparison and scheduled task (Mondays at 08:00).
- 12-scenario stress test suite covering false, misleading, truthful, and mixed claim types.
- Background job worker with queue + retry logic and worker-health endpoint (`GET /v1/admin/jobs/worker-health`).
- Full-text claim search (`GET /v1/claims/search`) with PostgreSQL GIN index, ILIKE fallback, and relevance ranking.
- Public read-only API tier with API key authentication — admin-issued `X-API-Key` keys for external consumers; exposes published claim verdicts at `GET /v1/public/claims` and cross-race published-volume reporting at `GET /v1/public/race-summary`.
- Admin API key management (`POST/GET/DELETE /v1/admin/api-keys`).
- Claim reviewability heuristics to exclude rhetorical slogans from evidence/review/compare workflows.
- Scoring service with transparent numerators/denominators and formula versioning.
- Moderation policy enforcement with boundary phrase detection.
- Audit event log for all admin/reviewer actions.
- Texas 2026 U.S. Senate race data: roster ingest, statement batches, evidence attachment, and adjudication packet scripts.
- 453 automated backend tests and 5 Playwright smoke tests verified on 2026-10-01, covering scoring, source policy and recommendation logic, review drafts, rate limiting, search, API key service, and core UI flows.

## Project Status And Next Steps
The implementation roadmap through Phase 10 is complete, but the product has not yet been validated as an operating fact-checking service. Do not add another broad feature phase before proving the editorial loop with a narrow pilot.

1. Select one race and a small, balanced set of factual claims.
2. Have at least two trained reviewers create citation-backed evaluations using the existing Workbench and dual-control flow.
3. Publish only evaluations that satisfy the existing evidence and moderation gates, then measure reviewer time, disagreement rate, unresolved-source rate, and correction turnaround.
4. Use that pilot to decide whether to simplify the product around reviewer throughput, invest in operations, or stop work.

See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) for the current go/no-go criteria and [ROADMAP.md](ROADMAP.md) for implementation history.

