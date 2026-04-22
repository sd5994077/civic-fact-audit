"""
Backfill claim evidence bundles for Texas 2026 U.S. Senate claims.

Purpose:
- Create non-curated bundles from the current statement/source model.
- Separate stance links from verification links for compare/public display.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Statement
from app.models.enums import RaceStage
from app.services.evidence_bundle_service import EvidenceBundleService

TARGET_STAGES: tuple[RaceStage, ...] = (RaceStage.primary, RaceStage.primary_runoff)


def _load_target_claim_ids(db: Session) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(Claim.id)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(
                func.lower(Candidate.state) == 'tx',
                func.lower(Candidate.office) == 'us senate',
                Candidate.election_cycle == 2026,
                Candidate.race_stage.in_(TARGET_STAGES),
                Claim.fact_checkable.is_(True),
            )
            .order_by(Statement.published_at.asc(), Claim.created_at.asc())
        )
        .scalars()
        .all()
    )


def run_backfill(db: Session) -> dict[str, int]:
    claim_ids = _load_target_claim_ids(db)
    bundle_count = 0
    stance_link_count = 0
    verification_link_count = 0

    for claim_id in claim_ids:
        bundle = EvidenceBundleService.sync_claim_bundle(db, claim_id)
        bundle_count += 1
        stance_link_count += len(bundle.stance_links)
        verification_link_count += len(bundle.verification_links)

    return {
        'claims_processed': len(claim_ids),
        'bundles_synced': bundle_count,
        'stance_links': stance_link_count,
        'verification_links': verification_link_count,
    }


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        stats = run_backfill(db)
        print(
            'Texas 2026 evidence bundle backfill complete. '
            f"claims_processed={stats['claims_processed']} "
            f"bundles_synced={stats['bundles_synced']} "
            f"stance_links={stats['stance_links']} "
            f"verification_links={stats['verification_links']}"
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
