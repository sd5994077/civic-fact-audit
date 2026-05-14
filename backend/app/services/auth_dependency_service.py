from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.database import get_db
from app.services.api_key_service import ApiKeyService
from app.services.auth_service import AuthIdentity, AuthService


@dataclass(frozen=True)
class ApiKeyIdentity:
    api_key_id: uuid.UUID
    name: str


def get_current_identity(
    authorization: str | None = Header(default=None, alias='Authorization'),
    db: Session = Depends(get_db),
) -> AuthIdentity:
    if authorization is None or not authorization.startswith('Bearer '):
        raise AppError('auth_required', 'Authorization bearer token is required.', status_code=401)
    token = authorization.removeprefix('Bearer ').strip()
    if not token:
        raise AppError('auth_required', 'Authorization bearer token is required.', status_code=401)
    return AuthService.identity_from_bearer(db, token)


def require_reviewer_or_admin(identity: AuthIdentity = Depends(get_current_identity)) -> AuthIdentity:
    if identity.role not in {'reviewer', 'admin'}:
        raise AppError('forbidden', 'Reviewer role is required for this action.', status_code=403)
    return identity


def require_admin(identity: AuthIdentity = Depends(get_current_identity)) -> AuthIdentity:
    if identity.role != 'admin':
        raise AppError('forbidden', 'Admin role is required for this action.', status_code=403)
    return identity


def require_api_key(
    x_api_key: str | None = Header(default=None, alias='X-API-Key'),
    db: Session = Depends(get_db),
) -> ApiKeyIdentity:
    if not x_api_key:
        raise AppError('api_key_required', 'X-API-Key header is required.', status_code=401)
    api_key = ApiKeyService.verify_key(db, plaintext=x_api_key)
    if api_key is None:
        raise AppError('invalid_api_key', 'API key is invalid or revoked.', status_code=401)
    ApiKeyService.record_usage(db, api_key=api_key)
    return ApiKeyIdentity(api_key_id=api_key.id, name=api_key.name)
