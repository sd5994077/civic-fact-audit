# Scoring Framework (MVP)

## Core Metrics
1. **Fact Support Rate (FSR)**
   - `supported_claims / total_evaluated_claims`
2. **False Claim Rate (FCR)**
   - `unsupported_claims / total_evaluated_claims`
3. **Evidence Sufficiency Rate (ESR)**
   - `claims_with_minimum_evidence / total_evaluated_claims`

## Composite (v1)
`composite_score = (0.5 * FSR) + (0.3 * ESR) - (0.2 * FCR)`

## Rules
- Default denominator policy excludes claims whose latest verdict is `insufficient`.
- A policy flag can include `insufficient` claims in the denominator for alternate reporting.
- Every claim scored as `supported`, `mixed`, or `unsupported` must have at least:
  - 1 primary source
  - 1 independent secondary source
- Verification sources flagged by source-admission cleanup (`sources.policy_flagged=true`) are excluded from evidence sufficiency checks and publish-gate verification counts.
- Formula must be versioned and stored with every snapshot (`formula_version`).

## Source Quality Scoring (v1)

Automated baseline via `score_source_quality()` in `app/core/source_quality_scoring.py` (version `quality_v1_2026_05_13`).

`quality_score` is optional on `AddSourceRequest` and `BulkSourceAttachItem`. When omitted the heuristic computes the value; an explicit caller-supplied value is always preserved.

| Signal | Effect |
|---|---|
| `source_class = primary` | base 0.85 |
| `source_class = secondary` | base 0.70 |
| `source_origin = verification` + `primary` | +0.05 |
| `source_origin = candidate` | −0.10 |
| `is_direct_candidate_quote = true` (candidate origin only) | +0.05 |
| URL domain suffix `.gov` | +0.10 |
| URL domain suffix `.edu` | +0.05 |

Result is clamped to [0.0, 1.0] and rounded to 2 decimal places.

Note: `quality_score` is stored per-source for future weighting but is not currently used in the FSR/FCR/ESR composite formula.

## Transparency Requirements
- Publish all metric numerators and denominators.
- Show links for all evidence used in each verdict.
- Maintain revision history for verdict changes.
- Expose denominator policy (`include_insufficient_in_denominator`) with each score response.
- Treat public verdict display as a separate approval step: only admin-published claims are eligible for public compare views.
