# Admin Console Implementation Plan (Current-State + Handoff)

Purpose: document implemented admin-console behavior and record the handoff to the next roadmap phase.

## 1) What Exists Today

- Candidate records can be created/listed/updated through admin-gated APIs, including roster metadata.
- Race roster and intake operations are primarily script-driven.
- Admin job orchestration is persisted with allowlisted job types and status/result tracking.
- Admin audit events are persisted and queryable in a dedicated admin API.
- Dedicated `/admin/` workspace exists for candidate management, review queue adjudication, evidence queue triage, bulk source attach operations, proposal triage, publish controls, jobs, and audit visibility.
- Jobs tab uses typed intake controls (`Race Profile`, `Statement Batch`) and auto-generates editable JSON payloads.
- Evidence Queue and Bulk Source Attach are first-class admin tabs; bulk attach includes client-side JSON validation and response summaries.
- Public dashboard remains comparison/export focused and no longer hosts reviewer/admin mutation actions.

## 2) Implemented Baseline Constraints

Current operational constraints preserved by the config-first intake model:

1. Admin job input payload is now validated per job type:
- `ingest_candidate_roster`: `{ "profile_id": "<profile_id>" }`
- `ingest_statement_batch`: `{ "profile_id": "<profile_id>", "statement_batch": "<batch_key>" }`
- non-intake jobs: `{}` (plus optional `dry_run` only when a given job type explicitly supports it)
- invalid payloads return structured `job_input_invalid` details with `missing_fields`, `unsupported_fields`, and `allowed_values`.
- admin UI metadata is available at `GET /v1/admin/jobs/metadata` so typed job controls can be rendered from backend config.

2. Job trigger audit linkage:
- `admin_job_triggered` events are recorded with `entity_type = admin_job_run` and `entity_id = <job_run_id>`.

3. Intake orchestration is config-first and async:
- profile config selects roster and statement-batch modules per race profile.
- execution now enqueues within `POST /v1/admin/jobs` and runs via a background worker with retries and status polling.

## 3) Proposed Data Model Additions

These are proposed defaults if no alternative is preferred.

## Candidate (extend existing table)
- `is_active` bool default `true`
- `roster_status` nullable string (or enum)
- `roster_source_url` nullable string
- `roster_checked_at` nullable timestamptz
- `roster_notes` nullable text

Operational rule:
- if candidate has linked statements/claims, disallow destructive edits to race-context identity fields in normal admin UI; use deactivation/supersede flow.

## AdminJobRun (new table)
- `id` UUID
- `job_type` string
- `status` string (`queued`/`running`/`succeeded`/`failed`/`canceled`)
- `requested_by_reviewer_id` string
- `input_payload` JSON/text
- `started_at` nullable timestamptz
- `finished_at` nullable timestamptz
- `result_summary` JSON/text
- `error_details` JSON/text
- `created_at`
- `updated_at`

Allowlisted `job_type` seed set:
- `ingest_candidate_roster`
- `ingest_statement_batch`
- `extract_claims_batch`
- `backfill_claim_reviewability`
- `map_issue_frames`
- `generate_publish_queue_report`
- `generate_publish_progress_report`

## AdminAuditEvent (optional new table)
- `id` UUID
- `actor_reviewer_id` string
- `action` string
- `entity_type` string
- `entity_id` string/UUID
- `before_payload` JSON/text
- `after_payload` JSON/text
- `metadata` JSON/text
- `created_at`

## 4) Backend Implementation Plan

Phase A: security and candidate admin foundation
- Require `admin` role for candidate mutations.
- Add `GET /v1/candidates/{id}`.
- Add `PATCH /v1/candidates/{id}` with controlled mutable fields.
- Add structured conflict/validation errors for protected race-context changes.

Phase B: roster metadata and ingestion service unification
- Move roster upsert logic into reusable service layer.
- Keep scripts as wrappers around services for reproducibility.
- Persist roster metadata fields from roster workflows.

Phase C: job orchestration backend
- Add job-run service and allowlisted executor routing.
- Add endpoints:
  - `POST /v1/admin/jobs`
  - `GET /v1/admin/jobs`
  - `GET /v1/admin/jobs/{id}`
- Return structured status and failure details.

Phase D: admin audit visibility
- Record candidate mutations and admin job triggers.
- Expose audit views via API for admin UI consumption.

## 5) Frontend Implementation Plan

Add dedicated `/admin` workspace with explicit role gate.

Initial sections:
- `Candidates`: search, detail, edit, activate/deactivate, roster metadata.
- `Intake`: roster upload/import trigger and statement intake trigger.
- `Jobs`: start jobs and monitor status/history.
- `Review`: existing reviewer queue and proposal triage components.
- `Publish`: publish queue and publish actions.

Design rule:
- separate public comparison surface from staff-only operations UI.

## 6) API/Error Contract Requirements

- Keep structured error object shape.
- Add dedicated admin error codes where needed:
  - `admin_forbidden`
  - `candidate_update_conflict`
  - `job_type_not_allowed`
  - `job_execution_failed`
- Include machine-readable details for blocking validations.

## 7) Migration + Rollout Strategy

1. Add non-breaking nullable columns and new tables.
2. Backfill roster metadata where possible from existing scripts/config.
3. Deploy admin-only mutation gates with feature flags if needed.
4. Roll out admin UI on top of stabilized APIs.
5. Keep script workflows operational during transition.

## 8) Test Plan

- Unit tests:
  - candidate update validation and immutable-field guards
  - job-run status transitions
  - allowlisted job routing and failure handling

- API tests:
  - admin-only enforcement for candidate writes and job trigger endpoints
  - structured errors for blocked updates and bad job types

- Regression tests:
  - existing review/publish/checking workflows still function
  - compare/export behavior unchanged except intended admin gating separation

## 9) Status + Handoff

The admin-console implementation scope is complete:
- candidate lifecycle/admin job/audit infrastructure is in place,
- `/admin/` contains the dedicated operator workspace,
- power-admin and dual-control workflows are implemented,
- worker-health observability is live,
- and the admin console no longer has an open implementation backlog.

Next roadmap step:
- use `docs/PRIORITY_RACES_2026.md` and the config-first intake profiles to onboard the next priority race(s) without changing the admin-console architecture.
