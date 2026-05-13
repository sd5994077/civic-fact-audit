import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.moderation_policy import get_moderation_policy
from app.db.database import get_db
from app.schemas.api import AdminAuditEventRead, ErrorResponse, ModerationRiskItem, ModerationRiskResponse
from app.services.admin_audit_service import AdminAuditService
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity

router = APIRouter(prefix='/admin')


@router.get(
    '/moderation-risk',
    response_model=ModerationRiskResponse,
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 422: {'model': ErrorResponse}},
)
def get_moderation_risk(
    window_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> ModerationRiskResponse:
    _ = identity
    policy = get_moderation_policy()
    risks = AdminAuditService.get_moderation_risk(db, window_days=window_days, limit=limit)
    return ModerationRiskResponse(
        risks=[ModerationRiskItem.model_validate(r) for r in risks],
        policy_version=policy.version,
        window_days=window_days,
    )


@router.get(
    '/audit-events',
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
    '/audit-events/{event_id}',
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
