from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.entities import ReviewerUser


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _b64url_decode(raw: str) -> bytes:
    padding = '=' * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + padding)


@dataclass(frozen=True)
class AuthIdentity:
    reviewer_user_id: uuid.UUID
    reviewer_id: str
    role: str


class AuthService:
    _HASH_ITERATIONS = 390_000
    _DUAL_CONTROL_TOKEN_USE = 'dual_control_approval'
    _DUAL_CONTROL_ACTIONS = {
        'candidate_mutation',
        'evaluation_overwrite',
        'bulk_attach_verification_sources',
        'intake_profile_mutation',
    }
    _DUAL_CONTROL_TTL_SECONDS = 15 * 60

    @staticmethod
    def hash_password(password: str) -> str:
        if len(password) < 8:
            raise AppError('weak_password', 'Password must be at least 8 characters.', status_code=422)
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), AuthService._HASH_ITERATIONS)
        return f'pbkdf2_sha256${AuthService._HASH_ITERATIONS}${salt}${digest.hex()}'

    @staticmethod
    def verify_password(password: str, encoded_hash: str) -> bool:
        try:
            algorithm, raw_iterations, salt, expected = encoded_hash.split('$', 3)
            if algorithm != 'pbkdf2_sha256':
                return False
            iterations = int(raw_iterations)
        except (ValueError, TypeError):
            return False

        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations).hex()
        return hmac.compare_digest(digest, expected)

    @staticmethod
    def _encode_signed_payload(payload: dict[str, object]) -> str:
        payload_raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
        payload_b64 = _b64url_encode(payload_raw)
        signature = hmac.new(
            settings.auth_secret_key.encode('utf-8'),
            payload_b64.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        return f'{payload_b64}.{_b64url_encode(signature)}'

    @staticmethod
    def issue_access_token(*, reviewer_user_id: uuid.UUID, role: str) -> str:
        exp_epoch = int(time.time()) + (settings.auth_token_ttl_minutes * 60)
        payload = {
            'sub': str(reviewer_user_id),
            'role': role,
            'exp': exp_epoch,
        }
        return AuthService._encode_signed_payload(payload)

    @staticmethod
    def issue_dual_control_approval_token(
        *,
        reviewer_user_id: uuid.UUID,
        role: str,
        action: str,
    ) -> tuple[str, datetime]:
        normalized_action = AuthService.normalize_dual_control_action(action)
        exp_epoch = int(time.time()) + AuthService._DUAL_CONTROL_TTL_SECONDS
        payload = {
            'sub': str(reviewer_user_id),
            'role': role,
            'exp': exp_epoch,
            'token_use': AuthService._DUAL_CONTROL_TOKEN_USE,
            'action': normalized_action,
        }
        token = AuthService._encode_signed_payload(payload)
        return token, datetime.fromtimestamp(exp_epoch, tz=timezone.utc)

    @staticmethod
    def _verify_signed_token(token: str) -> dict[str, object]:
        try:
            payload_b64, sig_b64 = token.split('.', 1)
        except ValueError as exc:
            raise AppError('invalid_token', 'Authentication token is malformed.', status_code=401) from exc

        expected_sig = hmac.new(
            settings.auth_secret_key.encode('utf-8'),
            payload_b64.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise AppError('invalid_token', 'Authentication token signature is invalid.', status_code=401)

        try:
            payload = json.loads(_b64url_decode(payload_b64).decode('utf-8'))
        except (ValueError, json.JSONDecodeError) as exc:
            raise AppError('invalid_token', 'Authentication token payload is invalid.', status_code=401) from exc

        if not isinstance(payload, dict):
            raise AppError('invalid_token', 'Authentication token payload is invalid.', status_code=401)

        exp = payload.get('exp')
        if not isinstance(exp, int) or exp < int(time.time()):
            raise AppError('token_expired', 'Authentication token has expired.', status_code=401)
        return payload

    @staticmethod
    def normalize_dual_control_action(action: str) -> str:
        normalized = action.strip()
        if normalized not in AuthService._DUAL_CONTROL_ACTIONS:
            raise AppError(
                'invalid_dual_control_action',
                'Dual-control action is not supported.',
                status_code=422,
                details={'allowed_actions': sorted(AuthService._DUAL_CONTROL_ACTIONS)},
            )
        return normalized

    @staticmethod
    def normalize_reviewer_id(reviewer_id: str | None) -> str | None:
        if reviewer_id is None:
            return None
        normalized = reviewer_id.strip().lower()
        if not normalized:
            return None
        return normalized

    @staticmethod
    def resolve_active_reviewer_id(
        db: Session,
        reviewer_id: str | None,
        *,
        allowed_roles: set[str] | None = None,
    ) -> str | None:
        normalized = AuthService.normalize_reviewer_id(reviewer_id)
        if normalized is None:
            return None
        if not hasattr(db, 'execute'):
            return None
        try:
            reviewer = (
                db.execute(select(ReviewerUser).where(func.lower(ReviewerUser.email) == normalized))
                .scalars()
                .first()
            )
        except Exception:
            return None
        if reviewer is None or not reviewer.is_active:
            return None
        if allowed_roles is not None and reviewer.role not in allowed_roles:
            return None
        return normalized

    @staticmethod
    def _identity_from_payload_subject(db: Session, payload: dict[str, object]) -> AuthIdentity:
        raw_sub = payload.get('sub')
        if not isinstance(raw_sub, str):
            raise AppError('invalid_token', 'Authentication token subject is invalid.', status_code=401)
        try:
            reviewer_user_id = uuid.UUID(raw_sub)
        except ValueError as exc:
            raise AppError('invalid_token', 'Authentication token subject is invalid.', status_code=401) from exc

        reviewer = db.get(ReviewerUser, reviewer_user_id)
        if reviewer is None or not reviewer.is_active:
            raise AppError('auth_failed', 'Reviewer account is not active.', status_code=403)

        return AuthIdentity(
            reviewer_user_id=reviewer.id,
            reviewer_id=reviewer.email,
            role=reviewer.role,
        )

    @staticmethod
    def authenticate_login(db: Session, *, email: str, password: str) -> tuple[ReviewerUser, str]:
        reviewer = (
            db.execute(select(ReviewerUser).where(func.lower(ReviewerUser.email) == email.strip().lower()))
            .scalars()
            .first()
        )
        if reviewer is None or not reviewer.is_active:
            raise AppError('auth_failed', 'Invalid email or password.', status_code=401)
        if not AuthService.verify_password(password, reviewer.password_hash):
            raise AppError('auth_failed', 'Invalid email or password.', status_code=401)
        token = AuthService.issue_access_token(reviewer_user_id=reviewer.id, role=reviewer.role)
        return reviewer, token

    @staticmethod
    def identity_from_bearer(db: Session, bearer_token: str) -> AuthIdentity:
        payload = AuthService._verify_signed_token(bearer_token.strip())
        token_use = payload.get('token_use')
        if token_use is not None:
            raise AppError(
                'invalid_token',
                'Authentication token is not valid for bearer auth.',
                status_code=401,
                details={'token_use': token_use},
            )
        return AuthService._identity_from_payload_subject(db, payload)

    @staticmethod
    def identity_from_dual_control_approval_token(
        db: Session,
        approval_token: str,
        *,
        expected_action: str,
    ) -> AuthIdentity:
        payload = AuthService._verify_signed_token(approval_token.strip())
        if payload.get('token_use') != AuthService._DUAL_CONTROL_TOKEN_USE:
            raise AppError(
                'invalid_dual_control_token',
                'Dual-control approval token is invalid.',
                status_code=401,
            )
        action = payload.get('action')
        if action != expected_action:
            raise AppError(
                'dual_control_token_action_mismatch',
                'Dual-control approval token action does not match this operation.',
                status_code=409,
                details={
                    'expected_action': expected_action,
                    'provided_action': action,
                },
            )
        return AuthService._identity_from_payload_subject(db, payload)
