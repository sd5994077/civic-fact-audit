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

- [ ] Admin reviewer account exists and you have credentials
- [ ] Database is running and migrations are up to date (`alembic upgrade head`)
- [ ] You have a neutral, record-based source for the candidate roster (SOS filing page, certified results page, or equivalent — see `docs/THREAT_MODEL.md` source admission rules)

---

## Step 1 — Add the intake profile to config

Edit `backend/app/config/intake_profiles_v1.json`. Add a new object to the `profiles` array:

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

Bump the config `version` string (e.g. `intake_profiles_v4_YYYY_MM_DD`).

---

## Step 2 — Generate script stubs

Run the stub generator to create pre-filled boilerplate roster and statement batch scripts:

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

---

## Step 7 — Begin the review workflow

Follow the standard review workflow:
1. Assign evidence sources to claims via the evidence queue
2. Reviewers evaluate claims using the evaluation workflow
3. Admin publishes approved evaluations

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
