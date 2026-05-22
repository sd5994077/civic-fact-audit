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
from urllib.parse import urlparse

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


SOURCE_CHECKED_AT = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
_DISALLOWED_GENERIC_SOURCE_PATHS = frozenset({'', '/', '/press/', '/speeches/', '/issues/', '/news/'})

SEEDS: list[StatementSeed] = [
    StatementSeed(
        candidate_name='Greg Abbott',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        source_type=StatementSourceType.press_release,
        source_url='https://www.gregabbott.com/governor-abbott-announces-bid-for-re-election-in-houston/',
        statement_text='Governor Abbott Announces Bid for Re-Election in Houston',
        published_at=datetime(2025, 11, 9, 0, 0, tzinfo=timezone.utc),
    ),
    StatementSeed(
        candidate_name='Gina Hinojosa',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        source_type=StatementSourceType.press_release,
        source_url='https://ginafortexas.com/2025/10/rep-gina-hinojosa-launches-campaign-for-governor-of-texas/',
        statement_text='Rep. Gina Hinojosa Launches Campaign for Governor of Texas',
        published_at=datetime(2025, 10, 15, 0, 0, tzinfo=timezone.utc),
    ),
]


def _validate_source_url(url: str) -> None:
    parsed = urlparse(url.strip())
    path = parsed.path.strip().lower()
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f'Invalid source_url: {url}')
    if path in _DISALLOWED_GENERIC_SOURCE_PATHS:
        raise ValueError(
            f'Generic landing-page source_url is not allowed for statement capture: {url}. '
            'Use a claim-level URL.'
        )


def ingest_batch(db: Session, seeds: list[StatementSeed]) -> tuple[int, int, int]:
    created = 0
    missing_candidate = 0
    duplicate = 0

    for seed in seeds:
        _validate_source_url(seed.source_url)

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
            print(f'[MISSING candidate] {seed.candidate_name} - run roster script first')
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
            f'created={created} missing_candidate={missing} duplicate={dup}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
