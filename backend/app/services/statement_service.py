from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Candidate, Statement
from app.schemas.api import StatementCreate


class StatementService:
    @staticmethod
    def create_statement(db: Session, payload: StatementCreate) -> Statement:
        candidate = db.get(Candidate, payload.candidate_id)
        if candidate is None:
            raise AppError('candidate_not_found', 'Candidate does not exist.', status_code=404)

        statement = Statement(
            candidate_id=payload.candidate_id,
            source_type=payload.source_type,
            source_url=str(payload.source_url),
            statement_text=payload.statement_text.strip(),
            published_at=payload.published_at,
        )
        db.add(statement)
        db.commit()
        db.refresh(statement)
        return statement
