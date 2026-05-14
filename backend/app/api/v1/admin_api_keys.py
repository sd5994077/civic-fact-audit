import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rate_limiter import ADMIN_WRITE_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.schemas.api import ApiKeyCreateRequest, ApiKeyCreatedResponse, ApiKeyRead, ErrorResponse
from app.services.api_key_service import ApiKeyService
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity

router = APIRouter(prefix='/admin/api-keys')


@router.post(
    '',
    response_model=ApiKeyCreatedResponse,
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def create_api_key(
    payload: ApiKeyCreateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='create_api_key')),
) -> ApiKeyCreatedResponse:
    api_key, plaintext = ApiKeyService.create_key(
        db,
        name=payload.name,
        created_by_reviewer_id=identity.reviewer_id,
    )
    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        created_by_reviewer_id=api_key.created_by_reviewer_id,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        plaintext_key=plaintext,
    )


@router.get(
    '',
    response_model=list[ApiKeyRead],
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}},
)
def list_api_keys(
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> list[ApiKeyRead]:
    _ = identity
    keys = ApiKeyService.list_keys(db)
    return [ApiKeyRead.model_validate(k, from_attributes=True) for k in keys]


@router.delete(
    '/{key_id}',
    response_model=ApiKeyRead,
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
    },
)
def revoke_api_key(
    key_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> ApiKeyRead:
    _ = identity
    api_key = ApiKeyService.revoke_key(db, key_id=key_id)
    return ApiKeyRead.model_validate(api_key, from_attributes=True)
