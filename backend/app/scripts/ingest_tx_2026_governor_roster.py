"""
Ingest the Texas 2026 Governor roster snapshot into candidates.

This script upserts candidate race metadata only (no claim evaluations).
Update ROSTER entries as official filing/certification status changes.

Source admission: roster_source_url must be a neutral, record-based
source (official SOS filing page, certified results page, or similar).
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


SOURCE_CHECKED_AT = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)

ROSTER: list[RosterEntry] = [
    RosterEntry(
        name='Greg Abbott',
        party='Republican',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        roster_status='general_nominee_reported',
        source_url='https://newtools.cira.state.tx.us/upload/page/10714/docs/2026%20Primary/OFFICIAL%20RESULTS%20-%20REPUBLICAN%20PRIMARY.pdf',
    ),
    RosterEntry(
        name='Gina Hinojosa',
        party='Democratic',
        office='Governor',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.general,
        roster_status='general_nominee_reported',
        source_url='https://newtools.cira.state.tx.us/upload/page/10714/docs/2026%20Primary/Official%20Results%20Democratic%20Primary.pdf',
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
    if not ROSTER:
        raise SystemExit('ROSTER is empty. Add candidate entries before running.')
    get_engine()
    db = SessionLocal()
    try:
        created, updated = CandidateService.upsert_roster_candidates(db, _to_upserts(ROSTER, SOURCE_CHECKED_AT))
        print(
            f'Ingested "Texas 2026 Governor" roster entries. '
            f'created={created} updated={updated} total={len(ROSTER)} '
            f'source_checked_at={SOURCE_CHECKED_AT.isoformat()}'
        )
        for entry in ROSTER:
            print(f'  {entry.name} ({entry.race_stage}): {entry.source_url} [{entry.roster_status}]')
    finally:
        db.close()


if __name__ == '__main__':
    main()
