# Review + Publish Workflow (Texas 2026)

This workflow converts provisional fact-check claims into public, cited verdicts.
Moderation/output boundaries are defined in `docs/MODERATION_POLICY.md`.

## 1) Triage proposal queue (new)
- API endpoints (reviewer/admin):
  - `POST /v1/claims/{claim_id}/proposals`
  - `GET /v1/claims/proposals`
  - `POST /v1/claims/proposals/{proposal_id}/approve`
  - `POST /v1/claims/proposals/{proposal_id}/reject`
  - `POST /v1/claims/proposals/{proposal_id}/apply`
- Proposal apply effects:
  - `issue_frame_mapping`: assigns `claims.issue_frame_id`
  - `candidate_source_capture`/`verification_source_suggestion`: attaches source and syncs evidence bundle
  - `draft_verdict`: remains draft-only guidance; reviewer must still use `POST /v1/claims/{claim_id}/evaluate`
- Source-admission enforcement:
  - Proposal create/apply can return `422 source_admission_policy_violation`.
  - If blocked, keep proposal for audit trail, update payload to a neutral/record-based verification source, then re-submit/re-approve.

## 2) Inspect publish queue
- API: `GET /v1/claims/publish-queue`
- Script: `python -m app.scripts.generate_tx_2026_publish_queue_report`

Blocked rows return `publish_gate_failures` codes:
- `claim_not_fact_checkable`
- `latest_verdict_must_be_supported_mixed_or_unsupported`
- `latest_rationale_required`
- `latest_citation_notes_required`
- `verification_primary_source_required`
- `verification_secondary_source_required`
- `latest_evaluation_moderation_policy_violation`

## 3) Reviewer completion checklist per claim
Before publish, reviewer/admin should ensure:
- Claim is fact-checkable.
- Latest verdict is `supported`, `mixed`, or `unsupported`.
- Rationale is present and neutral.
- Citation notes are present.
- Verification evidence includes at least:
  - 1 primary source
  - 1 independent secondary source

## 4) Publish
- API: `POST /v1/claims/{id}/publish` (admin-only)
- Batch script:
  - Dry run: `python -m app.scripts.publish_tx_2026_claims_batch`
  - Apply: `python -m app.scripts.publish_tx_2026_claims_batch --apply --approver reviewer@local`

## 5) Track completion progress
- Script: `python -m app.scripts.generate_tx_2026_publish_progress_report`

This prints:
- total fact-checkable claims
- published claims and percent
- ready-but-unpublished claims
- blocked claims grouped by failure reason

## 6) Export public compare rows (CSV/JSON)
- API: `GET /v1/compare/export`
- Query fields align with compare filters:
  - `state`, `office`, `election_cycle`, `race_stage`
  - `window_start`, `window_end`, `limit_issues`
  - `issue_contains`, `min_confidence`, `min_source_quality`
  - `format=json|csv`

Export rows include traceability fields (`claim_id`, `candidate_id`, verdict/confidence, source counts, warning codes) for downstream review and auditing.
