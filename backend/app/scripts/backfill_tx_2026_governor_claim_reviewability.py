"""
Backfill reviewability metadata for Texas 2026 Governor claims.
"""

from __future__ import annotations

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage
from app.scripts.pipeline_helpers import RaceContext, run_reviewability_backfill

TARGET_CONTEXT = RaceContext(
    profile_id='tx_2026_governor',
    label='Texas 2026 Governor',
    state='tx',
    office='governor',
    election_cycle=2026,
    race_stage=RaceStage.general,
)


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        updated, flagged = run_reviewability_backfill(db, TARGET_CONTEXT)
        print(
            'Texas 2026 Governor reviewability backfill complete. '
            f'claims_updated={updated} non_fact_checkable={flagged}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
