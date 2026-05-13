import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.database import get_db
from app.models.enums import RaceStage
from app.schemas.api import CandidateCreate, CandidatePublicRead, CandidateRead, CandidateUpdate, ErrorResponse
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity, AuthService
from app.services.candidate_service import CandidateService

router = APIRouter(prefix='/candidates')


@router.post(
    '',
    response_model=CandidateRead,
    responses={
        400: {'model': ErrorResponse},
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
    },
)
def create_candidate(
    payload: CandidateCreate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> CandidateRead:
    approval_reviewer_id: str | None = None
    if payload.approval_token is not None:
        approval_identity = AuthService.identity_from_dual_control_approval_token(
            db,
            payload.approval_token,
            expected_action='candidate_mutation',
        )
        approval_reviewer_id = approval_identity.reviewer_id
    candidate = CandidateService.create_candidate(
        db,
        payload,
        actor_reviewer_id=identity.reviewer_id,
        approval_reviewer_id=approval_reviewer_id,
    )
    return CandidateRead.model_validate(candidate, from_attributes=True)


@router.get(
    '',
    response_model=list[CandidatePublicRead],
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def list_candidates(
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CandidatePublicRead]:
    candidates = CandidateService.list_candidates(
        db,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
    )
    return [CandidatePublicRead.model_validate(candidate, from_attributes=True) for candidate in candidates]


@router.get(
    '/{candidate_id}',
    response_model=CandidateRead,
    responses={400: {'model': ErrorResponse}, 401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def get_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> CandidateRead:
    _ = identity
    candidate = CandidateService.get_candidate(db, candidate_id)
    return CandidateRead.model_validate(candidate, from_attributes=True)


@router.patch(
    '/{candidate_id}',
    response_model=CandidateRead,
    responses={
        400: {'model': ErrorResponse},
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
    },
)
def update_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> CandidateRead:
    mutable_fields = set(payload.model_fields_set).difference({'approval_token'})
    if not mutable_fields:
        raise AppError('candidate_update_empty', 'Candidate update requires at least one field.', status_code=422)
    approval_reviewer_id: str | None = None
    if payload.approval_token is not None:
        approval_identity = AuthService.identity_from_dual_control_approval_token(
            db,
            payload.approval_token,
            expected_action='candidate_mutation',
        )
        approval_reviewer_id = approval_identity.reviewer_id
    candidate = CandidateService.update_candidate(
        db,
        candidate_id,
        payload,
        actor_reviewer_id=identity.reviewer_id,
        approval_reviewer_id=approval_reviewer_id,
    )
    return CandidateRead.model_validate(candidate, from_attributes=True)
