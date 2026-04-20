# Data Model (MVP)

All tables include `created_at` and `updated_at` audit timestamps.

## Candidate
- `id` (UUID)
- `name`
- `party`
- `office`
- `state`
- `created_at`
- `updated_at`

## Statement
- `id` (UUID)
- `candidate_id` (FK)
- `source_type` (speech/interview/social/debate/press_release)
- `source_url`
- `statement_text`
- `published_at`
- `created_at`
- `updated_at`

## Claim
- `id` (UUID)
- `statement_id` (FK)
- `claim_text`
- `issue_tag`
- `extraction_confidence`
- `extraction_method`
- `extraction_metadata`
- `status` (draft/reviewed/published)
- `created_at`
- `updated_at`

## Source
- `id` (UUID)
- `claim_id` (FK)
- `url`
- `source_class` (primary/secondary)
- `publisher`
- `quality_score` (0-1)
- `created_at`
- `updated_at`
- unique: `(claim_id, url)`

## ClaimEvaluation
- `id` (UUID)
- `claim_id` (FK)
- `verdict` (supported/mixed/unsupported/insufficient)
- `confidence` (0-1)
- `rationale`
- `citation_notes`
- `reviewer_id`
- `created_at`
- `updated_at`

Multiple evaluations per claim are allowed. The latest evaluation is used for scoring; prior rows remain as revision history.

## ScoreSnapshot
- `id` (UUID)
- `candidate_id` (FK)
- `window_start`
- `window_end`
- `fact_support_rate`
- `false_claim_rate`
- `evidence_sufficiency_rate`
- `composite_score`
- `formula_version`
- `include_insufficient_in_denominator`
- `denominator_total`
- `created_at`
- `updated_at`
