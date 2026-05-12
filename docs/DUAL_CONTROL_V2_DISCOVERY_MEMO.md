# Dual-Control v2 Discovery Memo (2026-05-12)

## Scope
Inventory additional high-risk mutation paths that should be considered for dual-control expansion beyond the current verification-source proposal apply guard.

## Current Implemented Behavior
- `proposal_dual_control_required` currently blocks same-reviewer approve/apply for verification-source proposal apply actions.
- Coverage includes `verification_source_suggestion` and `candidate_source_capture` when payload `source_origin=verification`.

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
- Status: pending product + operations decision.
- Implementation: not yet started for v2 expansion paths above.
- Planning intent: preserve current additive policy, then phase in per-endpoint dual-control with auditable reviewer linkage metadata.
