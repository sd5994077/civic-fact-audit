from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import CandidateCreate, CandidateRead, ErrorResponse
from app.services.candidate_service import CandidateService

router = APIRouter(prefix='/candidates')


@router.post('', response_model=CandidateRead, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}})
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)) -> CandidateRead:
    candidate = CandidateService.create_candidate(db, payload)
    return CandidateRead.model_validate(candidate, from_attributes=True)
