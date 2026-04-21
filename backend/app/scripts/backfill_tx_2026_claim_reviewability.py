"""
Backfill reviewability metadata for Texas 2026 U.S. Senate claims.

Purpose:
- Apply the current fact-checkability heuristic to already-extracted claims.
- Keep non-fact-checkable campaign rhetoric out of evidence/review/compare workflows.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Statement
from app.models.enums import RaceStage
from app.services.claim_reviewability_service import ClaimReviewabilityService


def _load_target_claims(db: Session) -> list[Claim]:
    return (
        db.execute(
            select(Claim)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
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


def run_backfill(db: Session) -> tuple[int, int]:
    claims = _load_target_claims(db)
    updated = 0
    flagged_non_fact_checkable = 0

    for claim in claims:
        prior_metadata = ClaimReviewabilityService.parse_metadata(claim.extraction_metadata)
        updated_metadata = ClaimReviewabilityService.build_extraction_metadata(
            provider=prior_metadata.get('provider', 'local'),
            text=claim.claim_text,
            existing_metadata=prior_metadata,
        )
        if claim.extraction_metadata != updated_metadata:
            claim.extraction_metadata = updated_metadata
            updated += 1

        metadata = ClaimReviewabilityService.parse_metadata(claim.extraction_metadata)
        is_fact_checkable = bool(metadata.get('fact_checkable', True))
        claim.fact_checkable = is_fact_checkable
        if not is_fact_checkable:
            flagged_non_fact_checkable += 1

    db.commit()
    return updated, flagged_non_fact_checkable


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        updated, flagged = run_backfill(db)
        print(
            'Texas 2026 reviewability backfill complete. '
            f'claims_updated={updated} non_fact_checkable={flagged}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
