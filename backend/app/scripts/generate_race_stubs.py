"""
Generate boilerplate script stubs for a new intake profile.

Usage:
    python -m app.scripts.generate_race_stubs --profile-id <profile_id> [--write]

By default prints generated content to stdout for review.
Pass --write to create the files in app/scripts/ (fails if files already exist).

Emits two files:
  ingest_{profile_id}_roster.py        -- fill in ROSTER with candidate entries
  ingest_{profile_id}_statement_batch.py -- fill in SEEDS with statement data

All other pipeline steps (extraction, reviewability backfill, KPI) run
generically via run_generic_pipeline.py once these two files have been
executed against the database.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from app.core.intake_profiles import get_intake_profiles_config
from app.scripts.pipeline_helpers import race_context_from_profile


def _roster_stub(profile_id: str, label: str, state: str, office: str,
                 election_cycle: int, race_stage: str) -> str:
    return textwrap.dedent(f'''\
        """
        Ingest the {label} roster snapshot into candidates.

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


        # TODO: Add one RosterEntry per candidate. Remove this example entry.
        ROSTER: list[RosterEntry] = [
            # RosterEntry(
            #     name='Candidate Full Name',
            #     party='Democratic',  # or 'Republican', 'Independent', None
            #     office={office!r},
            #     state={state!r},
            #     election_cycle={election_cycle},
            #     race_stage=RaceStage.{race_stage},
            #     roster_status='filed_confirmed',  # e.g. filed_confirmed, runoff_reported
            #     source_url='https://sos.example.gov/candidates/race',
            # ),
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
                checked_at = datetime.now(timezone.utc)
                created, updated = CandidateService.upsert_roster_candidates(db, _to_upserts(ROSTER, checked_at))
                print(
                    f'Ingested {label!r} roster entries. '
                    f'created={{created}} updated={{updated}} total={{len(ROSTER)}}'
                )
                for entry in ROSTER:
                    print(f'  {{entry.name}} ({{entry.race_stage}}): {{entry.source_url}} [{{entry.roster_status}}]')
            finally:
                db.close()


        if __name__ == '__main__':
            main()
        ''')


def _statement_batch_stub(profile_id: str, label: str, state: str, office: str,
                          election_cycle: int, race_stage: str) -> str:
    return textwrap.dedent(f'''\
        """
        Ingest a {label} statement batch.

        This script seeds statement records from known public candidate pages
        and events. It is idempotent by (candidate_id, source_url, statement_text).

        Add additional rounds as new statements are collected by duplicating
        this file as ingest_{profile_id}_statement_batch_round2.py, etc.
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
            #     office={office!r},
            #     state={state!r},
            #     election_cycle={election_cycle},
            #     race_stage=RaceStage.{race_stage},
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
                    print(f'[MISSING candidate] {{seed.candidate_name}} — run roster script first')
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
                    f'{label!r} statement batch complete. '
                    f'created={{created}} missing_candidate={{missing}} duplicate={{dup}}'
                )
            finally:
                db.close()


        if __name__ == '__main__':
            main()
        ''')


def _write_stub(path: Path, content: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f'\n{"=" * 70}')
        print(f'# FILE: {path.name}')
        print('=' * 70)
        print(content)
    else:
        if path.exists():
            raise SystemExit(f'File already exists: {path}. Remove it first or edit manually.')
        path.write_text(content, encoding='utf-8')
        print(f'Written: {path}')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate boilerplate script stubs for a new intake profile.'
    )
    parser.add_argument('--profile-id', required=True, help='Profile ID from intake_profiles_v1.json')
    parser.add_argument(
        '--write',
        action='store_true',
        default=False,
        help='Write files to app/scripts/ (default: print to stdout)',
    )
    args = parser.parse_args()

    config = get_intake_profiles_config()
    profile = config.profiles_by_id.get(args.profile_id)
    if profile is None:
        known = list(config.profiles_by_id.keys())
        raise SystemExit(f"Unknown profile_id '{args.profile_id}'. Known profiles: {known}")

    ctx = race_context_from_profile(profile)
    scripts_dir = Path(__file__).resolve().parent
    dry_run = not args.write

    if dry_run:
        print(f'Previewing stubs for: {ctx.label} (profile_id={ctx.profile_id})')
        print('Pass --write to create files in app/scripts/.')

    roster_content = _roster_stub(
        profile_id=ctx.profile_id,
        label=ctx.label,
        state=ctx.state.upper(),
        office=ctx.office.title(),
        election_cycle=ctx.election_cycle,
        race_stage=ctx.race_stage.value,
    )
    _write_stub(
        scripts_dir / f'ingest_{ctx.profile_id}_roster.py',
        roster_content,
        dry_run=dry_run,
    )

    batch_content = _statement_batch_stub(
        profile_id=ctx.profile_id,
        label=ctx.label,
        state=ctx.state.upper(),
        office=ctx.office.title(),
        election_cycle=ctx.election_cycle,
        race_stage=ctx.race_stage.value,
    )
    _write_stub(
        scripts_dir / f'ingest_{ctx.profile_id}_statement_batch.py',
        batch_content,
        dry_run=dry_run,
    )

    if not dry_run:
        print(
            f'\nNext steps:\n'
            f'  1. Fill in ROSTER entries in ingest_{ctx.profile_id}_roster.py\n'
            f'  2. Run: python -m app.scripts.ingest_{ctx.profile_id}_roster\n'
            f'  3. Fill in SEEDS in ingest_{ctx.profile_id}_statement_batch.py\n'
            f'  4. Run: python -m app.scripts.ingest_{ctx.profile_id}_statement_batch\n'
            f'  5. Run: python -m app.scripts.run_generic_pipeline --profile-id {ctx.profile_id}'
        )


if __name__ == '__main__':
    main()
