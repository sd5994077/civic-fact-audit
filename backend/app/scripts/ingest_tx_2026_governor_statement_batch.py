"""
Ingest a Texas 2026 Governor statement batch.

This script seeds statement records from known public candidate pages
and events. It is idempotent by (candidate_id, source_url, statement_text).

Add additional rounds as new statements are collected by duplicating
this file as ingest_tx_2026_governor_statement_batch_round2.py, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Statement
from app.models.enums import RaceStage, StatementSourceType


@dataclass(frozen=True)
class StatementSeed:
    candidate_name: str
    office: str
    state: str
    election_cycle: int
    race_stage: RaceStage
    source_type: StatementSourceType
    source_url: str
    statement_text: str
    published_at: datetime
    note: str


CAPTURED_AT = datetime.now(timezone.utc)  # TODO: set a fixed capture timestamp

# TODO: Add one StatementSeed per statement. Remove this example entry.
SEEDS: list[StatementSeed] = [
    # StatementSeed(
    #     candidate_name='Candidate Full Name',
    #     office='Governor',
    #     state='TX',
    #     election_cycle=2026,
    #     race_stage=RaceStage.general,
    #     source_type=StatementSourceType.press_release,
    #     source_url='https://candidate.example.com/page',
    #     statement_text='Exact verbatim quote from the source.',
    #     published_at=CAPTURED_AT,
    #     note='Brief note on where this was found.',
    # ),
]


def ingest_batch(db: Session, seeds: list[StatementSeed]) -> tuple[int, int, int]:
    created = 0
    missing_candidate = 0
    duplicate = 0

    for seed in seeds:
        candidate = db.execute(
            select(Candidate).where(
                Candidate.name == seed.candidate_name,
                Candidate.office == seed.office,
                Candidate.state == seed.state,
                Candidate.election_cycle == seed.election_cycle,
                Candidate.race_stage == seed.race_stage,
            )
        ).scalar_one_or_none()

        if candidate is None:
            print(f'[MISSING candidate] {seed.candidate_name} — run roster script first')
            missing_candidate += 1
            continue

        existing = db.execute(
            select(Statement).where(
                Statement.candidate_id == candidate.id,
                Statement.source_url == seed.source_url,
                Statement.statement_text == seed.statement_text,
            )
        ).scalar_one_or_none()

        if existing is not None:
            duplicate += 1
            continue

        db.add(
            Statement(
                candidate_id=candidate.id,
                source_type=seed.source_type,
                source_url=seed.source_url,
                statement_text=seed.statement_text,
                published_at=seed.published_at,
                note=seed.note,
            )
        )
        created += 1

    db.commit()
    return created, missing_candidate, duplicate


def main() -> None:
    if not SEEDS:
        raise SystemExit('SEEDS is empty. Add statement entries before running.')
    get_engine()
    db = SessionLocal()
    try:
        created, missing, dup = ingest_batch(db, SEEDS)
        print(
            f"'Texas 2026 Governor' statement batch complete. "
            f"created={created} missing_candidate={missing} duplicate={dup}"
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
