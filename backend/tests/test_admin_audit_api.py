import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity


def _override_admin() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='admin@local', role='admin')


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def test_list_admin_audit_events_requires_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_admin, None)

    client = TestClient(app)
    response = client.get('/v1/admin/audit-events')

    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_list_admin_audit_events_success(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    event_id = uuid.uuid4()
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)

    captured = {}

    def _fake_list(_db, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return [
            {
                'id': event_id,
                'actor_reviewer_id': 'admin@local',
                'action': 'candidate_updated',
                'entity_type': 'candidate',
                'entity_id': 'candidate-1',
                'before_payload': {'name': 'A'},
                'after_payload': {'name': 'B'},
                'metadata': {'source': 'api'},
                'created_at': now,
                'updated_at': now,
            }
        ]

    monkeypatch.setattr('app.api.v1.admin_audit.AdminAuditService.list_events', _fake_list)

    client = TestClient(app)
    response = client.get('/v1/admin/audit-events?action=candidate_updated&entity_type=candidate&limit=10')

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]['id'] == str(event_id)
    assert captured['action'] == 'candidate_updated'
    assert captured['entity_type'] == 'candidate'
    assert captured['limit'] == 10
    app.dependency_overrides.clear()


def test_get_admin_audit_event_success(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    event_id = uuid.uuid4()
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)

    def _fake_get(_db, _event_id):  # type: ignore[no-untyped-def]
        assert _event_id == event_id
        return {
            'id': event_id,
            'actor_reviewer_id': 'admin@local',
            'action': 'claim_published',
            'entity_type': 'claim',
            'entity_id': 'claim-1',
            'before_payload': {'is_published': False},
            'after_payload': {'is_published': True},
            'metadata': {},
            'created_at': now,
            'updated_at': now,
        }

    monkeypatch.setattr('app.api.v1.admin_audit.AdminAuditService.get_event', _fake_get)

    client = TestClient(app)
    response = client.get(f'/v1/admin/audit-events/{event_id}')

    assert response.status_code == 200
    assert response.json()['id'] == str(event_id)
    app.dependency_overrides.clear()
