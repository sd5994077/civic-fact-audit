"""
Generate ingestion KPI snapshot for Texas 2026 U.S. Senate.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_engine
from app.models.entities import Candidate, Claim, Statement
from app.models.enums import RaceStage

TARGET_STATE = 'tx'
TARGET_OFFICE = 'us senate'
TARGET_ELECTION_CYCLE = 2026
TARGET_STAGES: tuple[RaceStage, ...] = (RaceStage.primary, RaceStage.primary_runoff)


def _base_candidate_filter() -> tuple[object, ...]:
    return (
        func.lower(Candidate.state) == TARGET_STATE,
        func.lower(Candidate.office) == TARGET_OFFICE,
        Candidate.election_cycle == TARGET_ELECTION_CYCLE,
        Candidate.race_stage.in_(TARGET_STAGES),
    )


def build_kpi_snapshot(db: Session) -> dict[str, int]:
    candidate_count = db.execute(select(func.count(Candidate.id)).where(*_base_candidate_filter())).scalar_one()
    statement_count = (
        db.execute(select(func.count(Statement.id)).join(Candidate, Candidate.id == Statement.candidate_id).where(*_base_candidate_filter()))
        .scalar_one()
    )
    claim_count = (
        db.execute(
            select(func.count(Claim.id))
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(*_base_candidate_filter())
        )
        .scalar_one()
    )
    fact_checkable_count = (
        db.execute(
            select(func.count(Claim.id))
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(*_base_candidate_filter(), Claim.fact_checkable.is_(True))
        )
        .scalar_one()
    )
    mapped_frame_count = (
        db.execute(
            select(func.count(Claim.id))
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .where(*_base_candidate_filter(), Claim.fact_checkable.is_(True), Claim.issue_frame_id.is_not(None))
        )
        .scalar_one()
    )
    return {
        'candidates': int(candidate_count),
        'statements': int(statement_count),
        'claims': int(claim_count),
        'fact_checkable_claims': int(fact_checkable_count),
        'mapped_issue_frame_claims': int(mapped_frame_count),
    }


def main() -> None:
    get_engine()
    db = SessionLocal()
    try:
        print(json.dumps(build_kpi_snapshot(db), indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()
