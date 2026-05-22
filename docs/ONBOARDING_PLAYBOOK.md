# Race Onboarding Playbook

_How to bring a new race (primary, runoff, general, special) into the civic-fact-audit pipeline._

---

## Overview

Adding a new race requires **two types of input**:

| Input type | Who provides it | What it is |
|---|---|---|
| **Profile config** | Developer | Race identity metadata in `intake_profiles_v1.json` |
| **Editorial data** | Researcher/operator | Candidate names + statement URLs (always manual) |

Everything else — claim extraction, reviewability backfill, KPI reporting — runs generically once the editorial data is in the database.

---

## Prerequisites

- [ ] Admin reviewer account exists and you have the login credentials for the account that will apply the change
- [ ] A second reviewer/admin account exists and you have the login credentials for the account that will issue the approval token
- [ ] Database is running and migrations are up to date (`alembic upgrade head`)
- [ ] You have a neutral, record-based source for the candidate roster (SOS filing page, certified results page, or equivalent — see `docs/THREAT_MODEL.md` source admission rules)

### Credentials you need

Use two separate identities during dual-control actions:
SecurePass1!
| Credential type | Who uses it | What it is for |
|---|---|---|
| **Admin/applying credentials** | The person making the change in the admin console | Sign in, open the Race Profiles form, and submit the save request |
| **Reviewer/approval credentials** | A different authorized reviewer or admin | Sign in, request the dual-control approval token for `intake_profile_mutation`, and hand that token to the applying user |

Do not reuse the same account for both roles. The approval step must come from a different reviewer/admin than the person saving the profile.

#### Local development accounts

These are the local accounts used by the app during development:

| Account | Email | Role | Password handling |
|---|---|---|---|
| **Bootstrap admin/reviewer** | `reviewer@local` | `admin` | Set from `reviewer_bootstrap_password` in `.env` |
| **Second reviewer** | `second@local` | `reviewer` | Create with `python -m app.scripts.create_reviewer ...`; use a local password you choose |

Keep passwords out of the playbook itself. If you change them locally, update your `.env` or creation command, not the documentation.

---

## Step 1 — Add the intake profile to config

Use the admin console **Race Profiles** tab to create or edit the intake profile. The UI writes to `backend/app/config/intake_profiles_v1.json` for you, so you do not need to hand-edit the JSON file for routine updates.

**What it does:** sets the race’s identity metadata, modules, and stage in the shared config.
**Why it matters:** every downstream ingest and pipeline step depends on this record being accurate and complete.

**Edit Race Profile accuracy check:** confirm the label, state, office, election cycle, race stage, roster module path, and JSON module maps match the official race context exactly.
The `Approval Token` is a signed dual-control token that proves a second authorized reviewer approved the change; it is required so one person cannot both approve and apply the update.

**How to get the token:** a second reviewer or admin can sign in on this page and use the new **Request Approval Token** panel to generate a token for `intake_profile_mutation`.
If you prefer the API, the same action is available from `POST /api/v1/auth/dual-control-approval-token`.
The response includes the `approval_token`, `approval_reviewer_id`, and `expires_at`; the token is short-lived and should be pasted into the form before it expires.
The approval token is separate from the normal login access token; keep using the login access token in the `Authorization: Bearer ...` header and paste the short-lived approval token into mutation forms that require dual control.

Example request body:

```json
{ "action": "intake_profile_mutation" }
```

If you are using the UI, the same rule applies: one person prepares the change, a different authorized reviewer logs in and requests the token, and the applying reviewer pastes it into the form.

If you need to review the underlying structure, the profile object looks like this:

```json
{
  "profile_id": "state_year_office_stage",
  "label": "Human-readable race label",
  "state": "TX",
  "office": "US Senate",
  "election_cycle": 2026,
  "race_stage": "primary_runoff",
  "roster_seed_module": "app.scripts.ingest_state_year_office_stage_roster",
  "statement_batch_modules": {
    "starter": "app.scripts.ingest_state_year_office_stage_statement_batch"
  },
  "admin_job_modules": {}
}
```

**Naming conventions:**
- `profile_id`: `{state_lower}_{year}_{office_slug}_{stage}` — e.g. `tx_2026_ag_runoff`
- `race_stage` must be one of: `primary`, `primary_runoff`, `general`, `special`
- `roster_seed_module` and `statement_batch_modules` values are dotted Python module paths

The backend automatically bumps the config `version` string when you save from the admin console.

---

## Step 2 — Generate script stubs

Run the stub generator to create pre-filled boilerplate roster and statement batch scripts:

**What it does:** creates starter roster and statement batch scripts for the selected profile.
**Why it matters:** gives you a consistent, reproducible place to enter the manual editorial data for that race.

These stubs are the handoff point between config and actual editorial work, so once they exist you can start filling in concrete candidate and statement data.

```bash
python -m app.scripts.generate_race_stubs --profile-id <profile_id>
```

This **previews** both files to stdout. Review them, then write to disk:

```bash
python -m app.scripts.generate_race_stubs --profile-id <profile_id> --write
```

Two files are created in `backend/app/scripts/`:
- `ingest_{profile_id}_roster.py`
- `ingest_{profile_id}_statement_batch.py`

---

## Step 3 — Fill in the roster (editorial)

Open `ingest_{profile_id}_roster.py`. Fill in the `ROSTER` list with one `RosterEntry` per candidate:

**What it does:** records the candidate roster for the race from neutral, record-based sources.
**Why it matters:** the roster is the foundation for candidate matching, statement ingestion, and later claim extraction.

Be strict here: use the official candidate spelling, the correct office and state, and a source that a reviewer can verify later.

```python
RosterEntry(
    name='Candidate Full Name',       # exact name as used in public records
    party='Republican',               # or 'Democratic', 'Independent', None
    office='US Senate',               # must match profile office exactly
    state='TX',
    election_cycle=2026,
    race_stage=RaceStage.primary_runoff,
    roster_status='runoff_reported',  # e.g. filed_confirmed, runoff_reported
    source_url='https://sos.state.gov/candidates/race',  # primary source
),
```

**Source admission requirements:**
- `source_url` must be a neutral, record-based source (official SOS page, certified results, court record, legislative record)
- Independent reporting may corroborate but must not be the only basis when a primary record exists
- Partisan/advocacy sources are disallowed as verification evidence

Run the roster script:

```bash
python -m app.scripts.ingest_{profile_id}_roster
```

Verify output: `created=N updated=0 total=N`

---

## Step 4 — Fill in statements (editorial)

Open `ingest_{profile_id}_statement_batch.py`. Fill in the `SEEDS` list with one `StatementSeed` per statement captured:

**What it does:** loads verbatim candidate statements into the pipeline with source metadata.
**Why it matters:** those statements become the raw material for claim extraction and reviewer workflows.

Each seed should point to a real source URL and preserve the exact wording as published or spoken.

```python
StatementSeed(
    candidate_name='Candidate Full Name',  # must match roster name exactly
    office='US Senate',
    state='TX',
    election_cycle=2026,
    race_stage=RaceStage.primary_runoff,
    source_type=StatementSourceType.press_release,
    source_url='https://candidate.example.com/page',
    statement_text='Exact verbatim quote from the source.',
    published_at=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
    note='Campaign homepage snapshot, captured YYYY-MM-DD.',
),
```

Run the statement batch script:

```bash
python -m app.scripts.ingest_{profile_id}_statement_batch
```

Verify: `created=N missing_candidate=0 duplicate=0`

Repeat this step in additional rounds (`_round2`, `_round3`, etc.) as new statements are collected. Add each new module to `statement_batch_modules` in the profile config.

---

## Step 5 — Run the generic pipeline

```bash
python -m app.scripts.run_generic_pipeline --profile-id <profile_id>
```

**What it does:** extracts claims, backfills reviewability metadata, and prints KPI counts.
**Why it matters:** this is the step that turns ingested statements into reviewable work for the team.

If this step reports missing claims or no reviewable output, go back and check the roster and statement files before moving on.

This runs in order:
1. **Claim extraction** — extracts claims from all statements that have none yet
2. **Reviewability backfill** — applies the fact-checkability heuristic to all claims
3. **KPI snapshot** — prints before/after counts (candidates, statements, claims, fact-checkable claims)

Expected output:
```
Pipeline start: <label> (profile_id=<profile_id>)
claim_extraction: claims_created=N statements_skipped=0
reviewability_backfill: metadata_updated=N non_fact_checkable=N
kpi_before={"candidates": N, "statements": N, "claims": 0, "fact_checkable_claims": 0}
kpi_after={"candidates": N, "statements": N, "claims": N, "fact_checkable_claims": N}
Pipeline complete.
```

Re-run this command after each new statement batch to pick up newly added statements.

---

## Step 6 — Verify via admin console

1. Open the admin console and navigate to the **Jobs** tab
2. Confirm worker health shows no terminal failures
3. Navigate to the **Compare** view and select the new race — candidates and claims should appear
4. Check the **Review Queue** tab — fact-checkable claims should be queued for evidence collection

**What it does:** confirms the profile change actually flowed through jobs, compare, and review surfaces.
**Why it matters:** catches configuration or ingestion mistakes before the race enters active review work.

If the race does not appear, the problem is usually one of these: the profile config is wrong, the roster script did not run cleanly, or the statement batch did not produce claims.

---

## Step 7 — Begin the review workflow

Follow the standard review workflow:
1. Assign evidence sources to claims via the evidence queue
2. Reviewers evaluate claims using the evaluation workflow
3. Admin publishes approved evaluations

**What it does:** moves from setup into evidence collection, evaluation, and publication.
**Why it matters:** this is the point where the race starts producing traceable, cited verdicts.

From here forward, the evidence trail matters more than speed: every verdict should be backed by citations and review notes.

---

## Updating an existing race

**New statement round:**
1. Create `ingest_{profile_id}_statement_batch_roundN.py` (copy the previous batch script, clear SEEDS, fill new data)
2. Add the new module to `statement_batch_modules` in `intake_profiles_v1.json`
3. Re-run `python -m app.scripts.run_generic_pipeline --profile-id <profile_id>`

**Roster update (candidate advances, withdraws, or status changes):**
1. Update the relevant `RosterEntry` in the roster script
2. Re-run the roster script (it is idempotent — upserts by race context)

**Runoff promotion (primary → runoff):**
Create a separate profile entry with `race_stage: "primary_runoff"` and its own roster/statement scripts. The primary profile remains intact.

**Updating candidate information (admin UI or API):**
1. Open the admin console and go to the candidate detail view, or call `PATCH /v1/candidates/{candidate_id}`.
2. Update only the fields you actually need to change:
   - `name`
   - `party`
   - `office`
   - `state`
   - `election_cycle`
   - `race_stage`
   - `is_active`
   - `roster_status`
   - `roster_source_url`
   - `roster_checked_at`
   - `roster_notes`
3. Save the change and confirm the audit trail shows the update.
4. If the candidate already has statements, avoid changing race-context fields unless the roster record is genuinely corrected.

**Adding candidate-originated comments, ideas, or statements:**
1. Capture the exact wording from the candidate’s own channel or public appearance.
2. Create the record with `POST /v1/statements` for ad hoc entries, or add it to the appropriate `ingest_{profile_id}_statement_batch.py` script for bulk ingestion.
3. Use an appropriate `source_type` such as `speech`, `interview`, `social`, or `press_release`.
4. Store the exact quote in `statement_text` and add a short provenance note in `note` if you need capture context.
5. Treat candidate-originated comments or ideas as source material for claim extraction, not as verification evidence on their own.
6. Re-run `python -m app.scripts.run_generic_pipeline --profile-id <profile_id>` so the new statements are extracted into claims.

---

## Reference

| Script | Purpose |
|---|---|
| `generate_race_stubs.py --profile-id X` | Generate roster + statement batch stubs |
| `ingest_{profile_id}_roster.py` | Seed candidate records (manual editorial data) |
| `ingest_{profile_id}_statement_batch.py` | Seed statement records (manual editorial data) |
| `run_generic_pipeline.py --profile-id X` | Extract claims + backfill reviewability + KPI |

| Config file | Purpose |
|---|---|
| `app/config/intake_profiles_v1.json` | Master race registry |
| `app/core/intake_profiles.py` | Profile loader (`get_intake_profiles_config()`) |
| `app/scripts/pipeline_helpers.py` | Generic `RaceContext` + query/run functions |
