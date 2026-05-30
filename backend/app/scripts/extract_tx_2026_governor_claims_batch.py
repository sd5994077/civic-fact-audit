"""
Extract claims in batch for Texas 2026 Governor statements.

Processes statements in race context that do not yet have claims.
"""

from __future__ import annotations

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage
from app.scripts.pipeline_helpers import RaceContext, run_extraction

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
        extracted_count, skipped_count = run_extraction(db, TARGET_CONTEXT)
        print(
            'Texas 2026 Governor extraction complete. '
            f'claims_created={extracted_count} statements_skipped={skipped_count}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
