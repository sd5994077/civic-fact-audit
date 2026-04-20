import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import ClaimEvaluationRead, ErrorResponse, EvaluateClaimRequest
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix='/claims')


@router.post('/{claim_id}/evaluate', response_model=ClaimEvaluationRead, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}})
def evaluate_claim(claim_id: uuid.UUID, payload: EvaluateClaimRequest, db: Session = Depends(get_db)) -> ClaimEvaluationRead:
    evaluation = EvaluationService.evaluate_claim(db, claim_id, payload)
    return ClaimEvaluationRead.model_validate(evaluation, from_attributes=True)
