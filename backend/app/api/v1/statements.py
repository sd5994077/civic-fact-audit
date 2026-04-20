from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import ErrorResponse, StatementCreate, StatementRead
from app.services.statement_service import StatementService

router = APIRouter(prefix='/statements')


@router.post('', response_model=StatementRead, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}})
def create_statement(payload: StatementCreate, db: Session = Depends(get_db)) -> StatementRead:
    statement = StatementService.create_statement(db, payload)
    return StatementRead.model_validate(statement, from_attributes=True)
