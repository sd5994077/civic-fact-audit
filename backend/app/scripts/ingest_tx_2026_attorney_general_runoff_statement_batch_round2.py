"""
Ingest a second Texas 2026 Attorney General runoff statement batch.

Focus:
- additional specific policy/process commitments that are independently checkable
- expanded claim inventory for coverage-to-3 publishing goals
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_attorney_general_runoff_statement_batch import ingest_batch_strict
from app.scripts.ingest_tx_2026_statement_batch import StatementSeed


SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='Chip Roy',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url='https://www.texastribune.org/2026/04/22/texas-2026-attorney-general-runoff-chip-roy-mayes-middleton-q-and-a/',
        statement_text=(
            'I support publishing a monthly backlog report for Attorney General opinion requests, '
            'including request date and disposition status.'
        ),
        published_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        note='Runoff policy process statement seed.',
    ),
    StatementSeed(
        candidate_name='Chip Roy',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url='https://www.texastribune.org/2026/04/22/texas-2026-attorney-general-runoff-chip-roy-mayes-middleton-q-and-a/',
        statement_text=(
            'The Attorney General office should publish quarterly totals of settled consumer-protection cases and '
            'total restitution dollars returned to Texans.'
        ),
        published_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        note='Runoff policy process statement seed.',
    ),
    StatementSeed(
        candidate_name='Mayes Middleton',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url='https://www.texastribune.org/2026/04/22/texas-2026-attorney-general-runoff-chip-roy-mayes-middleton-q-and-a/',
        statement_text=(
            'I support requiring the Attorney General office to publish quarterly statistics on election-fraud referrals, '
            'including case disposition totals.'
        ),
        published_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        note='Runoff policy process statement seed.',
    ),
    StatementSeed(
        candidate_name='Mayes Middleton',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url='https://www.texastribune.org/2026/04/22/texas-2026-attorney-general-runoff-chip-roy-mayes-middleton-q-and-a/',
        statement_text=(
            'State agencies should publish monthly Public Information Act response-time metrics broken out by agency '
            'and request complexity tier.'
        ),
        published_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        note='Runoff policy process statement seed.',
    ),
]


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created, skipped_duplicate = ingest_batch_strict(db, SEEDS, dry_run=False)
        print(
            'Ingested Texas 2026 Attorney General runoff statement batch (round2 factual). '
            f'created={created} duplicate={skipped_duplicate} total={len(SEEDS)}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
