"""
Ingest a second-pass Texas 2026 US Senate statement batch.

Focus: social posts, interviews, and debate/event materials.
This script is idempotent by (candidate_id, source_url, statement_text).
"""

from __future__ import annotations

import uuid
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


SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='James Talarico',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary,
        source_type=StatementSourceType.social,
        source_url='https://x.com/jamestalarico/status/1903521519155962163',
        statement_text='Jesus loves. Christian Nationalism kills.',
        published_at=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
        note='Candidate social post.',
    ),
    StatementSeed(
        candidate_name='John Cornyn',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.social,
        source_url='https://x.com/JohnCornyn/status/2038257392652100008',
        statement_text='In an asymmetrical war, Iran seeks an edge with its dis-information war.',
        published_at=datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
        note='Candidate social post.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.social,
        source_url='https://x.com/KenPaxtonTX/status/1935360538781040857',
        statement_text='General Mills agrees to remove artificial dyes from its products following my investigation.',
        published_at=datetime(2025, 6, 18, 12, 0, tzinfo=timezone.utc),
        note='Candidate social post.',
    ),
    StatementSeed(
        candidate_name='John Cornyn',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url='https://www.houstonchronicle.com/politics/election/2026/article/senate-republican-primary-results-21318098.php',
        statement_text='Primary runoff context: Cornyn argued Paxton was a risky nominee while seeking a fifth Senate term.',
        published_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
        note='Reported interview/press quote.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.interview,
        source_url='https://www.houstonchronicle.com/politics/election/2026/article/senate-republican-primary-results-21318098.php',
        statement_text='Primary runoff context: Paxton framed the race as a change mandate against Washington incumbency.',
        published_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
        note='Reported interview/press quote.',
    ),
    StatementSeed(
        candidate_name='Ken Paxton',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        source_type=StatementSourceType.debate,
        source_url='https://www.youtube.com/watch?v=cT2fv0ZsfVo',
        statement_text='Campaign event framing U.S. Senate run themes at a Tyler stop.',
        published_at=datetime(2026, 2, 19, 12, 0, tzinfo=timezone.utc),
        note='C-SPAN campaign-stop video metadata; treated as event/debate-class source.',
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


def _statement_exists(db: Session, *, candidate_id: uuid.UUID, source_url: str, statement_text: str) -> bool:
    stmt = (
        db.execute(
            select(Statement.id).where(
                Statement.candidate_id == candidate_id,
                Statement.source_url == source_url,
                Statement.statement_text == statement_text,
            )
        )
        .scalars()
        .first()
    )
    return stmt is not None


def ingest_batch(db: Session, seeds: list[StatementSeed]) -> tuple[int, int, int]:
    created = 0
    skipped_missing_candidate = 0
    skipped_duplicate = 0

    for seed in seeds:
        candidate = _find_candidate(db, seed)
        if candidate is None:
            skipped_missing_candidate += 1
            print(
                f'[SKIP missing candidate] {seed.candidate_name} '
                f'({seed.state} {seed.office} {seed.election_cycle} {seed.race_stage})'
            )
            continue

        if _statement_exists(
            db,
            candidate_id=candidate.id,
            source_url=seed.source_url,
            statement_text=seed.statement_text,
        ):
            skipped_duplicate += 1
            continue

        db.add(
            Statement(
                candidate_id=candidate.id,
                source_type=seed.source_type,
                source_url=seed.source_url,
                statement_text=seed.statement_text,
                published_at=seed.published_at,
            )
        )
        created += 1

    db.commit()
    return created, skipped_missing_candidate, skipped_duplicate


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created, skipped_missing_candidate, skipped_duplicate = ingest_batch(db, SEEDS)
        print(
            'Ingested Texas 2026 statement batch (round2). '
            f'created={created} missing_candidate={skipped_missing_candidate} duplicate={skipped_duplicate} total={len(SEEDS)}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
