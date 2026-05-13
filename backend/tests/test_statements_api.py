from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.enums import StatementSourceType
from app.services.auth_dependency_service import require_reviewer_or_admin
from app.services.auth_service import AuthIdentity


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def _override_reviewer() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='reviewer@local', role='reviewer')


def test_create_statement_requires_reviewer_or_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)

    client = TestClient(app)
    response = client.post(
        '/v1/statements',
        json={
            'candidate_id': str(uuid.uuid4()),
            'source_type': StatementSourceType.speech.value,
            'source_url': 'https://example.com/speech',
            'statement_text': 'This is a sufficiently long statement text.',
            'published_at': '2026-05-12T00:00:00Z',
        },
    )
    body = response.json()
    assert response.status_code == 401
    assert body['error']['code'] == 'auth_required'
    app.dependency_overrides.clear()


def test_create_statement_allows_reviewer_or_admin(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer

    candidate_id = uuid.uuid4()

    class _Statement:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.candidate_id = candidate_id
            self.source_type = StatementSourceType.speech
            self.source_url = 'https://example.com/speech'
            self.statement_text = 'This is a sufficiently long statement text.'
            self.published_at = datetime(2026, 5, 12, tzinfo=timezone.utc)
            self.created_at = datetime(2026, 5, 12, 1, 0, tzinfo=timezone.utc)

    def _fake_create_statement(_db, payload):  # type: ignore[no-untyped-def]
        assert payload.candidate_id == candidate_id
        return _Statement()

    monkeypatch.setattr('app.api.v1.statements.StatementService.create_statement', _fake_create_statement)

    client = TestClient(app)
    response = client.post(
        '/v1/statements',
        json={
            'candidate_id': str(candidate_id),
            'source_type': StatementSourceType.speech.value,
            'source_url': 'https://example.com/speech',
            'statement_text': 'This is a sufficiently long statement text.',
            'published_at': '2026-05-12T00:00:00Z',
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body['candidate_id'] == str(candidate_id)
    assert body['source_type'] == StatementSourceType.speech.value
    app.dependency_overrides.clear()
