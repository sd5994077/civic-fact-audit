from sqlalchemy.orm import Session

from app.models.entities import Candidate
from app.schemas.api import CandidateCreate


class CandidateService:
    @staticmethod
    def create_candidate(db: Session, payload: CandidateCreate) -> Candidate:
        candidate = Candidate(
            name=payload.name.strip(),
            party=payload.party,
            office=payload.office,
            state=payload.state,
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate
