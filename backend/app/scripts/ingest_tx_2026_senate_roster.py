"""
Ingest a Texas 2026 US Senate roster snapshot into candidates.

This script only upserts race metadata (candidate records), not claim evaluations.
Update the ROSTER entries as official filing/certification status changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate
from app.models.enums import RaceStage


@dataclass(frozen=True)
class RosterEntry:
    name: str
    party: str | None
    office: str
    state: str
    election_cycle: int
    race_stage: RaceStage
    roster_status: str
    source_url: str


ROSTER: list[RosterEntry] = [
    RosterEntry(
        name='James Talarico',
        party='Democratic',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary,
        roster_status='primary_nominee_reported',
        source_url='https://www.houstonchronicle.com/politics/election/2026/article/texas-primary-live-updates-21941132.php',
    ),
    RosterEntry(
        name='John Cornyn',
        party='Republican',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        roster_status='runoff_reported',
        source_url='https://www.houstonchronicle.com/politics/election/2026/article/texas-primary-live-updates-21941132.php',
    ),
    RosterEntry(
        name='Ken Paxton',
        party='Republican',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        roster_status='runoff_reported',
        source_url='https://www.houstonchronicle.com/politics/election/2026/article/texas-primary-live-updates-21941132.php',
    ),
]


def _get_existing_candidate(db: Session, entry: RosterEntry) -> Candidate | None:
    return (
        db.execute(
            select(Candidate).where(
                Candidate.name == entry.name,
                Candidate.office == entry.office,
                Candidate.state == entry.state,
                Candidate.election_cycle == entry.election_cycle,
                Candidate.race_stage == entry.race_stage,
            )
        )
        .scalars()
        .first()
    )


def upsert_roster(db: Session, roster: list[RosterEntry]) -> tuple[int, int]:
    created = 0
    updated = 0
    for entry in roster:
        existing = _get_existing_candidate(db, entry)
        if existing is None:
            db.add(
                Candidate(
                    name=entry.name,
                    party=entry.party,
                    office=entry.office,
                    state=entry.state,
                    election_cycle=entry.election_cycle,
                    race_stage=entry.race_stage,
                )
            )
            created += 1
            continue

        changed = False
        if existing.party != entry.party:
            existing.party = entry.party
            changed = True
        if changed:
            updated += 1
    db.commit()
    return created, updated


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created, updated = upsert_roster(db, ROSTER)
        print(f'Ingested Texas 2026 US Senate roster entries. created={created} updated={updated} total={len(ROSTER)}')
        print('Verification sources used for this snapshot:')
        for entry in ROSTER:
            print(f'- {entry.name} ({entry.race_stage}): {entry.source_url} [{entry.roster_status}]')
        print('Independent lane: add an entry once Texas SOS filing/certification confirms an independent candidate.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
