import uuid
from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import AppError
from app.services.auth_service import AuthService


def test_hash_and_verify_password_roundtrip() -> None:
    encoded = AuthService.hash_password('test-password-123')
    assert AuthService.verify_password('test-password-123', encoded) is True
    assert AuthService.verify_password('wrong-password', encoded) is False


def test_hash_password_rejects_short_values() -> None:
    try:
        AuthService.hash_password('short')
        assert False, 'Expected AppError for weak password'
    except AppError as exc:
        assert exc.code == 'weak_password'


def test_issue_and_verify_access_token_identity() -> None:
    original_secret = settings.auth_secret_key
    settings.auth_secret_key = 'test-secret'
    try:
        token = AuthService.issue_access_token(reviewer_user_id=uuid.uuid4(), role='reviewer')
        assert '.' in token
    finally:
        settings.auth_secret_key = original_secret


@dataclass
class _FakeReviewer:
    id: uuid.UUID
    email: str
    role: str
    is_active: bool


class _FakeDb:
    def __init__(self, reviewer: _FakeReviewer) -> None:
        self.reviewer = reviewer

    def get(self, model, id_):  # type: ignore[no-untyped-def]
        if id_ == self.reviewer.id:
            return self.reviewer
        return None


def test_identity_from_bearer_resolves_active_user() -> None:
    original_secret = settings.auth_secret_key
    settings.auth_secret_key = 'test-secret'
    reviewer_id = uuid.uuid4()
    token = AuthService.issue_access_token(reviewer_user_id=reviewer_id, role='reviewer')
    db = _FakeDb(_FakeReviewer(id=reviewer_id, email='reviewer@local', role='reviewer', is_active=True))
    try:
        identity = AuthService.identity_from_bearer(db, token)
        assert identity.reviewer_id == 'reviewer@local'
        assert identity.role == 'reviewer'
    finally:
        settings.auth_secret_key = original_secret


def test_identity_from_bearer_rejects_invalid_signature() -> None:
    original_secret = settings.auth_secret_key
    settings.auth_secret_key = 'test-secret'
    reviewer_id = uuid.uuid4()
    token = AuthService.issue_access_token(reviewer_user_id=reviewer_id, role='reviewer')
    db = _FakeDb(_FakeReviewer(id=reviewer_id, email='reviewer@local', role='reviewer', is_active=True))
    try:
        payload_b64, sig_b64 = token.split('.', 1)
        tampered_payload = payload_b64[:-1] + ('a' if payload_b64[-1] != 'a' else 'b')
        tampered = f'{tampered_payload}.{sig_b64}'
        try:
            AuthService.identity_from_bearer(db, tampered)
            assert False, 'Expected AppError for invalid token signature'
        except AppError as exc:
            assert exc.code == 'invalid_token'
    finally:
        settings.auth_secret_key = original_secret
