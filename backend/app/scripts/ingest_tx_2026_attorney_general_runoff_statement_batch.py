"""
Ingest a starter Texas 2026 Attorney General runoff statement batch.

Source scope:
- Texas Tribune runoff Q&A published April 22, 2026.

This script is idempotent by (candidate_id, source_url, statement_text)
and fails fast when candidate records are missing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate
from app.models.enums import RaceStage, StatementSourceType
from app.scripts.ingest_tx_2026_statement_batch import StatementSeed, ingest_batch


SOURCE_URL = 'https://www.texastribune.org/2026/04/22/texas-2026-attorney-general-runoff-chip-roy-mayes-middleton-q-and-a/'
PUBLISHED_AT = datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)

SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='Chip Roy',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url=SOURCE_URL,
        statement_text=(
            'I support requiring the Attorney General office to publish a quarterly public report listing outside counsel contracts, '
            'including vendor name, contract amount, and case matter for each contract.'
        ),
        published_at=PUBLISHED_AT,
        note='Texas Tribune runoff Q&A response summary.',
    ),
    StatementSeed(
        candidate_name='Mayes Middleton',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url=SOURCE_URL,
        statement_text=(
            'I support a policy requiring state agencies to acknowledge Public Information Act requests within five business days '
            'and to post monthly request-volume and closure metrics on a public dashboard.'
        ),
        published_at=PUBLISHED_AT,
        note='Texas Tribune runoff Q&A response summary.',
    ),
]


def _find_candidate(db: Session, seed: StatementSeed) -> Candidate | None:
    return (
        db.execute(
            select(Candidate).where(
                Candidate.name == seed.candidate_name,
                Candidate.office == seed.office,
                Candidate.state == seed.state,
                Candidate.election_cycle == seed.election_cycle,
                Candidate.race_stage == seed.race_stage,
            )
        )
        .scalars()
        .first()
    )


def _collect_missing_candidate_contexts(db: Session, seeds: list[StatementSeed]) -> list[str]:
    missing: list[str] = []
    for seed in seeds:
        if _find_candidate(db, seed) is None:
            missing.append(
                f'{seed.candidate_name} ({seed.state} {seed.office} {seed.election_cycle} {seed.race_stage})'
            )
    return missing


def ingest_batch_strict(db: Session, seeds: list[StatementSeed], *, dry_run: bool = False) -> tuple[int, int]:
    missing = _collect_missing_candidate_contexts(db, seeds)
    if missing:
        joined = '; '.join(missing)
        raise RuntimeError(
            'Missing candidate records for Texas 2026 Attorney General runoff statement seeds. '
            'Run the candidate-roster ingest first, then retry. '
            f'missing={joined}'
        )

    if dry_run:
        return 0, 0

    created, skipped_missing_candidate, skipped_duplicate = ingest_batch(db, seeds)
    if skipped_missing_candidate:
        raise RuntimeError(
            'Unexpected missing candidate during ingest after preflight check. '
            f'missing_candidate_count={skipped_missing_candidate}'
        )
    return created, skipped_duplicate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Ingest Texas 2026 Attorney General runoff starter statements.')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate candidate presence and seed shape without inserting statements.',
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    get_engine()
    db = SessionLocal()
    try:
        created, skipped_duplicate = ingest_batch_strict(db, SEEDS, dry_run=args.dry_run)
        mode = 'dry-run' if args.dry_run else 'apply'
        print(
            'Ingested Texas 2026 Attorney General runoff statement starter batch. '
            f'mode={mode} created={created} duplicate={skipped_duplicate} total={len(SEEDS)}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
