from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import RaceStage
from app.schemas.api import CandidateCreate, CandidateRead, ErrorResponse
from app.services.candidate_service import CandidateService

router = APIRouter(prefix='/candidates')


@router.post('', response_model=CandidateRead, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}})
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)) -> CandidateRead:
    candidate = CandidateService.create_candidate(db, payload)
    return CandidateRead.model_validate(candidate, from_attributes=True)


@router.get('', response_model=list[CandidateRead], responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}})
def list_candidates(
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CandidateRead]:
    candidates = CandidateService.list_candidates(
        db,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
    )
    return [CandidateRead.model_validate(candidate, from_attributes=True) for candidate in candidates]
