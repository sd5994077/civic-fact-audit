import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.rate_limiter import WRITE_STANDARD_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.models.entities import Candidate, Claim, ClaimEvaluation, Statement
from app.models.enums import RaceStage
from app.schemas.api import ErrorResponse, PublicClaimRead
from app.services.auth_dependency_service import ApiKeyIdentity, require_api_key

router = APIRouter(prefix='/public')


def _build_public_claims_query(
    *,
    candidate_id: uuid.UUID | None,
    state: str | None,
    office: str | None,
    election_cycle: int | None,
    race_stage: RaceStage | None,
    limit: int,
):
    latest_eval = (
        select(
            ClaimEvaluation.claim_id,
            ClaimEvaluation.verdict,
            ClaimEvaluation.confidence,
            ClaimEvaluation.rationale,
        )
        .distinct(ClaimEvaluation.claim_id)
        .order_by(ClaimEvaluation.claim_id, ClaimEvaluation.created_at.desc())
        .subquery()
    )

    stmt = (
        select(
            Claim.id.label('claim_id'),
            Claim.claim_text,
            Claim.issue_tag,
            Claim.published_at,
            latest_eval.c.verdict,
            latest_eval.c.confidence,
            latest_eval.c.rationale,
            Candidate.id.label('candidate_id'),
            Candidate.name.label('candidate_name'),
            Candidate.party.label('candidate_party'),
            Candidate.office.label('candidate_office'),
            Candidate.state.label('candidate_state'),
            Candidate.election_cycle,
            Candidate.race_stage,
            Statement.source_url.label('statement_source_url'),
            Statement.published_at.label('statement_published_at'),
        )
        .select_from(Claim)
        .join(Statement, Claim.statement_id == Statement.id)
        .join(Candidate, Statement.candidate_id == Candidate.id)
        .outerjoin(latest_eval, latest_eval.c.claim_id == Claim.id)
        .where(Claim.is_published.is_(True))
        .order_by(Claim.published_at.desc())
        .limit(limit)
    )

    if candidate_id is not None:
        stmt = stmt.where(Candidate.id == candidate_id)
    if state is not None:
        stmt = stmt.where(Candidate.state == state)
    if office is not None:
        stmt = stmt.where(Candidate.office == office)
    if election_cycle is not None:
        stmt = stmt.where(Candidate.election_cycle == election_cycle)
    if race_stage is not None:
        stmt = stmt.where(Candidate.race_stage == race_stage)

    return stmt


@router.get(
    '/claims',
    response_model=list[PublicClaimRead],
    responses={
        401: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def list_public_claims(
    candidate_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _key: ApiKeyIdentity = Depends(require_api_key),
    _rl: None = Depends(ip_rate_limit(WRITE_STANDARD_LIMIT, endpoint_key='public_claims_list')),
) -> list[PublicClaimRead]:
    stmt = _build_public_claims_query(
        candidate_id=candidate_id,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
        limit=limit,
    )
    rows = db.execute(stmt).mappings().all()
    return [PublicClaimRead.model_validate(dict(row)) for row in rows]


@router.get(
    '/claims/{claim_id}',
    response_model=PublicClaimRead,
    responses={
        401: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def get_public_claim(
    claim_id: uuid.UUID,
    db: Session = Depends(get_db),
    _key: ApiKeyIdentity = Depends(require_api_key),
    _rl: None = Depends(ip_rate_limit(WRITE_STANDARD_LIMIT, endpoint_key='public_claims_detail')),
) -> PublicClaimRead:
    stmt = _build_public_claims_query(
        candidate_id=None,
        state=None,
        office=None,
        election_cycle=None,
        race_stage=None,
        limit=1,
    ).where(Claim.id == claim_id)
    row = db.execute(stmt).mappings().first()
    if row is None:
        raise AppError('not_found', 'Published claim not found.', status_code=404)
    return PublicClaimRead.model_validate(dict(row))
