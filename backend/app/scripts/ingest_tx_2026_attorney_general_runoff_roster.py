"""
Ingest a Texas 2026 Attorney General runoff roster snapshot into candidates.

This script upserts candidate race metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.database import SessionLocal, get_engine
from app.models.enums import RaceStage
from app.services.candidate_service import CandidateRosterUpsert, CandidateService


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


SOURCE_URL = 'https://www.texastribune.org/2026/04/22/texas-2026-attorney-general-runoff-chip-roy-mayes-middleton-q-and-a/'

ROSTER: list[RosterEntry] = [
    RosterEntry(
        name='Chip Roy',
        party='Republican',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        roster_status='runoff_reported',
        source_url=SOURCE_URL,
    ),
    RosterEntry(
        name='Mayes Middleton',
        party='Republican',
        office='Attorney General',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        roster_status='runoff_reported',
        source_url=SOURCE_URL,
    ),
]


def _to_upserts(roster: list[RosterEntry], checked_at: datetime) -> list[CandidateRosterUpsert]:
    return [
        CandidateRosterUpsert(
            name=entry.name,
            party=entry.party,
            office=entry.office,
            state=entry.state,
            election_cycle=entry.election_cycle,
            race_stage=entry.race_stage,
            roster_status=entry.roster_status,
            roster_source_url=entry.source_url,
            roster_checked_at=checked_at,
        )
        for entry in roster
    ]


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        checked_at = datetime.now(timezone.utc)
        created, updated = CandidateService.upsert_roster_candidates(db, _to_upserts(ROSTER, checked_at))
        print(
            'Ingested Texas 2026 Attorney General runoff roster entries. '
            f'created={created} updated={updated} total={len(ROSTER)}'
        )
        print('Verification sources used for this snapshot:')
        for entry in ROSTER:
            print(f'- {entry.name} ({entry.race_stage}): {entry.source_url} [{entry.roster_status}]')
    finally:
        db.close()


if __name__ == '__main__':
    main()
