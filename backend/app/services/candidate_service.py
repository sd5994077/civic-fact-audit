from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.entities import Candidate
from app.models.enums import RaceStage
from app.schemas.api import CandidateCreate


class CandidateService:
    @staticmethod
    def _build_candidate_query(
        *,
        state: str | None,
        office: str | None,
        election_cycle: int | None,
        race_stage: RaceStage | None,
    ) -> Select[tuple[Candidate]]:
        query = select(Candidate)
        filters: list[object] = []
        if state is not None:
            filters.append(func.lower(Candidate.state) == state.strip().lower())
        if office is not None:
            filters.append(func.lower(Candidate.office) == office.strip().lower())
        if election_cycle is not None:
            filters.append(Candidate.election_cycle == election_cycle)
        if race_stage is not None:
            filters.append(Candidate.race_stage == race_stage)
        if filters:
            query = query.where(*filters)
        return query.order_by(Candidate.name.asc())

    @staticmethod
    def create_candidate(db: Session, payload: CandidateCreate) -> Candidate:
        candidate = Candidate(
            name=payload.name.strip(),
            party=payload.party,
            office=payload.office,
            state=payload.state,
            election_cycle=payload.election_cycle,
            race_stage=payload.race_stage,
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate

    @staticmethod
    def list_candidates(
        db: Session,
        *,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
    ) -> list[Candidate]:
        query = CandidateService._build_candidate_query(
            state=state,
            office=office,
            election_cycle=election_cycle,
            race_stage=race_stage,
        )
        return db.execute(query).scalars().all()
