import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import AdminAuditEventRead, ErrorResponse
from app.services.admin_audit_service import AdminAuditService
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity

router = APIRouter(prefix='/admin/audit-events')


@router.get(
    '',
    response_model=list[AdminAuditEventRead],
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 422: {'model': ErrorResponse}},
)
def list_admin_audit_events(
    action: str | None = Query(default=None, min_length=1, max_length=128),
    entity_type: str | None = Query(default=None, min_length=1, max_length=128),
    entity_id: str | None = Query(default=None, min_length=1, max_length=255),
    actor_reviewer_id: str | None = Query(default=None, min_length=1, max_length=255),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> list[AdminAuditEventRead]:
    _ = identity
    rows = AdminAuditService.list_events(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_reviewer_id=actor_reviewer_id,
        limit=limit,
    )
    return [AdminAuditEventRead.model_validate(row) for row in rows]


@router.get(
    '/{event_id}',
    response_model=AdminAuditEventRead,
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def get_admin_audit_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> AdminAuditEventRead:
    _ = identity
    row = AdminAuditService.get_event(db, event_id)
    return AdminAuditEventRead.model_validate(row)
