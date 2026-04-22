# Ingestion Workflow (Race-Based)

This workflow keeps race setup and statement intake reproducible and auditable.

## 1) Create/refresh race roster
- Run the race roster ingester for the target race.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.ingest_tx_2026_senate_roster`

## 2) Seed statement-source batch
- Run the statement batch ingester for the same race context.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.ingest_tx_2026_statement_batch`
  - `python -m app.scripts.ingest_tx_2026_statement_batch_round2`
  - `python -m app.scripts.ingest_tx_2026_statement_batch_round3`
- Use the later batches to introduce narrower, record-checkable claims after initial campaign-context capture.

## 3) Extract claims
- Call `POST /v1/claims/extract` per statement, or run a race-scoped batch extractor.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.extract_tx_2026_claims_batch`
- Keep extraction confidence and metadata for auditability.
- Apply reviewability heuristics so slogans and campaign rhetoric do not enter evidence or human-review queues.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.backfill_tx_2026_claim_reviewability`

## 4) Attach evidence
- Add at least one primary and one independent secondary source for claims that will receive supported/mixed/unsupported verdicts.
- Pull queue items from `GET /v1/claims/evidence-queue` to triage claims missing minimum evidence.
- Use `POST /v1/claims/sources/bulk` to attach sources across multiple claims in one request.
- Mark each attached source as `candidate`-originated or `verification`-originated so review and public display can keep statement proof separate from truth proof.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.map_tx_2026_claim_issue_frames`
  - `python -m app.scripts.generate_tx_2026_evidence_queue_report`
  - `python -m app.scripts.attach_tx_2026_evidence_batch`
  - `python -m app.scripts.backfill_tx_2026_evidence_bundles`

Map claims into shared `IssueFrame` records before evidence parity work so candidate compare cards use the same normalized question when claims are substantively comparable. The current Texas mapper is conservative: it maps fact-checkable claims with known issue tags and leaves slogans or ambiguous statements unmapped.
Backfill non-curated evidence bundles after source attachment so compare/public views can distinguish stance links from verification links before later admin curation.

## 5) Human evaluation
- Pull ready items from `GET /v1/claims/review-queue` once minimum evidence is attached.
- Sign in via `POST /v1/auth/login` and use returned bearer token.
- Use `POST /v1/claims/{id}/evaluate`.
- Send header: `Authorization: Bearer <access_token>`.
- Include rationale and citation notes in every verdict.
- Only fact-checkable claims should appear here; rhetorical or slogan-only statements stay out of the queue.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.generate_tx_2026_review_queue_report`
  - `python -m app.scripts.generate_tx_2026_adjudication_packet`

## 6) Compute scores
- Use `GET /v1/candidates/{id}/scores` with explicit window bounds.
- Expose denominator and formula version in all score outputs.

## Repeatability rules
- Keep candidate race context explicit: `state`, `office`, `election_cycle`, `race_stage`.
- Treat roster ingestion and statement ingestion as idempotent operations.
- Update source links when official filing status or campaign channels change.
- Use one race as the implementation template, then promote the workflow to additional races instead of hardcoding one-off scripts forever.
- Prioritize expansion by explicit race list and stage:
  - current pilot: Texas 2026 U.S. Senate primary/runoff context
  - next discussions should cover which additional 2026 races matter most and are realistic to review well
