# Source Recommendation Hardening Plan

## Objective
Improve Workbench `Suggested Verification Links` so reviewers can still discover useful research links while attaching only policy-safe, evidence-appropriate sources.

This pass intentionally avoids LLM integration. The current system remains deterministic and policy-gated.

## Current Baseline
- Backend recommendations are template-driven with HTTP reachability + topic-overlap checks.
- Source admission policy already blocks social and partisan/advocacy verification sources.
- Workbench currently renders recommendations with a one-click attach affordance.

## Problems Being Addressed
- Broad search or section pages can appear as if they are direct verification evidence.
- Topic overlap alone can overstate evidentiary quality.
- Reviewers need clearer separation between "research helper" and "attachable evidence."

## Phase 9 Scope (Current)
1. Add backend `page_type` classification for each recommendation.
2. Add backend `recommendation_role` classification.
3. Keep discovery links visible; block one-click attach for non-attachable roles in Workbench.
4. Return explicit reviewer-facing notes for research-only/rejected cases.

## Out of Scope (Current)
- No LLM source discovery/ranking in this pass.
- No scoring-formula changes.
- No schema migrations.

## Next Slice
1. [x] Add deterministic evidence-anchor extraction directly from fetched content — Federal Register
   resolver results are re-checked against the real fetched document text (not just search-API
   metadata) via `_federal_register_item_is_attachable` before being marked attachable.
2. [x] Funding/reimbursement claims:
   - enforce claimed amount and funding-context anchors before attachable role.
3. [x] Numeric voting-record claims:
   - preserve methodology signal requirements and strengthen denominator/numerator checks
     (`_numeric_voting_anchor_assessment`: `claimed_stat`/`denominator`/`methodology` anchors;
     attach requires methodology plus a matching stat or denominator).
4. [x] Add richer reviewer UX messaging about why a recommendation is research-only — persistent
   guidance banner explaining attachable_evidence vs discovery_only and publish-gate impact, role
   pills, and a per-recommendation missing-anchor note (e.g. "missing: program, funding_context")
   on the Workbench Suggested Verification Links panel.

## Acceptance Criteria
- Workbench only shows `Attach This Source` for `recommendation_role=attachable_evidence`.
- Discovery links remain visible with clear explanation notes.
- Backend responses include `page_type` and `recommendation_role` for each recommendation.
- Existing source-admission guardrails remain intact.
