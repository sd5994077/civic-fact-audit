# Roadmap

## Phase 0 - Foundations (Week 1)
- [ ] Confirm legal/ethical policy and moderation boundaries.
- [x] Stand up FastAPI + Postgres local development.
- [x] Define canonical data model and migration strategy.
- [x] Define core verification policy for statement capture vs fact verification (`docs/VERIFICATION_POLICY.md`).
- [ ] Add ingestion interfaces for speeches, interviews, social posts.
- [x] Add race roster ingestion script for Texas 2026 U.S. Senate (`backend/app/scripts/ingest_tx_2026_senate_roster.py`).
- [x] Add initial Texas 2026 statement-source batch ingester (`backend/app/scripts/ingest_tx_2026_statement_batch.py`).
- [x] Add round-two Texas statement-source ingester for social/interview/debate (`backend/app/scripts/ingest_tx_2026_statement_batch_round2.py`).
- [x] Add round-three Texas statement-source ingester for narrower factual claims from official candidate pages (`backend/app/scripts/ingest_tx_2026_statement_batch_round3.py`).
- [x] Add evidence queue endpoint/reporting for source attachment triage (`GET /v1/claims/evidence-queue` and `backend/app/scripts/generate_tx_2026_evidence_queue_report.py`).
- [x] Add bulk source attachment endpoint for reviewer throughput (`POST /v1/claims/sources/bulk`).
- [x] Add Texas 2026 first-pass evidence attachment batch with targeted source mappings for known factual claims (`backend/app/scripts/attach_tx_2026_evidence_batch.py`).

## Phase 1 - Claim Capture (Weeks 2-3)
- [x] Build statement ingestion pipeline.
- [x] Use AI extraction to create structured claims.
- [x] Add human review queue for extracted claims.
- [x] Version claim text and provenance metadata.
- [x] Exclude non-fact-checkable campaign rhetoric from evidence/review queues and compare output.

## Phase 2 - Evidence + Verification (Weeks 4-5)
- [x] Evidence linking (primary + independent secondary).
- [x] Verification workflow with confidence labels.
- [x] Reviewer actions: supported, mixed, unsupported, insufficient evidence.
- [x] Audit logging and change history.
- [x] Add review-ready queue/reporting for human adjudication (`GET /v1/claims/review-queue` and `backend/app/scripts/generate_tx_2026_review_queue_report.py`).
- [x] Add authenticated reviewer login and role-gated evaluation writes (`POST /v1/auth/login`, bearer auth on `POST /v1/claims/{id}/evaluate`).
- [x] Distinguish candidate-originated sources from verification sources in review and public display.
- [ ] Add evidence parity rules so comparable candidate issue views use balanced source classes where possible.

## Phase 3 - Scoring + Transparency (Weeks 6-7)
- [x] Implement score formulas from `docs/SCORING.md`.
- [x] Add candidate score snapshots by date range.
- [x] Publish claim-level explanation cards.
- [ ] Add data export (CSV/JSON).
- [ ] Convert provisional Texas claims into human-reviewed cited verdicts.
- [ ] Publish expandable evidence bundle cards with up to five supporting and five rebutting links per claim/issue view.
- [ ] Surface evidence sufficiency and source-balance warnings before showing public verdict confidence.

## Phase 4 - Public Dashboard (Weeks 8-10)
- [ ] Build frontend views for candidates/issues/claims.
- [ ] Add filter controls (date, issue, confidence, source quality).
- [ ] Add comparison pages without endorsement language.
- [ ] Accessibility and performance pass.
- [ ] Add race selector and explicit stage labels so users can switch between primary, runoff, and general contexts.
- [ ] Add shared issue frames so candidate cards compare the same normalized topic/question before public fact-check display.

## Phase 5 - Reliability + Scale (Weeks 11+)
- [ ] Background jobs and retries.
- [ ] Source quality scoring automation.
- [ ] Caching and query optimization.
- [ ] Security hardening and threat model review.
- [ ] Generalize the Texas Senate workflow into a reusable multi-race intake pipeline.
- [ ] Define a priority-race list for 2026 so additional Senate, House, gubernatorial, and other high-impact campaigns can be onboarded deliberately.
- [ ] Build a power-admin workflow for AI-assisted claim grouping, source suggestion, evidence-bundle approval, and final human signoff.

## Near-Term Delivery Plan
1. Shared issue frames
- [x] Define a normalized issue-frame model with a canonical topic and comparison question.
- [x] Add allowed evidence class policy fields for frame-level parity enforcement.
- [x] Map Texas 2026 Senate claims into shared frames so candidate cards compare like-for-like issue views.

2. Balanced evidence bundles
- [x] Add a bundle model that stores stance links separately from verification links.
- [ ] Limit public issue cards to a curated set of links per side and label each by source origin and class.
- [ ] Add parity checks that flag when one candidate has materially weaker or different evidence classes than another on the same issue frame.

3. Admin + AI workflow
- [ ] Let AI propose claim-to-frame mappings, candidate-source captures, and draft verification sources.
- [ ] Require human admin or reviewer approval before proposed sources or verdicts become public.
- [ ] Add an admin queue for unresolved parity gaps, weak evidence bundles, and draft verdict review.

4. Rating workflow
- [x] Keep candidate-originated material as proof of what was said, not proof that it was true.
- [ ] Generate AI draft rationales only after evidence bundles are assembled.
- [ ] Publish public verdicts only after a verified human approves the rating and citations.
