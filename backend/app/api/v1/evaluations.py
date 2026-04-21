import uuid

from fastapi import APIRouter, Depends
from fastapi import Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import RaceStage
from app.schemas.api import ClaimEvaluationRead, ErrorResponse, EvaluateClaimRequest, ReviewQueueItem
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix='/claims')


@router.get(
    '/review-queue',
    response_model=list[ReviewQueueItem],
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def review_queue(
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    require_minimum_evidence: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[ReviewQueueItem]:
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


@router.post('/{claim_id}/evaluate', response_model=ClaimEvaluationRead, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}})
def evaluate_claim(claim_id: uuid.UUID, payload: EvaluateClaimRequest, db: Session = Depends(get_db)) -> ClaimEvaluationRead:
    evaluation = EvaluationService.evaluate_claim(db, claim_id, payload)
    return ClaimEvaluationRead.model_validate(evaluation, from_attributes=True)
