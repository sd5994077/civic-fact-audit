"""
Bootstrap provisional issue tags and reviewer evaluations for Texas 2026 claims.

Purpose:
- Make newly extracted claims visible in compare views that require evaluated claims.
- Keep outputs explicitly provisional (`insufficient`) until evidence review is complete.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, ClaimEvaluation, Statement
from app.models.enums import ClaimStatus, RaceStage, Verdict

REVIEWER_ID = 'tx_2026_bootstrap_reviewer'


def _infer_issue_tag(text: str) -> str:
    lowered = text.lower()
    keyword_map: list[tuple[str, str]] = [
        ('border', 'Border & Immigration'),
        ('immigration', 'Border & Immigration'),
        ('inflation', 'Economy'),
        ('tax', 'Economy'),
        ('price', 'Economy'),
        ('health', 'Healthcare'),
        ('drug', 'Healthcare'),
        ('energy', 'Energy'),
        ('oil', 'Energy'),
        ('gas', 'Energy'),
        ('iran', 'Foreign Policy'),
        ('israel', 'Foreign Policy'),
        ('crime', 'Public Safety'),
        ('school', 'Education'),
        ('election', 'Democracy & Elections'),
        ('vote', 'Democracy & Elections'),
    ]
    for keyword, tag in keyword_map:
        if keyword in lowered:
            return tag
    return 'Campaign Messaging'


def _load_target_claims(db: Session) -> list[Claim]:
    latest_eval_subquery = (
        select(ClaimEvaluation.claim_id, func.max(ClaimEvaluation.created_at).label('latest_created_at'))
        .group_by(ClaimEvaluation.claim_id)
        .subquery()
    )
    return (
        db.execute(
            select(Claim)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .outerjoin(latest_eval_subquery, latest_eval_subquery.c.claim_id == Claim.id)
            .where(
                func.lower(Candidate.state) == 'tx',
                func.lower(Candidate.office) == 'us senate',
                Candidate.election_cycle == 2026,
                Candidate.race_stage.in_((RaceStage.primary, RaceStage.primary_runoff)),
            )
            .order_by(Statement.published_at.asc())
        )
        .scalars()
        .all()
    )


def _has_any_evaluation(db: Session, claim_id: uuid.UUID) -> bool:
    row = db.execute(select(ClaimEvaluation.id).where(ClaimEvaluation.claim_id == claim_id)).scalars().first()
    return row is not None


def run_bootstrap(db: Session) -> tuple[int, int]:
    tagged_count = 0
    evaluated_count = 0
    claims = _load_target_claims(db)

    for claim in claims:
        if not claim.issue_tag:
            claim.issue_tag = _infer_issue_tag(claim.claim_text)
            tagged_count += 1

        if _has_any_evaluation(db, claim.id):
            continue

        db.add(
            ClaimEvaluation(
                claim_id=claim.id,
                verdict=Verdict.insufficient,
                confidence=0.4,
                rationale='Provisional bootstrap review: claim requires evidence attachment and human verification.',
                citation_notes='Pending primary + independent secondary source review.',
                reviewer_id=REVIEWER_ID,
            )
        )
        claim.status = ClaimStatus.reviewed
        evaluated_count += 1

    db.commit()
    return tagged_count, evaluated_count


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        tagged_count, evaluated_count = run_bootstrap(db)
        print(
            'Texas 2026 bootstrap claim review complete. '
            f'issue_tags_added={tagged_count} provisional_evaluations_added={evaluated_count}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
