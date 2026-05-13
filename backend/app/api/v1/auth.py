import hashlib

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rate_limiter import AUTH_LOGIN_LIMIT, DUAL_CONTROL_TOKEN_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.schemas.api import (
    AuthLoginRequest,
    AuthLoginResponse,
    AuthMeResponse,
    DualControlApprovalTokenRequest,
    DualControlApprovalTokenResponse,
    ErrorResponse,
)
from app.services.auth_dependency_service import get_current_identity, require_reviewer_or_admin
from app.services.admin_audit_service import AdminAuditService
from app.services.auth_service import AuthIdentity, AuthService

router = APIRouter(prefix='/auth')


@router.post('/login', response_model=AuthLoginResponse, responses={400: {'model': ErrorResponse}, 401: {'model': ErrorResponse}, 429: {'model': ErrorResponse}})
def login(
    payload: AuthLoginRequest,
    db: Session = Depends(get_db),
    _rl: None = Depends(ip_rate_limit(AUTH_LOGIN_LIMIT, endpoint_key='auth_login')),
) -> AuthLoginResponse:
    reviewer, access_token = AuthService.authenticate_login(
        db,
        email=payload.email,
        password=payload.password,
    )
    return AuthLoginResponse(
        access_token=access_token,
        token_type='bearer',
        reviewer_id=reviewer.email,
        role=reviewer.role,
    )


@router.get('/me', response_model=AuthMeResponse, responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}})
def me(identity: AuthIdentity = Depends(get_current_identity)) -> AuthMeResponse:
    return AuthMeResponse(
        reviewer_id=identity.reviewer_id,
        role=identity.role,
    )


@router.post(
    '/dual-control-approval-token',
    response_model=DualControlApprovalTokenResponse,
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
    },
)
def issue_dual_control_approval_token(
    payload: DualControlApprovalTokenRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(DUAL_CONTROL_TOKEN_LIMIT, endpoint_key='dual_control_token')),
) -> DualControlApprovalTokenResponse:
    action = AuthService.normalize_dual_control_action(payload.action)
    token, expires_at = AuthService.issue_dual_control_approval_token(
        reviewer_user_id=identity.reviewer_user_id,
        role=identity.role,
        action=action,
    )
    token_fingerprint = hashlib.sha256(token.encode('utf-8')).hexdigest()[:16]
    AdminAuditService.record_event(
        db,
        actor_reviewer_id=identity.reviewer_id,
        action='dual_control_approval_token_issued',
        entity_type='auth',
        entity_id=action,
        metadata={
            'source': 'api',
            'action': action,
            'approval_reviewer_id': identity.reviewer_id,
            'role': identity.role,
            'token_expires_at': expires_at.isoformat(),
            'token_fingerprint': token_fingerprint,
        },
    )
    return DualControlApprovalTokenResponse(
        action=action,
        approval_reviewer_id=identity.reviewer_id,
        approval_token=token,
        expires_at=expires_at,
    )
