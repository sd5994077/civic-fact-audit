# Dual-Control v2 Discovery Memo (2026-05-12)

## Scope
Inventory additional high-risk mutation paths that should be considered for dual-control expansion beyond the current verification-source proposal apply guard.

## Current Implemented Behavior
- `proposal_dual_control_required` currently blocks same-reviewer approve/apply for verification-source proposal apply actions.
- Coverage includes `verification_source_suggestion` and `candidate_source_capture` when payload `source_origin=verification`.
- Publish/unpublish first slice is implemented: `POST /v1/claims/{id}/publish` and `POST /v1/claims/{id}/unpublish` enforce `approval_reviewer_id != applying_reviewer_id` and persist reviewer-linkage audit metadata.
- Remaining v2 expansion paths from discovery are now implemented for this phase with server-verified approval tokens and deterministic `409` dual-control conflicts:
  - candidate create/update mutations (`candidate_dual_control_required`)
  - claim evaluation overwrite path (`evaluation_overwrite_dual_control_required`)
  - bulk source attach for verification-origin items (`bulk_attach_dual_control_required`)

## Recommended v2 Expansion
- Candidate lifecycle mutations:
  - candidate update/activation changes in admin candidate APIs.
  - Rationale: impacts race context and downstream public interpretation.
- Claim publication toggles:
  - publish/unpublish actions.
  - Rationale: immediate public-surface impact.
- Claim evaluation edits for already-reviewed claims:
  - follow-up evaluation submissions that replace latest verdict context.
  - Rationale: material adjudication impact.
- Bulk source attach operations:
  - large multi-claim verification-source write paths.
  - Rationale: high blast radius and potential admission-policy bypass risk if misused.

## Deferred Items
- Admin job execution dual-control:
  - defer until job allowlist risk scoring exists (some jobs are read/report-only).
- Proposal creation dual-control:
  - defer because proposal creation is non-mutating to published truth state.

## Decision Status
- Status: dual-control v2 verification-only expansion for candidate mutation, evaluation overwrite, and bulk attach is implemented.
- Implementation details:
  - candidate create/update accept `approval_token` and enforce reviewer separation against the applying actor using server-verified token subject identity.
  - evaluation overwrite enforces reviewer separation only when a prior evaluation exists (first evaluation remains single-step and does not require approval token).
  - bulk attach enforces reviewer separation only when any batch item has `source_origin=verification`; candidate-origin-only batches are unaffected in this slice, and token identity is server-resolved.
  - audit metadata now includes `approval_reviewer_id`, `applying_reviewer_id`, and `dual_control_enforced` on these mutation paths.
  - dual-control approval token issuance is audited (`dual_control_approval_token_issued`) and dual-control approval tokens are rejected by bearer-auth identity resolution.
