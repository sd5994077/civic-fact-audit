# Roadmap

## Phase 0 - Foundations (Week 1)
- [ ] Confirm legal/ethical policy and moderation boundaries.
- [x] Stand up FastAPI + Postgres local development.
- [x] Define canonical data model and migration strategy.
- [ ] Add ingestion interfaces for speeches, interviews, social posts.

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

## Phase 4 - Public Dashboard (Weeks 8-10)
- [ ] Build frontend views for candidates/issues/claims.
- [ ] Add filter controls (date, issue, confidence, source quality).
- [ ] Add comparison pages without endorsement language.
- [ ] Accessibility and performance pass.

## Phase 5 - Reliability + Scale (Weeks 11+)
- [ ] Background jobs and retries.
- [ ] Source quality scoring automation.
- [ ] Caching and query optimization.
- [ ] Security hardening and threat model review.
