"""
Extract claims in batch for Texas 2026 US Senate statements.

Processes statements in race context that do not yet have claims.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Statement
from app.models.enums import RaceStage
from app.services.claim_extraction_service import ClaimExtractionService
from app.scripts.pipeline_helpers import RaceContext, build_candidate_filter

MAX_CLAIMS_PER_STATEMENT = 5
TARGET_CONTEXT = RaceContext(
    profile_id='tx_2026_senate',
    label='Texas 2026 U.S. Senate',
    state='tx',
    office='us senate',
    election_cycle=2026,
    race_stage=RaceStage.primary,
)
TARGET_CANDIDATE_FILTER = build_candidate_filter(TARGET_CONTEXT)


def _query_unextracted_statement_ids() -> Select[tuple[uuid.UUID]]:
    claim_counts = (
        select(Claim.statement_id, func.count(Claim.id).label('claim_count'))
        .group_by(Claim.statement_id)
        .subquery()
    )
    return (
        select(Statement.id)
        .join(Candidate, Candidate.id == Statement.candidate_id)
        .outerjoin(claim_counts, claim_counts.c.statement_id == Statement.id)
        .where(
            *TARGET_CANDIDATE_FILTER,
            func.coalesce(claim_counts.c.claim_count, 0) == 0,
        )
        .order_by(Statement.published_at.asc())
    )


def run_extraction(db: Session) -> tuple[int, int]:
    statement_ids = db.execute(_query_unextracted_statement_ids()).scalars().all()
    extracted_count = 0
    skipped_count = 0

    for statement_id in statement_ids:
        try:
            claims = ClaimExtractionService.extract_claims(
                db,
                statement_id=statement_id,
                max_claims=MAX_CLAIMS_PER_STATEMENT,
            )
            extracted_count += len(claims)
        except AppError as exc:
            skipped_count += 1
            print(f'[SKIP extraction] statement_id={statement_id} code={exc.code}')
            continue

    return extracted_count, skipped_count


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        extracted_count, skipped_count = run_extraction(db)
        print(
            'Texas 2026 batch extraction complete. '
            f'claims_created={extracted_count} statements_skipped={skipped_count}'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
