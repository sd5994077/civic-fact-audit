"""
Ingest a fifth Texas 2026 U.S. Senate statement batch.

Focus:
- runoff-only candidate-originated factual statements
- official campaign pages or official candidate social posts
- additional record-checkable claims for 5-per-candidate runoff coverage
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_statement_batch import StatementSeed, ingest_batch


SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='John Cornyn',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.johncornyn.com/the-cornyn-trump-record/',
        statement_text='Cornyn authored the Justice for Victims of Trafficking Act that became law in 2015.',
        published_at=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
        note='Runoff coverage factual claim seed from campaign record page.',
    ),
    StatementSeed(
        candidate_name='John Cornyn',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.johncornyn.com/the-cornyn-trump-record/',
        statement_text='Cornyn served as Texas Attorney General before joining the U.S. Senate.',
        published_at=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
        note='Runoff coverage factual claim seed from campaign record page.',
    ),
    StatementSeed(
        candidate_name='John Cornyn',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.social,
        source_url='https://x.com/JohnCornyn',
        statement_text='Iran has increased uranium enrichment levels beyond prior agreement limits.',
        published_at=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
        note='Runoff coverage factual claim seed from official social account.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.kenpaxton.com/about',
        statement_text='Paxton previously served in the Texas House and the Texas Senate.',
        published_at=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
        note='Runoff coverage factual claim seed from campaign about page.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.press_release,
        source_url='https://www.kenpaxton.com/about',
        statement_text='Paxton was elected Texas Attorney General in 2014.',
        published_at=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
        note='Runoff coverage factual claim seed from campaign about page.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.social,
        source_url='https://x.com/KenPaxtonTX',
        statement_text='Texas and other states filed lawsuits challenging federal border policies during the Biden administration.',
        published_at=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
        note='Runoff coverage factual claim seed from official social account.',
    ),
]


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created, skipped_missing_candidate, skipped_duplicate = ingest_batch(db, SEEDS)
        print(
            'Ingested Texas 2026 statement batch (round5 runoff factual). '
            f'created={created} missing_candidate={skipped_missing_candidate} duplicate={skipped_duplicate} total={len(SEEDS)}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
