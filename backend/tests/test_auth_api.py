import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.services.auth_dependency_service import require_reviewer_or_admin
from app.services.auth_service import AuthIdentity


def _override_reviewer() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='reviewer@local', role='reviewer')


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def test_issue_dual_control_token_requires_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    client = TestClient(app)
    response = client.post('/v1/auth/dual-control-approval-token', json={'action': 'candidate_mutation'})
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_issue_dual_control_token_returns_token(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer

    captured = {}
    expires_at = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        'app.api.v1.auth.AuthService.issue_dual_control_approval_token',
        lambda *, reviewer_user_id, role, action: ('approval-token', expires_at),
    )
    monkeypatch.setattr(
        'app.api.v1.auth.AdminAuditService.record_event',
        lambda _db, **kwargs: captured.update(kwargs),
    )

    client = TestClient(app)
    response = client.post('/v1/auth/dual-control-approval-token', json={'action': 'candidate_mutation'})
    body = response.json()

    assert response.status_code == 200
    assert body['action'] == 'candidate_mutation'
    assert body['approval_reviewer_id'] == 'reviewer@local'
    assert body['approval_token'] == 'approval-token'
    assert body['expires_at'] == expires_at.isoformat().replace('+00:00', 'Z')
    assert captured['action'] == 'dual_control_approval_token_issued'
    assert captured['entity_type'] == 'auth'
    assert captured['entity_id'] == 'candidate_mutation'
    assert captured['metadata']['approval_reviewer_id'] == 'reviewer@local'
    assert captured['metadata']['action'] == 'candidate_mutation'
    app.dependency_overrides.clear()
