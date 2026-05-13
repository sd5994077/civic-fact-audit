# Admin Console Implementation Plan (Current-State + Next Step)

Purpose: document implemented admin-console behavior and define the next implementation step.

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

Current operational constraints to preserve until config-first intake work is completed:

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

## 9) Status + Next Step Checklist

- [x] Candidate model extension approved/implemented.
- [x] Job-run model approved/implemented.
- [x] Audit-event model decision approved/implemented.
- [x] Mutation guard policy approved/implemented (race-context protections + admin gating).
- [x] Admin endpoint contract approved/implemented.
- [x] Frontend section priority approved/implemented.
- [x] Next step: generalize race-specific CLI workflows into config-first admin flows (typed job inputs and per-job validated payload schemas).
- [x] Power-admin workflow v1 implemented:
  - source/bundle-first proposal review cues in Proposals tab,
  - two-person control for verification-source proposal apply,
  - publish-tab pre-publish checklist gate as final signoff control,
  - no new signoff state-machine or endpoint family introduced.
- [x] Power-admin source checklist coverage implemented for both proposal types, including `needs review` mismatch handling for `candidate_source_capture` and `verification_source_suggestion`.
- [x] Proposal-detail claim context enrichment implemented in `/admin` with current evidence sufficiency snapshot and latest evaluation summary beside proposal payload.
- [x] Backend/API proposal audit metadata coverage implemented so `proposal_approved` and `proposal_applied` reads persist reviewer-linkage fields (`approval_reviewer_id`, `applying_reviewer_id`, `proposal_type`).
- [x] Publish checklist hard-block and stale-selection regression coverage implemented for the admin Publish tab.
- [x] Dual-control v2 first slice implemented:
  - publish/unpublish endpoints enforce two-person control against latest evaluation approver identity,
  - `claim_published` / `claim_unpublished` audit events persist reviewer-linkage metadata (`approval_reviewer_id`, `applying_reviewer_id`, `dual_control_enforced`),
  - `/admin` Publish tab surfaces explicit dual-control denial guidance for deterministic `409 publish_dual_control_required`.
- [x] Dual-control v2 verification-only expansion implemented:
  - candidate create/update now enforce reviewer separation (`409 candidate_dual_control_required`) using server-verified dual-control approval tokens,
  - evaluation overwrite now enforces reviewer separation with first-evaluation exception (`409 evaluation_overwrite_dual_control_required` only when overwriting) using server-verified dual-control approval tokens,
  - bulk attach now uses object payload (`approval_token` + `items`) and enforces reviewer separation only for verification-origin items (`409 bulk_attach_dual_control_required`),
  - dual-control reviewer identities are resolved against active reviewer accounts (reviewer/admin roles) before mutation is allowed,
  - bulk attach emits a deterministic `bulk_operation_id` for traceable batch audit correlation,
  - candidate/evaluation overwrite/bulk attach audit events persist reviewer-linkage metadata and dual-control flags.

## 10) Worker-Health Observability (Complete)

- [x] Add worker-health observability for queue lag, retry counts, and terminal failure alerting:
  - `GET /v1/admin/jobs/worker-health` endpoint (admin-only) returns a `WorkerHealthResponse` with `worker_alive`, `queue_depth`, `due_depth`, `retry_queue_depth`, `oldest_queued_age_seconds`, `oldest_due_age_seconds`, `running_count`, `terminal_failure_count`, and `recent_terminal_failures` (last 10),
  - aggregate query uses `COUNT(*) FILTER (WHERE ...)` and `MIN() FILTER (WHERE ...)` for a single-pass read,
  - `worker_alive` reflects live thread state via `AdminJobService._worker_thread.is_alive()`,
  - `recent_terminal_failures` surface `job_type`, `attempt_count`, `max_attempts`, `last_error_code`, and `finished_at` for each exhausted-retry job,
  - route registered before `/{job_run_id}` to prevent FastAPI UUID coercion conflict,
  - admin UI Jobs tab shows a Worker Health panel with colour-coded stat tiles (alive/dead, queue depth, due-now, retrying, running, oldest-due lag, terminal failure count) and a recent-failures list,
  - panel auto-refreshes every 30 seconds while the Jobs tab is active and stops polling on tab switch,
  - two API tests (`test_get_worker_health_requires_admin_auth`, `test_get_worker_health_success`) and two service unit tests (`test_health_failure_summary_serializes_job_run_fields`, `test_health_failure_summary_handles_zero_attempts`) added.
