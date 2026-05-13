"""
Run the ingestion pipeline for any registered intake profile.

Usage:
    python -m app.scripts.run_generic_pipeline --profile-id <profile_id>

Steps performed:
  1. Claim extraction (statements without claims)
  2. Reviewability backfill (fact-checkability heuristic)
  3. KPI snapshot (before/after counts)

Statement ingestion and roster seeding are deliberate manual steps because
they require editorial data (candidate names, statement URLs). See
docs/ONBOARDING_PLAYBOOK.md for the full end-to-end workflow.
"""

from __future__ import annotations

import argparse
import json

from app.core.intake_profiles import get_intake_profiles_config
from app.db.database import SessionLocal, get_engine
from app.scripts.pipeline_helpers import (
    build_kpi_snapshot,
    race_context_from_profile,
    run_extraction,
    run_reviewability_backfill,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run ingestion pipeline for a registered intake profile.'
    )
    parser.add_argument('--profile-id', required=True, help='Profile ID from intake_profiles_v1.json')
    args = parser.parse_args()

    config = get_intake_profiles_config()
    profile = config.profiles_by_id.get(args.profile_id)
    if profile is None:
        known = list(config.profiles_by_id.keys())
        raise SystemExit(f"Unknown profile_id '{args.profile_id}'. Known profiles: {known}")

    ctx = race_context_from_profile(profile)
    print(f'Pipeline start: {ctx.label} (profile_id={ctx.profile_id})')

    get_engine()
    db = SessionLocal()
    try:
        kpi_before = build_kpi_snapshot(db, ctx)

        extracted, skipped = run_extraction(db, ctx)
        print(f'claim_extraction: claims_created={extracted} statements_skipped={skipped}')

        updated, non_fact_checkable = run_reviewability_backfill(db, ctx)
        print(
            f'reviewability_backfill: metadata_updated={updated} '
            f'non_fact_checkable={non_fact_checkable}'
        )

        kpi_after = build_kpi_snapshot(db, ctx)
        print(f'kpi_before={json.dumps(kpi_before)}')
        print(f'kpi_after={json.dumps(kpi_after)}')
        print('Pipeline complete.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
