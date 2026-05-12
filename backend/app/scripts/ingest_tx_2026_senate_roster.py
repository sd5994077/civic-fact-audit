"""
Ingest a Texas 2026 US Senate roster snapshot into candidates.

This script only upserts race metadata (candidate records), not claim evaluations.
Update the ROSTER entries as official filing/certification status changes.
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
        print(f'Ingested Texas 2026 US Senate roster entries. created={created} updated={updated} total={len(ROSTER)}')
        print('Verification sources used for this snapshot:')
        for entry in ROSTER:
            print(f'- {entry.name} ({entry.race_stage}): {entry.source_url} [{entry.roster_status}]')
        print('Independent lane: add an entry once Texas SOS filing/certification confirms an independent candidate.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
