# Roadmap

## Current Handoff - 2026-06-15
- Stopped after recovering the interrupted test run.
- Verified backend suite is clean: `python -m pytest backend\tests` -> 418 passed.
- Verified frontend smoke suite is clean: `npm test` -> 4 Playwright tests passed.
- Applied recovery fix: review-draft escalation now requires both primary and secondary verification evidence before invoking the Anthropic second pass, preventing one-source drafts from making avoidable live model calls.
- Added regression coverage for that escalation guard and for the dead-source publish gate (`verification_source_url_unreachable`).
- Pickup item: review the large dirty worktree and decide which generated artifacts/temp files should be kept before committing logical chunks.

## Phase 0 - Foundations (Week 1)
- [x] Confirm legal/ethical policy and moderation boundaries (`docs/MODERATION_POLICY.md`, moderation publish/evaluate gates).
- [x] Stand up FastAPI + Postgres local development.
- [x] Define canonical data model and migration strategy.
- [x] Define core verification policy for statement capture vs fact verification (`docs/VERIFICATION_POLICY.md`).
- [x] Add ingestion interfaces for speeches, interviews, social posts (`StatementSourceType` plus statement ingest routes/scripts).
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
- [x] Add evidence parity rules so comparable candidate issue views use balanced source classes where possible.

## Phase 3 - Scoring + Transparency (Weeks 6-7)
- [x] Implement score formulas from `docs/SCORING.md`.
- [x] Add candidate score snapshots by date range.
- [x] Publish claim-level explanation cards.
- [x] Add data export (CSV/JSON).
- [x] Convert provisional Texas claims into human-reviewed cited verdicts.
- [x] Add publish-queue diagnostics and progress reporting for Texas 2026 review throughput (`backend/app/scripts/generate_tx_2026_publish_queue_report.py`, `backend/app/scripts/generate_tx_2026_publish_progress_report.py`, `docs/REVIEW_WORKFLOW.md`).
- [x] Publish expandable evidence bundle cards with up to five supporting and five rebutting links per claim/issue view.
- [x] Surface evidence sufficiency and source-balance warnings before showing public verdict confidence.

## Phase 4 - Public Dashboard (Weeks 8-10)
- [x] Build frontend views for candidates/issues/claims.
- [x] Add filter controls (date, issue, confidence, source quality).
- [x] Add comparison pages without endorsement language.
- [x] Accessibility and performance pass.
- [x] Add race selector and explicit stage labels so users can switch between primary, runoff, and general contexts.
- [x] Add shared issue frames so candidate cards compare the same normalized topic/question before public fact-check display.

## Phase 5 - Reliability + Scale (Weeks 11+)
- [x] Background jobs and retries.
- [x] Source quality scoring automation (`score_source_quality()` heuristic, `quality_score` now optional on add/bulk-attach, versioned formula `quality_v1_2026_05_13`).
- [x] Caching and query optimization (composite index on `candidates(state, office, election_cycle, race_stage)`; `claims(fact_checkable)` and `claims(fact_checkable, is_published)` indexes; `list_publish_queue` `is_published` filter pushed to SQL before `LIMIT` to prevent published claims consuming queue slots).
- [x] Security hardening and threat model review (`docs/THREAT_MODEL.md`, CORS middleware, production startup validators for `postgres_password` + `cors_allowed_origins`, `.env.example`).
- [x] Expand moderation beyond boundary phrase gates (regex rule engine, 4 new violation types: `violence_or_threat`, `harassment_or_doxxing`, `defamatory_framing`, `prompt_injection_attempt`; prompt injection gate on claim extraction; per-reviewer violation audit logging; `GET /v1/admin/moderation-risk` risk endpoint).
- [x] Generalize the Texas Senate workflow into a reusable multi-race intake pipeline.
- [x] Add a runoff onboarding playbook and templated script generator (`generate_race_stubs.py`, `run_generic_pipeline.py`, `pipeline_helpers.py`, `docs/ONBOARDING_PLAYBOOK.md`) — new races require only a profile config entry + editorial roster/statement data; extraction, backfill, and KPI run generically.
- [x] Harden source-admission enforcement with config-backed partisan/domain rules, proposal-path validation parity, and non-destructive legacy verification-source exclusion flags.
- [x] Define a priority-race list for 2026 so additional Senate, House, gubernatorial, and other high-impact campaigns can be onboarded deliberately (`docs/PRIORITY_RACES_2026.md`, Tier 1 profiles `tx_2026_governor` + `tx_2026_senate_general` registered in config, Tier 2/3 races documented with promotion checklist).

## Phase 6 - Admin Operations Console (Post-Model Revision)
- Reference implementation spec: `docs/ADMIN_CONSOLE_IMPLEMENTATION_PLAN.md`
- [x] Finalize admin-facing data-model changes for candidate lifecycle, roster verification metadata, ingestion jobs, and operator audit records before implementation.
- [x] Lock down candidate mutation endpoints so create/update/archive actions are admin-only and auditable.
- [x] Add candidate administration APIs for candidate detail, controlled updates, active/inactive state, and race-context integrity checks.
- [x] Persist roster verification metadata instead of leaving roster status/source checks only in scripts and console output.
- [x] Introduce allowlisted operational job records for roster intake, statement intake, extraction, reviewability backfills, issue-frame mapping, and reporting.
- [x] Build a dedicated admin frontend workspace for candidate management, race intake (profile-driven typed job inputs), job execution/status, evidence operations, review queues, proposal triage, and publish controls.
- [x] Add dedicated admin frontend workspace (`/admin/`) for candidate management, review queue adjudication, proposal triage, publish controls, job execution/status, and audit visibility.
- [x] Separate public compare/dashboard browsing from staff-only admin/reviewer workflows in the UI information architecture.
- [x] Add admin audit visibility for who triggered jobs, changed candidate records, applied proposals, and published/unpublished claims.
- [x] Track and implement remaining dual-control v2 expansion scope for additional high-risk mutation paths (candidate updates, evaluation overwrite paths, bulk attach) with explicit approval reviewer fields, first-evaluation overwrite exception, verification-only bulk enforcement, and deterministic bulk-operation audit correlation; see `docs/DUAL_CONTROL_V2_DISCOVERY_MEMO.md`.
- [x] Harden dual-control enforcement so approval/applying reviewer identities resolve to active reviewer/admin accounts before candidate mutation, evaluation overwrite, and verification-source bulk attach writes.
- [x] Implement dual-control v2 first slice for `POST /v1/claims/{id}/publish` and `POST /v1/claims/{id}/unpublish` with reviewer-linkage audit metadata and admin Publish-tab operator guidance.
- [x] Generalize current race-specific CLI workflows into config-first admin flows for profile-scoped extraction/reviewability/report jobs, preserving reproducibility and source traceability.
- [x] Add config-first preset intake profiles for admin roster/statement ingestion (`profile_id` + `statement_batch` typed payload validation/routing).
- [x] Prepare current-profile candidate/source draft inventory artifact (review-only, no direct ingestion) for `tx_2026_senate` and `tx_2026_ag_runoff`.
- [x] Add current-profile coverage-to-3 workflow support (new factual statement batches, profile-scoped progress/coverage reports, and operator runbook) for `tx_2026_senate` and `tx_2026_ag_runoff`.
- [x] Build the power-admin workflow v1 for AI-assisted claim grouping, source suggestion, evidence-bundle approval, and final human signoff inside the dedicated admin surface.
- [x] Ship Claim Workbench MVP (`GET /v1/claims/workbench` + `/admin` Workbench-first operator flow + checklist/handoff guidance docs) while keeping existing queues and safety gates intact.

## Near-Term Delivery Plan
1. Shared issue frames
- [x] Define a normalized issue-frame model with a canonical topic and comparison question.
- [x] Add allowed evidence class policy fields for frame-level parity enforcement.
- [x] Map Texas 2026 Senate claims into shared frames so candidate cards compare like-for-like issue views.

2. Balanced evidence bundles
- [x] Add a bundle model that stores stance links separately from verification links.
- [x] Limit public issue cards to a curated set of links per side and label each by source origin and class.
- [x] Add parity checks that flag when one candidate has materially weaker or different evidence classes than another on the same issue frame.

3. Admin + AI workflow
- [x] Let AI propose claim-to-frame mappings, candidate-source captures, and draft verification sources.
- [x] Require human admin or reviewer approval before proposed sources or verdicts become public.
- [x] Add an admin/reviewer publish queue for draft verdict review with explicit publish-gate failures (`GET /v1/claims/publish-queue`).

4. Rating workflow
- [x] Keep candidate-originated material as proof of what was said, not proof that it was true.
- [x] Generate AI draft rationales only after evidence bundles are assembled.
- [x] Publish public verdicts only after a verified human approves the rating and citations.

5. Admin operations console
- [x] Review and approve the target data-model extensions before any implementation begins.
- [x] Ship admin-safe candidate CRUD and roster-verification foundations first.
- [x] Add persistent job orchestration records before exposing web-triggered intake workflows.
- [x] Build the admin UI only after backend mutation, audit, and job contracts are stable.
- [x] Add worker-health observability: queue lag, retry counts, and terminal-failure visibility (`GET /v1/admin/jobs/worker-health`, Jobs tab health panel with 30s auto-refresh).

## Phase 7 - Production Hardening
- [x] Rate limiting — per-IP sliding-window limits on all write endpoints (`app/core/rate_limiter.py`); HTTP 429 with `Retry-After` header; no new dependencies; multi-instance upgrade path documented (Redis swap-in). Limits: login 10/min, dual-control token 30/min, evaluate/create-proposal 120/min, publish/unpublish/bulk-attach/proposal-decisions 60/min.
- [x] Public read-only API tier — `api_keys` table with SHA-256 hashing, `ApiKeyService` for generate/verify/revoke, `require_api_key` dependency for `X-API-Key` header auth, admin endpoints `POST/GET/DELETE /v1/admin/api-keys`, public claims endpoints `GET /v1/public/claims` and `GET /v1/public/claims/{id}` for published claim verdicts, CORS updated for `X-API-Key` header.
- [x] Full-text claim search — `GET /v1/claims/search?q=` with PostgreSQL GIN tsvector index on `claim_text`, ILIKE fallback on `issue_tag` and `candidate.name`, ts_rank ordering, and optional race-context + status filters (`app/services/search_service.py`, migration `20260513_03`).
- [x] Reviewer notification workflow — `reviewer_notifications` table with dedup index, `NotificationService` for enqueue/process, `EmailTransport` (smtplib) and `WebhookTransport` (urllib), background-thread dispatch after `evaluate_claim` (`claim_ready_for_publish`) and `create_proposal` (`proposal_needs_triage`), admin endpoints `GET/POST /v1/admin/notifications`, configurable via env vars (`notification_enabled`, `smtp_*`, `notification_webhook_url`).

## Phase 8 - Priority Race Expansion
- [x] Add admin-console race-profile CRUD so intake profiles can be created and edited without hand-editing JSON.
- [x] Onboard the next priority race(s) using the existing config-first intake profiles and `/admin/` operator workspace, without introducing new admin-console architecture. (`tx_2026_governor` onboarding executed on May 19, 2026)
- [x] Keep the rollout aligned with `docs/PRIORITY_RACES_2026.md` and the reusable race-profile onboarding playbook. (`tx_2026_governor` executed via scripted roster + statement batches + generic pipeline + profile-scoped diagnostics)
- [x] Expand public-facing reporting and performance tuning only where new race volume creates a measurable need. (Added `GET /v1/public/race-summary` and `claims(is_published, published_at)` performance index for higher-volume published-claim reads across multiple races.)

## Phase 9 - Evidence-Aware Source Recommendations
- Reference implementation plan: `docs/SOURCE_RECOMMENDATION_HARDENING_PLAN.md`
- [x] Distinguish recommendation page types in backend validation (`search_results`, `homepage`, `section_page`, `evidence_page`, `article`, `pdf_or_report`, `unknown`).
- [x] Add recommendation role metadata (`attachable_evidence`, `discovery_only`, `candidate_quote_only`, `rejected`) so research links stay visible without being auto-attachable evidence.
- [x] Gate Workbench one-click attach to `attachable_evidence` recommendations only, with clear research-only explanations for discovery links.
- [x] Add deterministic Congress.gov bill-ID resolver v1 (API-keyed) for `tx_senate_congress_primary` so explicit bill citations can resolve from research links to official bill pages.
- [x] Add claim-type evidence anchors to move from topic-overlap-only checks to evidence sufficiency checks (funding/reimbursement anchors existed; added numeric voting-record anchors — `claimed_stat`/`denominator`/`methodology` — gating attach on methodology plus a matching stat or denominator, not just keyword presence).
- [x] Add deterministic page-level anchor extraction from fetched content to support robust amount/methodology checks before evidence attachment (Federal Register resolver results are now re-checked against the real fetched document text, not just search-API metadata, before being marked attachable).
- [x] Add Workbench reviewer guidance text for discovery-only vs attachable recommendations and publish-gate impact (persistent guidance banner, role pills, and per-recommendation missing-anchor notes on the Suggested Verification Links panel).

## Phase 10 - Hybrid Review Assistant
- [x] Add reviewer-authenticated AI draft endpoint for claim-level review packets (`POST /v1/claims/{id}/review-draft`).
- [x] Add Workbench "Draft Evidence Review" UI with one-click prefill into evaluation fields.
- [x] Enforce that AI drafts remain non-final reviewer assistance (no auto-evaluate, no auto-publish).
- [x] Add persistent draft history and diffing between AI draft and reviewer-submitted evaluation (`claim_ai_drafts` table + `GET /v1/claims/{id}/review-drafts` + `GET /v1/claims/{id}/review-draft-diff`, surfaced in Workbench).
- [x] Add deterministic numeric-claim denominator/methodology validators to complement model confidence (`_numeric_voting_anchor_assessment` in the source-recommendation service; see Phase 9).
