from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.rate_limiter import ADMIN_WRITE_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.schemas.api import ErrorResponse, NotificationEventRead, NotificationTestRequest
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity
from app.services.notification_service import NotificationService

router = APIRouter(prefix='/admin/notifications')


@router.get(
    '',
    response_model=list[NotificationEventRead],
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
    },
)
def list_notifications(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> list[NotificationEventRead]:
    _ = identity
    events = NotificationService.list_events(db, limit=limit, offset=offset, status=status)
    return [NotificationEventRead.model_validate(e, from_attributes=True) for e in events]


@router.post(
    '/test',
    response_model=NotificationEventRead,
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def test_notification(
    payload: NotificationTestRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='test_notification')),
) -> NotificationEventRead:
    _ = identity
    event = NotificationService.test_notification(db, reviewer_id=payload.reviewer_id, event_type=payload.event_type)
    return NotificationEventRead.model_validate(event, from_attributes=True)
