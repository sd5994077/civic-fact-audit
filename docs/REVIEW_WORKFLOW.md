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
- Proposal attribution:
  - `proposed_by` is set server-side from authenticated reviewer/admin identity.
- Bulk source attach request contract:
  - `POST /v1/claims/sources/bulk` expects `{ "approval_reviewer_id": "<id>", "items": [...] }`.
  - Dual-control is enforced only when a batch contains verification-origin items.
- Source-admission enforcement:
  - Proposal create/apply can return `422 source_admission_policy_violation`.
  - If blocked, keep proposal for audit trail, update payload to a neutral/record-based verification source, then re-submit/re-approve.
- Two-person control (verification-source apply):
  - `verification_source_suggestion` proposals require `approved_by != applying_reviewer`.
  - If the same reviewer attempts apply, API returns `409 proposal_dual_control_required`.
  - Use a second reviewer/admin account to apply after approval.
- Power-admin source/bundle-first sequence:
  - Review source proposal payload with admission fields (`source_origin`, `source_class`, `publisher`, `quality_score`).
  - Approve/reject proposal.
  - Apply approved proposal to attach source and sync claim evidence bundle atomically.
  - Continue to publish queue only after evidence coverage and reviewer evaluation are complete.

## 2) Inspect publish queue
- API: `GET /v1/claims/publish-queue`
- Script: `python -m app.scripts.generate_tx_2026_publish_queue_report`
- AG runoff script: `python -m app.scripts.generate_tx_2026_attorney_general_runoff_publish_queue_report`

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
- If updating an already-evaluated claim verdict, provide `approval_reviewer_id` from a different reviewer/admin than the applying actor.
- Moderation gate is clean.
- Publish gate passes for the claim.

Signoff definition:
- Final human signoff is achieved by reviewer/admin completion plus publish-gate pass.
- No separate signoff object/state exists in v1.

## 4) Publish
- API: `POST /v1/claims/{id}/publish` (admin-only)
- Unpublish API: `POST /v1/claims/{id}/unpublish` (admin-only)
- Batch script:
  - Dry run: `python -m app.scripts.publish_tx_2026_claims_batch`
  - Apply: `python -m app.scripts.publish_tx_2026_claims_batch --apply --approver reviewer@local`
- Admin UI guard:
  - Publish action is blocked in `/admin` until checklist items pass.
  - Checklist enforces rationale/citation/evidence/moderation/gate readiness prior to `POST /v1/claims/{id}/publish`.
- Two-person control (publish/unpublish final mutation):
  - `publish` and `unpublish` require `approval_reviewer_id != applying_reviewer_id`.
  - Approval reviewer is resolved from the latest human claim evaluation reviewer identity.
  - If the same reviewer (or no approval reviewer) is resolved, API returns `409 publish_dual_control_required`.
  - Retry path: hand off final `publish`/`unpublish` action to a different reviewer/admin account and retry.

## Exception handling notes
- Evaluation overwrite dual-control blocked (`409 evaluation_overwrite_dual_control_required`):
  - first evaluation is exempt; overwrites require a different approval reviewer identity.
  - keep claim state unchanged and re-submit evaluate request with different reviewer separation.
- Bulk attach dual-control blocked (`409 bulk_attach_dual_control_required`):
  - conflict applies only when payload contains verification-origin items.
  - keep batch unchanged, hand off apply action to a different reviewer/admin, then retry same payload.
- Self-apply blocked (`409 proposal_dual_control_required`):
  - Keep proposal in `approved`, route apply to a different reviewer/admin.
- Publish/unpublish dual-control blocked (`409 publish_dual_control_required`):
  - Keep claim state unchanged, hand off final mutation to a different reviewer/admin, retry same endpoint.
- Source policy violation (`422 source_admission_policy_violation`):
  - Keep proposal unchanged, revise source to admissible record-based verification source, re-submit/approve/apply.
- Apply retry path:
  - Fix payload issue or role separation issue, then retry `POST /v1/claims/proposals/{proposal_id}/apply`.

## 5) Track completion progress
- Script: `python -m app.scripts.generate_tx_2026_publish_progress_report`
- AG runoff script: `python -m app.scripts.generate_tx_2026_attorney_general_runoff_publish_progress_report`

This prints:
- total fact-checkable claims
- published claims and percent
- ready-but-unpublished claims
- blocked claims grouped by failure reason

## 6) Enforce coverage gate (current profiles)
- Script (Senate): `python -m app.scripts.generate_tx_2026_claim_coverage_report`
- Script (AG runoff): `python -m app.scripts.generate_tx_2026_attorney_general_runoff_claim_coverage_report`
- Required pass condition for both profiles: each candidate has `published_verified_claims >= 3`.

## 6) Export public compare rows (CSV/JSON)
- API: `GET /v1/compare/export`
- Query fields align with compare filters:
  - `state`, `office`, `election_cycle`, `race_stage`
  - `window_start`, `window_end`, `limit_issues`
  - `issue_contains`, `min_confidence`, `min_source_quality`
  - `format=json|csv`

Export rows include traceability fields (`claim_id`, `candidate_id`, verdict/confidence, source counts, warning codes) for downstream review and auditing.
