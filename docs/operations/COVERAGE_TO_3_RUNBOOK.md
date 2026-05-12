# Coverage-to-3 Runbook (Current Profiles)

Scope:
- `tx_2026_senate`
- `tx_2026_ag_runoff`

Goal:
- each candidate must reach `published_verified_claims >= 3`

## Admin-job sequence
1. `POST /v1/admin/jobs` with `job_type=ingest_statement_batch`
- senate batch: `round4`
- ag runoff batch: `round2`
2. `POST /v1/admin/jobs` with `job_type=extract_claims_batch` per profile.
3. `POST /v1/admin/jobs` with `job_type=backfill_claim_reviewability` per profile.
4. `POST /v1/admin/jobs` with `job_type=generate_publish_queue_report` per profile.
5. `POST /v1/admin/jobs` with `job_type=generate_publish_progress_report` per profile.

## Evidence + review sequence
1. Pull queue: `GET /v1/claims/evidence-queue`.
2. Attach sources: `POST /v1/claims/sources/bulk`.
- required for each publishable claim:
- verification `primary` >= 1
- verification `secondary` >= 1
3. Evaluate claims: `POST /v1/claims/{id}/evaluate`.
4. Publish gate finalization: `POST /v1/claims/{id}/publish`.

## Coverage gate
Run profile report jobs:
- `job_type=generate_profile_claim_coverage_report`

Pass condition:
- every candidate in the profile has `published_verified_claims >= 3`

Failure handling:
- do not publish additional claims solely to force count if evidence policy fails
- keep claims in queue until source-admission and publish gates pass

## Safe-stop / rollback points
1. After statement ingest:
- safe to stop; no verdict/publication changes.
2. After extraction/reviewability:
- safe to stop; claims can remain unpublished.
3. After evidence attach:
- if policy issue detected, remove/replace problematic sources before evaluation.
4. After evaluation but before publish:
- safe to revise rationale/citations and re-evaluate.
5. After publish:
- rollback path is `POST /v1/claims/{id}/unpublish` with audit trace.

## Audit checkpoints
1. Confirm every attached verification source records:
- `source_origin`
- `source_class`
- `publisher`
- reviewer rationale notes
2. Confirm no partisan/advocacy verification sources are attached.
3. Confirm each published claim has rationale + citation notes populated.
4. Confirm `generate_profile_claim_coverage_report` passes for both profiles.
