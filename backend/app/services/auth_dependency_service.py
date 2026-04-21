from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.database import get_db
from app.services.auth_service import AuthIdentity, AuthService


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
