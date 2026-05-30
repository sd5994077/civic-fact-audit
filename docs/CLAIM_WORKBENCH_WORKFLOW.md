# Claim Workbench Workflow (MVP)

This is the primary reviewer/admin workflow for claim adjudication in `/admin`.

Policy boundaries still apply:
- moderation boundaries: `docs/MODERATION_POLICY.md`
- source admission boundaries: `docs/SOURCE_STANDARDS.md`
- verification model: `docs/VERIFICATION_POLICY.md`

## 1) Reviewer-Facing States

Workbench rows expose one canonical reviewer-facing state per claim:
- `Needs Evidence`
- `Needs Review`
- `Needs Second Reviewer`
- `Ready to Publish`
- `Published`
- `Insufficient Evidence`

Tie-break precedence:
1. `Published`
2. `Ready to Publish`
3. `Needs Second Reviewer`
4. `Insufficient Evidence`
5. `Needs Review`
6. `Needs Evidence`

State derivation is read-time only (`GET /v1/claims/workbench`), with no state table or migration.
Non-fact-checkable claims are excluded by default and can be included with `include_non_fact_checkable=true`.
The admin UI also hides terminal states (`Published` and `Insufficient Evidence`) by default unless a reviewer-state filter is selected or `Show terminal states` is checked.

## 2) Responsibilities

Reviewer/admin responsibilities in Workbench:
- attach admissible sources (record `source_origin`, `source_class`, publisher, and quote exception only when applicable)
- submit claim evaluation (`supported|mixed|unsupported|insufficient`) with rationale/citation notes
- resolve blocking checklist items
- hand off when dual-control is required

Admin-only responsibilities:
- execute publish/unpublish final mutation

No endpoint in this workflow may be used to produce endorsements or voting recommendations.

## 3) Evidence and Evaluation Flow

1. Start with `Needs Evidence` rows.
2. Attach verification evidence until at least one verification `primary` and one verification `secondary` source are present.
   - Workbench can pre-load neutral candidates from `GET /v1/claims/{claim_id}/source-recommendations`.
   - Suggestions are reviewer aids only; reviewers must still confirm relevance before attaching.
   - Recommendations marked `discovery_only` are research links and are not one-click attachable evidence.
3. Row moves to `Needs Review` when minimum verification evidence is present and no latest human evaluation exists.
4. Submit evaluation via `POST /v1/claims/{claim_id}/evaluate`.
5. If latest verdict is `insufficient`, row is treated as review-complete but non-publishable (`Insufficient Evidence`).

Important gates:
- verdicts `supported|mixed|unsupported` require minimum verification evidence
- evaluation overwrites require dual-control (`evaluation_overwrite` approval token from a different reviewer/admin)
- moderation policy applies to rationale and citation notes

## 4) Publish and Handoff Flow

Workbench exposes checklist entries and raw `publish_gate_failures` codes from current publish logic.

Publish-readiness checklist order:
1. `fact_checkable`
2. `latest_verdict_publishable`
3. `latest_rationale_present`
4. `latest_citation_notes_present`
5. `verification_primary_present`
6. `verification_secondary_present`
7. `moderation_clear`
8. `dual_control_ready_for_publish`

`Ready to Publish` means publish gate checks pass and the claim is not published.
Dual-control still applies for publish/unpublish final mutation:
- publish approval identity is inferred from latest evaluation reviewer
- applying publisher must be a different reviewer/admin
- violations return `409 publish_dual_control_required`

Second-reviewer hints:
- `publish_handoff`: final publish actor must differ from approval reviewer
- `overwrite_handoff`: overwrite path requires second-reviewer approval token

## 5) Common Blocking Conditions and Remediation

- Missing verification primary/secondary:
  - Attach admissible verification sources.
- Missing citation notes:
  - Re-evaluate claim with citation notes (overwrite dual-control applies if a prior evaluation exists).
- Moderation policy failure:
  - Rewrite rationale/citation notes to neutral, non-partisan language and resubmit evaluation.
- Source-admission rejection (`422 source_admission_policy_violation`):
  - Replace partisan/advocacy verification source with neutral record-based source.
  - Candidate-origin partisan material is allowed only for direct candidate quote capture under allowed exception constraints.
- Dual-control conflict (`409 evaluation_overwrite_dual_control_required` / `409 publish_dual_control_required`):
  - Hand off to different reviewer/admin per endpoint requirements.

## 6) Advanced Tool Boundaries

Workbench is the default path for day-to-day operations.

Use advanced tabs only when necessary:
- `Review Queue`, `Evidence Queue`, `Publish Controls`: API-level queue inspection/regression checks
- `Proposal Triage`: proposal lifecycle and apply operations
- `Advanced: Bulk Attach`: controlled bulk source ingestion requiring strict payload review and dual-control handling for verification-origin items

## 7) QA Smoke Coverage

Run frontend/admin smoke checks:

```bash
npm run test:smoke
```

The smoke suite now includes a focused Workbench recommendation regression on claim `89949aa0-1f75-481b-9449-6ee4f45f5b3b`:
- validates Workbench scope/filter loading
- validates suggested verification link rendering
- validates one-click attach from suggestion
- validates verification coverage update (`primary >= 1`, `secondary >= 1`)
