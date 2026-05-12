# Candidate Inventory Draft Review Checklist

This workflow is for review-only inventory preparation. It does not ingest candidates/statements directly.

## Artifact
- `docs/operations/candidate_inventory_current_profiles_draft.json`

## Scope
- `tx_2026_senate`
- `tx_2026_ag_runoff`
- Inventory entries are copied from current roster/statement seed scripts and remain draft until reviewer approval.
- Coverage push adds new factual seed batches:
  - `tx_2026_senate`: `round4`
  - `tx_2026_ag_runoff`: `round2`

## Required reviewer checks before any ingestion
1. Confirm each `candidate` identity/race-context field is complete and accurate for roster upsert fields.
2. Confirm each `statement_sources` entry includes `source_origin`, `source_class`, `publisher`, `url`, and `rationale`.
3. Confirm each `verification_source_candidates` entry includes `source_origin`, `source_class`, `publisher`, and review rationale.
4. Reject any partisan/advocacy verification source entries.
5. Keep candidate-originated links marked as candidate-originated material only, not verification truth evidence.
6. Verify each `policy_precheck` flag and add/adjust review notes for exceptions.
7. For `verification` + `secondary` entries, add/track a neutral primary-record replacement target when available.

## Mapping to existing ingestion jobs
1. Approved candidate roster fields map to `ingest_candidate_roster` payload selection by `profile_id`.
2. Approved statement-source seeds map to `ingest_statement_batch` by `profile_id` and `statement_batch`.
3. After ingestion, run profile-scoped operational jobs through `POST /v1/admin/jobs` in order:
   - `extract_claims_batch`
   - `backfill_claim_reviewability`
4. Keep reviewer decision trail in proposal/review notes when admission exceptions are applied.
