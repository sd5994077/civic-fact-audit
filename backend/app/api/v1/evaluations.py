import uuid

from fastapi import APIRouter, Depends
from fastapi import Query
from sqlalchemy.orm import Session

from app.core.rate_limiter import ADMIN_WRITE_LIMIT, WRITE_STANDARD_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.models.enums import RaceStage
from app.schemas.api import (
    ClaimEvaluationRead,
    ClaimWorkbenchItem,
    ClaimWorkbenchState,
    ErrorResponse,
    EvaluateClaimRequest,
    ReviewDraftDiffResponse,
    ReviewDraftHistoryItem,
    ReviewDraftResponse,
    ReviewQueueItem,
)
from app.schemas.api import PublishClaimResponse, PublishQueueItem
from app.services.auth_dependency_service import require_admin, require_reviewer_or_admin
from app.services.auth_service import AuthIdentity, AuthService
from app.services.claim_ai_draft_service import ClaimAiDraftService
from app.services.claim_workbench_service import ClaimWorkbenchService
from app.services.evaluation_service import EvaluationService
from app.services.review_draft_service import ReviewDraftService

router = APIRouter(prefix='/claims')


@router.get(
    '/review-queue',
    response_model=list[ReviewQueueItem],
    responses={
        400: {'model': ErrorResponse},
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
    },
)
def review_queue(
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    require_minimum_evidence: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
) -> list[ReviewQueueItem]:
    _ = identity
    rows = EvaluationService.list_review_queue(
        db,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
        require_minimum_evidence=require_minimum_evidence,
        limit=limit,
    )
    return [ReviewQueueItem.model_validate(row) for row in rows]


@router.post(
    '/{claim_id}/evaluate',
    response_model=ClaimEvaluationRead,
    responses={
        400: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def evaluate_claim(
    claim_id: uuid.UUID,
    payload: EvaluateClaimRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(WRITE_STANDARD_LIMIT, endpoint_key='evaluate_claim')),
) -> ClaimEvaluationRead:
    approval_reviewer_id: str | None = None
    if payload.approval_token is not None:
        approval_identity = AuthService.identity_from_dual_control_approval_token(
            db,
            payload.approval_token,
            expected_action='evaluation_overwrite',
        )
        approval_reviewer_id = approval_identity.reviewer_id
    evaluation = EvaluationService.evaluate_claim(
        db,
        claim_id,
        payload,
        reviewer_id=identity.reviewer_id,
        approval_reviewer_id=approval_reviewer_id,
    )
    return ClaimEvaluationRead.model_validate(evaluation, from_attributes=True)


@router.post(
    '/{claim_id}/review-draft',
    response_model=ReviewDraftResponse,
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
        502: {'model': ErrorResponse},
        503: {'model': ErrorResponse},
    },
)
def review_draft(
    claim_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(WRITE_STANDARD_LIMIT, endpoint_key='review_draft')),
) -> ReviewDraftResponse:
    _ = identity
    payload = ReviewDraftService.generate_review_draft(db, claim_id=claim_id)
    ClaimAiDraftService.record_draft(db, claim_id=claim_id, payload=payload)
    return ReviewDraftResponse.model_validate(payload)


@router.get(
    '/{claim_id}/review-drafts',
    response_model=list[ReviewDraftHistoryItem],
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def review_draft_history(
    claim_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
) -> list[ReviewDraftHistoryItem]:
    _ = identity
    rows = ClaimAiDraftService.list_draft_history(db, claim_id=claim_id, limit=limit)
    return [ReviewDraftHistoryItem.model_validate(row) for row in rows]


@router.get(
    '/{claim_id}/review-draft-diff',
    response_model=ReviewDraftDiffResponse,
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def review_draft_diff(
    claim_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
) -> ReviewDraftDiffResponse:
    _ = identity
    payload = ClaimAiDraftService.get_draft_diff(db, claim_id=claim_id)
    return ReviewDraftDiffResponse.model_validate(payload)


@router.get(
    '/workbench',
    response_model=list[ClaimWorkbenchItem],
    responses={400: {'model': ErrorResponse}, 401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}},
)
def claim_workbench(
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    workbench_state: ClaimWorkbenchState | None = Query(default=None),
    include_non_fact_checkable: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
) -> list[ClaimWorkbenchItem]:
    rows = ClaimWorkbenchService.list_workbench(
        db,
        actor_reviewer_id=identity.reviewer_id,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
        include_non_fact_checkable=include_non_fact_checkable,
        workbench_state=workbench_state,
        limit=limit,
    )
    return [ClaimWorkbenchItem.model_validate(row) for row in rows]


@router.get(
    '/publish-queue',
    response_model=list[PublishQueueItem],
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def publish_queue(
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    include_already_published: bool = Query(default=False),
    only_gate_passed: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
) -> list[PublishQueueItem]:
    _ = identity
    rows = EvaluationService.list_publish_queue(
        db,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
        include_already_published=include_already_published,
        only_gate_passed=only_gate_passed,
        limit=limit,
    )
    return [PublishQueueItem.model_validate(row) for row in rows]


@router.post(
    '/{claim_id}/publish',
    response_model=PublishClaimResponse,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 422: {'model': ErrorResponse}, 429: {'model': ErrorResponse}},
)
def publish_claim(
    claim_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='publish_claim')),
) -> PublishClaimResponse:
    claim = EvaluationService.publish_claim(db, claim_id, approver_id=identity.reviewer_id)
    return PublishClaimResponse(
        claim_id=claim.id,
        is_published=claim.is_published,
        published_at=claim.published_at,
        published_by_reviewer_id=claim.published_by_reviewer_id,
    )


@router.post(
    '/{claim_id}/unpublish',
    response_model=PublishClaimResponse,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 429: {'model': ErrorResponse}},
)
def unpublish_claim(
    claim_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='unpublish_claim')),
) -> PublishClaimResponse:
    claim = EvaluationService.unpublish_claim(db, claim_id, approver_id=identity.reviewer_id)
    return PublishClaimResponse(
        claim_id=claim.id,
        is_published=claim.is_published,
        published_at=claim.published_at,
        published_by_reviewer_id=claim.published_by_reviewer_id,
        publish_note=f'Unpublished by {identity.reviewer_id}',
    )
