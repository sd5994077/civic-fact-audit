"""
Ingest a fourth Texas 2026 U.S. Senate statement batch.

Focus:
- additional record-checkable factual claims for current-profile coverage expansion
- statements intended to support at least three published verified claims per candidate
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_statement_batch import StatementSeed, ingest_batch


SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='James Talarico',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary,
        source_type=StatementSourceType.press_release,
        source_url='https://jamestalarico.com/issue/health-care/',
        statement_text='Texas has the highest uninsured rate in the country.',
        published_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        note='Campaign issue page factual claim seed.',
    ),
    StatementSeed(
        candidate_name='John Cornyn',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.johncornyn.com/the-cornyn-trump-record/',
        statement_text='Cornyn helped author and pass the largest border security package in Texas history in 2006.',
        published_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        note='Campaign record page factual claim seed.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.kenpaxton.com/about',
        statement_text='As Texas Attorney General, Paxton has filed over 30 amicus briefs defending Second Amendment rights.',
        published_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        note='Campaign about page factual claim seed.',
    ),
]


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created, skipped_missing_candidate, skipped_duplicate = ingest_batch(db, SEEDS)
        print(
            'Ingested Texas 2026 statement batch (round4 factual). '
            f'created={created} missing_candidate={skipped_missing_candidate} duplicate={skipped_duplicate} total={len(SEEDS)}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
