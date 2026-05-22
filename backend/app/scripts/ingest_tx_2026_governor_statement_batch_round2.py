"""
Ingest a second-pass Texas 2026 Governor statement batch.

Focus: objective, record-checkable statements to improve review queue readiness.
This script is idempotent via ingest_batch duplicate checks.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_governor_statement_batch import StatementSeed, ingest_batch


SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='Greg Abbott',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        source_type=StatementSourceType.press_release,
        source_url='https://www.gregabbott.com/governor-abbott-endorsed-by-national-border-patrol-council/',
        statement_text='This past legislative session, he invested more than $3 billion in border security funding for the next two years.',
        published_at=datetime(2026, 1, 14, 0, 0, tzinfo=timezone.utc),
    ),
    StatementSeed(
        candidate_name='Greg Abbott',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        source_type=StatementSourceType.press_release,
        source_url='https://www.gregabbott.com/governor-abbott-raises-over-20-million-in-latest-reporting-period/',
        statement_text='Governor Greg Abbott announced $20,188,882.21 in contributions raised for his campaign in the latest reporting period.',
        published_at=datetime(2025, 7, 16, 0, 0, tzinfo=timezone.utc),
    ),
    StatementSeed(
        candidate_name='Gina Hinojosa',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        source_type=StatementSourceType.press_release,
        source_url='https://ginafortexas.com/2026/05/new-hinojosa-calls-out-texas-public-schools-in-crisis-after-12-years-of-greg-abbott/',
        statement_text='More than 100 schools are shutting down, and over 150 school districts are on four-day weeks.',
        published_at=datetime(2026, 5, 11, 0, 0, tzinfo=timezone.utc),
    ),
    StatementSeed(
        candidate_name='Gina Hinojosa',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        source_type=StatementSourceType.press_release,
        source_url='https://ginafortexas.com/2026/05/hinojosa-rallies-hundreds-of-texans-at-dallas-block-party/',
        statement_text='We have over 100 schools all across this state that are shutting down, including at least fifteen in DFW.',
        published_at=datetime(2026, 5, 17, 0, 0, tzinfo=timezone.utc),
    ),
]


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created, skipped_missing_candidate, skipped_duplicate = ingest_batch(db, SEEDS)
        print(
            "'Texas 2026 Governor' statement batch round2 complete. "
            f'created={created} missing_candidate={skipped_missing_candidate} duplicate={skipped_duplicate} total={len(SEEDS)}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
