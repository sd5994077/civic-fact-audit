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
- Formula must be versioned and stored with every snapshot (`formula_version`).

## Transparency Requirements
- Publish all metric numerators and denominators.
- Show links for all evidence used in each verdict.
- Maintain revision history for verdict changes.
- Expose denominator policy (`include_insufficient_in_denominator`) with each score response.
