"""
Seed real fact-checkable claims for the TX US Senate 2026 primary runoff.

Creates Statements and Claims for John Cornyn and Ken Paxton.
Claims are created in 'draft' status with no evaluation — use the
Claim Workbench in the admin UI to attach sources, run AI draft,
submit evaluations, and publish.

Run from project root:
  docker compose exec -e PYTHONPATH=/app api python -m app.scripts.seed_tx_senate_runoff_claims
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Statement
from app.models.enums import ClaimStatus, RaceStage, StatementSourceType


@dataclass(frozen=True)
class SeedEntry:
    candidate_name: str
    issue_tag: str
    statement_text: str          # full quote / paraphrase in context
    claim_text: str              # the specific, narrow fact-checkable assertion
    source_url: str
    source_type: StatementSourceType
    statement_date: datetime


CLAIMS: list[SeedEntry] = [
    # ── Ken Paxton ──────────────────────────────────────────────────────────
    SeedEntry(
        candidate_name='Ken Paxton',
        issue_tag='Voting Record & Tenure',
        statement_text=(
            'John Cornyn has been in Washington for 14 years or so and I can\'t think of '
            'a single thing he\'s accomplished for our state or even for the country.'
        ),
        claim_text='John Cornyn has been in Washington for approximately 14 years.',
        source_url='https://www.aol.com/ken-paxton-suggests-could-primary-025434160.html',
        source_type=StatementSourceType.interview,
        statement_date=datetime(2025, 4, 1, tzinfo=timezone.utc),
    ),
    SeedEntry(
        candidate_name='Ken Paxton',
        issue_tag='Gun Rights & Public Safety',
        statement_text=(
            'John Cornyn is an anti-gun establishment politician. He worked with Democrats '
            'to pass gun control legislation after Uvalde and he should be held accountable '
            'for that by Texas Republicans.'
        ),
        claim_text=(
            'John Cornyn is anti-gun based on his vote for the Bipartisan Safer Communities Act.'
        ),
        source_url='https://www.keranews.org/texas-news/2025-10-27/how-john-cornyns-historic-gun-safety-bill-has-become-a-reelection-liability',
        source_type=StatementSourceType.interview,
        statement_date=datetime(2025, 10, 1, tzinfo=timezone.utc),
    ),
    SeedEntry(
        candidate_name='Ken Paxton',
        issue_tag='Campaign Finance & Election Integrity',
        statement_text=(
            'ActBlue has allowed donations from people outside of the United States and '
            'from those who have exceeded federal campaign donation limits.'
        ),
        claim_text=(
            'ActBlue allowed donations from people outside the United States and from '
            'donors who exceeded federal campaign contribution limits.'
        ),
        source_url='https://www.fox7austin.com/news/paxton-blocked-from-suing-actblue',
        source_type=StatementSourceType.press_release,
        statement_date=datetime(2025, 9, 1, tzinfo=timezone.utc),
    ),

    # ── John Cornyn ─────────────────────────────────────────────────────────
    SeedEntry(
        candidate_name='John Cornyn',
        issue_tag='Gun Rights & Public Safety',
        statement_text=(
            'The Bipartisan Safer Communities Act does not impose new restrictions on '
            'which firearms can be sold. It changes rules around who can buy them and '
            'how sales are processed.'
        ),
        claim_text=(
            'The Bipartisan Safer Communities Act does not restrict which firearms can be sold.'
        ),
        source_url='https://www.cornyn.senate.gov/bipartisan-safer-communities-act/',
        source_type=StatementSourceType.press_release,
        statement_date=datetime(2022, 6, 25, tzinfo=timezone.utc),
    ),
    SeedEntry(
        candidate_name='John Cornyn',
        issue_tag='Gun Rights & Public Safety',
        statement_text=(
            'The Bipartisan Safer Communities Act is the first major federal gun safety '
            'legislation in nearly three decades.'
        ),
        claim_text=(
            'The Bipartisan Safer Communities Act (2022) is the first major federal gun '
            'law since the 1990s.'
        ),
        source_url='https://www.cornyn.senate.gov/bipartisan-safer-communities-act/',
        source_type=StatementSourceType.press_release,
        statement_date=datetime(2022, 6, 25, tzinfo=timezone.utc),
    ),
    SeedEntry(
        candidate_name='John Cornyn',
        issue_tag='Border & Immigration',
        statement_text=(
            'U.S. Customs and Border Protection are reporting record low crossings '
            'at the southern border.'
        ),
        claim_text=(
            'CBP reported record low illegal crossings at the southern border as of early 2025.'
        ),
        source_url='https://www.cornyn.senate.gov/news/cornyn-statement-on-senate-passage-of-secure-america-act/',
        source_type=StatementSourceType.speech,
        statement_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
    ),
]


def _get_candidate(db: Session, name: str) -> Candidate:
    candidate = db.scalars(
        select(Candidate).where(
            Candidate.name == name,
            Candidate.state == 'TX',
            Candidate.office == 'US Senate',
            Candidate.election_cycle == 2026,
            Candidate.race_stage == RaceStage.primary_runoff,
        )
    ).first()
    if candidate is None:
        raise RuntimeError(
            f'Candidate "{name}" not found in DB for TX US Senate 2026 primary_runoff. '
            'Run the candidates check first: curl http://localhost:8000/api/v1/candidates'
        )
    return candidate


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        created = 0
        skipped = 0

        for entry in CLAIMS:
            candidate = _get_candidate(db, entry.candidate_name)

            # Skip if an identical statement already exists for this candidate + URL
            existing = db.scalars(
                select(Statement).where(
                    Statement.candidate_id == candidate.id,
                    Statement.source_url == entry.source_url,
                    Statement.statement_text == entry.statement_text,
                )
            ).first()
            if existing is not None:
                print(f'  SKIP  [{entry.candidate_name}] {entry.claim_text[:60]}…')
                skipped += 1
                continue

            stmt = Statement(
                candidate_id=candidate.id,
                source_type=entry.source_type,
                source_url=entry.source_url,
                statement_text=entry.statement_text,
                published_at=entry.statement_date,
            )
            db.add(stmt)
            db.flush()

            claim = Claim(
                statement_id=stmt.id,
                claim_text=entry.claim_text,
                issue_tag=entry.issue_tag,
                fact_checkable=True,
                extraction_confidence=1.0,
                extraction_method='manual',
                extraction_metadata='seed_tx_senate_runoff_claims',
                status=ClaimStatus.draft,
            )
            db.add(claim)
            db.flush()

            print(f'  CREATE [{entry.candidate_name}] {entry.claim_text[:70]}…')
            created += 1

        db.commit()
        print(f'\nDone — {created} claim(s) created, {skipped} skipped (already exist).')
        print('\nNext: open http://localhost:3001/admin/ → Claim Workbench to evaluate and publish.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
