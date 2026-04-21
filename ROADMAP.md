# Roadmap

## Phase 0 - Foundations (Week 1)
- [ ] Confirm legal/ethical policy and moderation boundaries.
- [x] Stand up FastAPI + Postgres local development.
- [x] Define canonical data model and migration strategy.
- [ ] Add ingestion interfaces for speeches, interviews, social posts.
- [x] Add race roster ingestion script for Texas 2026 U.S. Senate (`backend/app/scripts/ingest_tx_2026_senate_roster.py`).
- [x] Add initial Texas 2026 statement-source batch ingester (`backend/app/scripts/ingest_tx_2026_statement_batch.py`).
- [x] Add round-two Texas statement-source ingester for social/interview/debate (`backend/app/scripts/ingest_tx_2026_statement_batch_round2.py`).
- [x] Add evidence queue endpoint/reporting for source attachment triage (`GET /v1/claims/evidence-queue` and `backend/app/scripts/generate_tx_2026_evidence_queue_report.py`).
- [x] Add bulk source attachment endpoint for reviewer throughput (`POST /v1/claims/sources/bulk`).
- [x] Add Texas 2026 first-pass evidence attachment batch (`backend/app/scripts/attach_tx_2026_evidence_batch.py`).

## Phase 1 - Claim Capture (Weeks 2-3)
- [x] Build statement ingestion pipeline.
- [x] Use AI extraction to create structured claims.
- [x] Add human review queue for extracted claims.
- [x] Version claim text and provenance metadata.

## Phase 2 - Evidence + Verification (Weeks 4-5)
- [x] Evidence linking (primary + independent secondary).
- [x] Verification workflow with confidence labels.
- [x] Reviewer actions: supported, mixed, unsupported, insufficient evidence.
- [x] Audit logging and change history.

## Phase 3 - Scoring + Transparency (Weeks 6-7)
- [x] Implement score formulas from `docs/SCORING.md`.
- [x] Add candidate score snapshots by date range.
- [ ] Publish claim-level explanation cards.
- [ ] Add data export (CSV/JSON).
- [ ] Convert provisional Texas claims into human-reviewed cited verdicts.

## Phase 4 - Public Dashboard (Weeks 8-10)
- [ ] Build frontend views for candidates/issues/claims.
- [ ] Add filter controls (date, issue, confidence, source quality).
- [ ] Add comparison pages without endorsement language.
- [ ] Accessibility and performance pass.
- [ ] Add race selector and explicit stage labels so users can switch between primary, runoff, and general contexts.

## Phase 5 - Reliability + Scale (Weeks 11+)
- [ ] Background jobs and retries.
- [ ] Source quality scoring automation.
- [ ] Caching and query optimization.
- [ ] Security hardening and threat model review.
- [ ] Generalize the Texas Senate workflow into a reusable multi-race intake pipeline.
- [ ] Define a priority-race list for 2026 so additional Senate, House, gubernatorial, and other high-impact campaigns can be onboarded deliberately.
