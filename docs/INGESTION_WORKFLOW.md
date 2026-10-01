# Ingestion Workflow (Race-Based)

This workflow keeps race setup and statement intake reproducible and auditable.

## Admin job intake profiles (Step 2)
- Intake jobs in `POST /v1/admin/jobs` are profile-driven and now enqueue for background worker execution with retries.
- Supported payload shapes:
  - `{"job_type":"ingest_candidate_roster","input_payload":{"profile_id":"tx_2026_senate"}}`
  - `{"job_type":"ingest_statement_batch","input_payload":{"profile_id":"tx_2026_senate","statement_batch":"round5"}}`
  - `{"job_type":"extract_claims_batch","input_payload":{"profile_id":"tx_2026_senate"}}`
  - `{"job_type":"backfill_claim_reviewability","input_payload":{"profile_id":"tx_2026_ag_runoff"}}`
  - `{"job_type":"generate_publish_queue_report","input_payload":{"profile_id":"tx_2026_ag_runoff"}}`
  - `{"job_type":"generate_publish_progress_report","input_payload":{"profile_id":"tx_2026_ag_runoff"}}`
  - `{"job_type":"generate_profile_claim_coverage_report","input_payload":{"profile_id":"tx_2026_senate"}}`
- Current profile ids:
  - `tx_2026_senate`
  - `tx_2026_ag_runoff`
- `statement_batch` values are profile-specific and must match configured batch keys for the selected profile.
- Additional profile-scoped job support is surfaced via `GET /v1/admin/jobs/metadata` (`allowed_values.profile_id` per job type).

## 1) Create/refresh race roster
- Run the race roster ingester for the target race.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.ingest_tx_2026_senate_roster`
- Example (Texas 2026 Attorney General runoff starter):
  - `python -m app.scripts.ingest_tx_2026_attorney_general_runoff_roster`
- Candidate mutation API guardrails:
  - `POST /v1/candidates` and `PATCH /v1/candidates/{id}` are admin-only.
  - `GET /v1/candidates/{id}` is admin-only and can be used to verify candidate metadata after intake updates.
  - Roster ingestion now persists `roster_status`, `roster_source_url`, and `roster_checked_at` on candidate records for auditable snapshot history.

## 2) Seed statement-source batch
- Run the statement batch ingester for the same race context.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.ingest_tx_2026_statement_batch`
  - `python -m app.scripts.ingest_tx_2026_statement_batch_round2`
  - `python -m app.scripts.ingest_tx_2026_statement_batch_round3`
  - `python -m app.scripts.ingest_tx_2026_statement_batch_round4`
  - `python -m app.scripts.ingest_tx_2026_statement_batch_round5`
- Example (Texas 2026 Attorney General runoff starter):
  - `python -m app.scripts.ingest_tx_2026_attorney_general_runoff_statement_batch --dry-run`
  - `python -m app.scripts.ingest_tx_2026_attorney_general_runoff_statement_batch`
  - `python -m app.scripts.ingest_tx_2026_attorney_general_runoff_statement_batch_round2`
- Use the later batches to introduce narrower, record-checkable claims after initial campaign-context capture.

## 3) Extract claims
- Call `POST /v1/claims/extract` per statement, or run a race-scoped batch extractor.
- Example (Texas 2026 U.S. Senate):
  - `python -m app.scripts.extract_tx_2026_claims_batch`
- For `tx_2026_senate`, the generic pipeline intentionally covers both `primary` and `primary_runoff` candidates so runoff statements enter the same reviewable workbench flow as the active Senate profile.
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
- Pull ready items from reviewer-authenticated `GET /v1/claims/review-queue` once minimum evidence is attached.
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

## Coverage-to-5 runoff operator sequence (US Senate)
Use this sequence for `tx_2026_senate` when the goal is at least 5 published verified claims for each runoff candidate (John Cornyn and Ken Paxton).

1. Ingest approved statement batches through `POST /v1/admin/jobs`:
   - Senate: `round5` (in addition to already-approved earlier rounds).
2. Run `extract_claims_batch` then `backfill_claim_reviewability`.
3. Run `generate_publish_queue_report` and `generate_publish_progress_report`.
4. Attach evidence with `POST /v1/claims/sources/bulk`:
   - at least one verification `primary`
   - at least one verification `secondary`
   - no partisan/advocacy verification sources
5. Evaluate via `POST /v1/claims/{id}/evaluate` and publish via `POST /v1/claims/{id}/publish`.
6. Run `generate_profile_claim_coverage_report` and require pass:
   - John Cornyn `published_verified_claims >= 5`
   - Ken Paxton `published_verified_claims >= 5`
7. If either runoff candidate fails coverage gate, keep remaining claims unpublished and continue evidence/review work until gate passes.
