# Source Standards

This document defines source-admission standards for claim verification and how policy lists are maintained.

## Verification Admission Priority

Use sources in this order:
1. Neutral, record-based primary evidence (government records, court filings, legislative records, certified datasets, official reports with methods).
2. Independent reporting for corroboration.
3. Candidate-originated material only to document what was said, not to verify truth.

Rule of precedence:
- Primary records outweigh fact-check summaries and news reporting when records are available.

## Recommendation Tiers (Workbench)

`GET /v1/claims/{claim_id}/source-recommendations` may return recommendation metadata category labels:
- `primary_record`
- `civic_research`
- `fact_check`
- `secondary_news`

These categories help reviewers prioritize triage. They do not change persisted source schema (`source_class` remains `primary` or `secondary`) and they do not replace human adjudication requirements.

## Disallowed for Verification Origin

Do not attach these as `source_origin=verification`:
- partisan party organizations and campaign committees
- advocacy PAC/Super PAC material
- candidate campaign-owned promotional content
- anonymous reposts, meme screenshots, unsourced commentary

## Direct Candidate Quote Exception

A partisan source can be accepted only as candidate-originated statement capture when all conditions pass:
- `source_origin=candidate`
- `is_direct_candidate_quote=true`
- URL is from an allowed social domain (`x.com`, `twitter.com`, `facebook.com`, `instagram.com`, `youtube.com`, `tiktok.com`, `truthsocial.com`)

This exception captures candidate-originated quotes and is not verification truth evidence.

## Policy Config and Matching

Policy lists are versioned in:
- `backend/app/config/source_admission_policy_v1.json`
- `backend/app/config/source_recommendation_policy_v1.json`

Config keys:
- `partisan_publishers`
- `partisan_domains`
- `social_domains`
- `matching.publisher` and `matching.domain`

Matching behavior:
- publisher: `contains` (case-insensitive)
- domain: `suffix` on normalized hostname (exact host or subdomain; userinfo/port stripped)

## Legacy Cleanup and Auditability

Legacy verification rows are preserved and flagged (non-destructive):
- `sources.policy_flagged=true`
- `sources.policy_flag_reason`
- `sources.policy_flagged_at`

Flagged verification sources are excluded from minimum-evidence and publish-gate verification checks.

Scripts:
- Backfill: `python -m app.scripts.backfill_source_admission_policy_flags`
- Report: `python -m app.scripts.generate_source_admission_policy_flag_report`

## Change Process for Policy Lists

1. Propose a change with concrete examples and rationale in reviewer/admin notes.
2. Edit `backend/app/config/source_admission_policy_v1.json`.
3. Run tests: `pytest`.
4. Run impact report: `python -m app.scripts.generate_source_admission_policy_flag_report`.
5. If list changes affect existing rows, run backfill and attach report output to review notes.

## Reviewer Proposal Note Minimums

When adding or approving sources, include these fields in proposal/review notes when applicable:
- `source_origin`
- `source_class`
- `publisher`
- brief rationale for why the source is admissible
