from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rate_limiter import ADMIN_WRITE_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.schemas.api import (
    AdminIntakeProfileCreateRequest,
    AdminIntakeProfileUpdateRequest,
    AdminIntakeProfilesResponse,
    ErrorResponse,
)
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity, AuthService
from app.services.intake_profile_service import IntakeProfileService

router = APIRouter(prefix='/admin/intake-profiles')


@router.get(
    '',
    response_model=AdminIntakeProfilesResponse,
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}},
)
def list_intake_profiles(identity: AuthIdentity = Depends(require_admin)) -> AdminIntakeProfilesResponse:
    _ = identity
    return AdminIntakeProfilesResponse.model_validate(IntakeProfileService.list_profiles())


@router.post(
    '',
    response_model=AdminIntakeProfilesResponse,
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def create_intake_profile(
    payload: AdminIntakeProfileCreateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='create_intake_profile')),
) -> AdminIntakeProfilesResponse:
    approval_reviewer_id = None
    if payload.approval_token is not None:
        approval_identity = AuthService.identity_from_dual_control_approval_token(
            db,
            payload.approval_token,
            expected_action='intake_profile_mutation',
        )
        approval_reviewer_id = approval_identity.reviewer_id
    response = IntakeProfileService.create_profile(
        db,
        payload,
        actor_reviewer_id=identity.reviewer_id,
        approval_reviewer_id=approval_reviewer_id,
    )
    return AdminIntakeProfilesResponse.model_validate(response)


@router.patch(
    '/{profile_id}',
    response_model=AdminIntakeProfilesResponse,
    responses={
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def update_intake_profile(
    profile_id: str,
    payload: AdminIntakeProfileUpdateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='update_intake_profile')),
) -> AdminIntakeProfilesResponse:
    approval_reviewer_id = None
    if payload.approval_token is not None:
        approval_identity = AuthService.identity_from_dual_control_approval_token(
            db,
            payload.approval_token,
            expected_action='intake_profile_mutation',
        )
        approval_reviewer_id = approval_identity.reviewer_id
    response = IntakeProfileService.update_profile(
        db,
        profile_id,
        payload,
        actor_reviewer_id=identity.reviewer_id,
        approval_reviewer_id=approval_reviewer_id,
    )
    return AdminIntakeProfilesResponse.model_validate(response)
