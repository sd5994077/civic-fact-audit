from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rate_limiter import ADMIN_WRITE_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.schemas.api import ErrorResponse, StatementCreate, StatementRead
from app.services.auth_dependency_service import require_reviewer_or_admin
from app.services.auth_service import AuthIdentity
from app.services.statement_service import StatementService

router = APIRouter(prefix='/statements')


@router.post(
    '',
    response_model=StatementRead,
    responses={
        400: {'model': ErrorResponse},
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def create_statement(
    payload: StatementCreate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='create_statement')),
) -> StatementRead:
    _ = identity
    statement = StatementService.create_statement(db, payload)
    return StatementRead.model_validate(statement, from_attributes=True)
