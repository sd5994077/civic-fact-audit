"""
Ingest a third Texas 2026 U.S. Senate statement batch.

Focus:
- candidate-controlled or direct public pages with narrower factual assertions
- statements intended to repopulate the review queue with record-checkable claims
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_statement_batch import StatementSeed, ingest_batch
from app.db.database import SessionLocal, get_engine


SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='James Talarico',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary,
        source_type=StatementSourceType.press_release,
        source_url='https://jamestalarico.com/issue/public-education/',
        statement_text='When I entered the classroom, the Texas Legislature had just gutted the public education budget by $5 billion.',
        published_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        note='Campaign issues page.',
    ),
    StatementSeed(
        candidate_name='John Cornyn',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.johncornyn.com/the-cornyn-trump-record/',
        statement_text='Helped confirm all three of President Trump’s Supreme Court Justices — Neil Gorsuch, Brett Kavanaugh, and Amy Coney Barrett.',
        published_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        note='Campaign record page.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.kenpaxton.com/about',
        statement_text='He’s sued the Biden administration over 100 times.',
        published_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        note='Campaign about page.',
    ),
]


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created, skipped_missing_candidate, skipped_duplicate = ingest_batch(db, SEEDS)
        print(
            'Ingested Texas 2026 statement batch (round3 factual). '
            f'created={created} missing_candidate={skipped_missing_candidate} duplicate={skipped_duplicate} total={len(SEEDS)}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
