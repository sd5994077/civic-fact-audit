# Build Plan (MVP)

## Objective
Deliver a local MVP that can ingest candidate statements, extract claims, attach evidence, evaluate factual support, and compute transparent score snapshots.

## Deliverables
1. REST API service with authentication-ready structure.
2. Postgres schema for candidates/statements/claims/sources/evaluations/snapshots.
3. Claim extraction service (AI-assisted) with reviewer queue.
4. Scoring service with reproducible formulas.
5. Basic dashboard-ready endpoints.

## Work Breakdown

### 1) Backend Skeleton
- Set up FastAPI app, settings management, and route modules.
- Add `/health` and `/version` endpoints.
- Add placeholders for `candidates`, `claims`, and `evaluations` routes.

### 2) Data Model
- Create core entities:
  - Candidate
  - Statement
  - Claim
  - Source
  - ClaimEvaluation
  - ScoreSnapshot
- Add created/updated timestamps and source provenance fields.

### 3) Ingestion + Extraction
- Accept raw text ingestion payload.
- Chunk statement text and call AI extraction prompt.
- Store extracted claims with confidence and extraction metadata.

### 4) Evidence Linking
- Attach source links to claims.
- Enforce minimum evidence rule (1 primary + 1 independent source).
- Store source type and quality score.

### 5) Evaluation Workflow
- Reviewer endpoint to mark claim verdict.
- Track rationale and citation notes.
- Keep revision history for transparency.

### 6) Scoring
- Compute Fact Support Rate, False Claim Rate, and optional composite score.
- Snapshot per candidate and date range.
- Return score components with denominators.

### 7) API Endpoints (initial)
- `POST /v1/statements`
- `POST /v1/claims/extract`
- `POST /v1/claims/{id}/sources`
- `POST /v1/claims/{id}/evaluate`
- `GET /v1/candidates/{id}/scores`

## Definition of Done (MVP)
- Endpoints functional locally.
- Schema migrated and queryable.
- At least 10 seeded claims can be evaluated end-to-end.
- Score endpoint returns transparent formulas and inputs.

## Risks
- Source quality inconsistency.
- AI extraction drift across topics.
- Legal/policy constraints for politically sensitive outputs.

## Mitigations
- Strict source-quality rubric.
- Human review before public scoring.
- Keep full citation trails and change logs.
