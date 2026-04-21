from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import AuthLoginRequest, AuthLoginResponse, AuthMeResponse, ErrorResponse
from app.services.auth_dependency_service import get_current_identity
from app.services.auth_service import AuthIdentity, AuthService

router = APIRouter(prefix='/auth')


@router.post('/login', response_model=AuthLoginResponse, responses={400: {'model': ErrorResponse}, 401: {'model': ErrorResponse}})
def login(payload: AuthLoginRequest, db: Session = Depends(get_db)) -> AuthLoginResponse:
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
