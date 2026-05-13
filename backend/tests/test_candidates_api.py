import uuid

from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.database import get_db
from app.main import app
from app.models.enums import RaceStage
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity


def _override_admin() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='admin@local', role='admin')


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def _mock_dual_control_token(monkeypatch, *, reviewer_id: str = 'approver@local') -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        'app.api.v1.candidates.AuthService.identity_from_dual_control_approval_token',
        lambda _db, _token, *, expected_action: AuthIdentity(
            reviewer_user_id=uuid.uuid4(),
            reviewer_id=reviewer_id,
            role='reviewer',
        ),
    )


def _mock_dual_control_token_error(monkeypatch, exc: AppError) -> None:  # type: ignore[no-untyped-def]
    def _raise(_db, _token, *, expected_action):  # type: ignore[no-untyped-def]
        raise exc

    monkeypatch.setattr(
        'app.api.v1.candidates.AuthService.identity_from_dual_control_approval_token',
        _raise,
    )


def test_create_candidate_requires_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_admin, None)
    client = TestClient(app)
    response = client.post(
        '/v1/candidates',
        json={
            'name': 'Candidate A',
            'approval_token': 'approval-token',
            'party': 'Independent',
            'office': 'US Senate',
            'state': 'TX',
            'election_cycle': 2026,
            'race_stage': 'primary',
        },
    )
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_update_candidate_requires_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_admin, None)
    client = TestClient(app)
    response = client.patch(
        f'/v1/candidates/{uuid.uuid4()}',
        json={'approval_token': 'approval-token', 'party': 'Independent'},
    )
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_get_candidate_by_id_response_shape(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    candidate_id = uuid.uuid4()

    class _FakeCandidate:
        def __init__(self) -> None:
            from datetime import datetime, timezone

            self.id = candidate_id
            self.name = 'Candidate A'
            self.party = 'Independent'
            self.office = 'US Senate'
            self.state = 'TX'
            self.election_cycle = 2026
            self.race_stage = RaceStage.primary
            self.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

    monkeypatch.setattr('app.api.v1.candidates.CandidateService.get_candidate', lambda _db, _id: _FakeCandidate())
    client = TestClient(app)
    response = client.get(f'/v1/candidates/{candidate_id}')
    body = response.json()
    assert response.status_code == 200
    assert body['id'] == str(candidate_id)
    assert body['name'] == 'Candidate A'
    app.dependency_overrides.clear()


def test_get_candidate_requires_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_admin, None)
    client = TestClient(app)
    response = client.get(f'/v1/candidates/{uuid.uuid4()}')
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_patch_candidate_forwards_to_service(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    candidate_id = uuid.uuid4()
    captured = {}
    _mock_dual_control_token(monkeypatch, reviewer_id='approver@local')

    class _FakeCandidate:
        def __init__(self) -> None:
            from datetime import datetime, timezone

            self.id = candidate_id
            self.name = 'Candidate A'
            self.party = 'Nonpartisan'
            self.office = 'US Senate'
            self.state = 'TX'
            self.election_cycle = 2026
            self.race_stage = RaceStage.primary
            self.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

    def _fake_update(_db, _candidate_id, payload, *, actor_reviewer_id, approval_reviewer_id=None):  # type: ignore[no-untyped-def]
        captured['id'] = _candidate_id
        captured['fields_set'] = payload.model_fields_set
        captured['actor'] = actor_reviewer_id
        return _FakeCandidate()

    monkeypatch.setattr('app.api.v1.candidates.CandidateService.update_candidate', _fake_update)
    client = TestClient(app)
    response = client.patch(
        f'/v1/candidates/{candidate_id}',
        json={'approval_token': 'approval-token', 'party': 'Nonpartisan'},
    )
    body = response.json()
    assert response.status_code == 200
    assert captured['id'] == candidate_id
    assert 'party' in captured['fields_set']
    assert captured['actor'] == 'admin@local'
    assert body['party'] == 'Nonpartisan'
    app.dependency_overrides.clear()


def test_patch_candidate_empty_payload_returns_422() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    client = TestClient(app)
    response = client.patch(f'/v1/candidates/{uuid.uuid4()}', json={})
    body = response.json()
    assert response.status_code == 422
    assert body['error']['code'] == 'candidate_update_empty'
    app.dependency_overrides.clear()


def test_patch_candidate_returns_409_for_dual_control_conflict(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    candidate_id = uuid.uuid4()
    _mock_dual_control_token(monkeypatch, reviewer_id='admin@local')

    def _fake_update(_db, _candidate_id, payload, *, actor_reviewer_id, approval_reviewer_id=None):  # type: ignore[no-untyped-def]
        assert _candidate_id == candidate_id
        assert actor_reviewer_id == 'admin@local'
        assert approval_reviewer_id == 'admin@local'
        raise AppError(
            'candidate_dual_control_required',
            'Candidate mutations require different reviewers for approval and final mutation.',
            status_code=409,
            details={
                'candidate_id': str(candidate_id),
                'approval_reviewer_id': 'admin@local',
                'applying_reviewer_id': 'admin@local',
                'action': 'candidate_update',
            },
        )

    monkeypatch.setattr('app.api.v1.candidates.CandidateService.update_candidate', _fake_update)

    client = TestClient(app)
    response = client.patch(
        f'/v1/candidates/{candidate_id}',
        json={'approval_token': 'approval-token', 'party': 'Independent'},
    )
    body = response.json()
    assert response.status_code == 409
    assert body['error']['code'] == 'candidate_dual_control_required'
    assert body['error']['details']['candidate_id'] == str(candidate_id)
    assert body['error']['details']['approval_reviewer_id'] == 'admin@local'
    assert body['error']['details']['applying_reviewer_id'] == 'admin@local'
    assert body['error']['details']['action'] == 'candidate_update'
    app.dependency_overrides.clear()


def test_create_candidate_returns_409_for_dual_control_conflict(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    _mock_dual_control_token(monkeypatch, reviewer_id='admin@local')

    def _fake_create(_db, payload, *, actor_reviewer_id, approval_reviewer_id=None):  # type: ignore[no-untyped-def]
        assert actor_reviewer_id == 'admin@local'
        assert approval_reviewer_id == 'admin@local'
        raise AppError(
            'candidate_dual_control_required',
            'Candidate mutations require different reviewers for approval and final mutation.',
            status_code=409,
            details={
                'candidate_id': None,
                'approval_reviewer_id': 'admin@local',
                'applying_reviewer_id': 'admin@local',
                'action': 'candidate_create',
            },
        )

    monkeypatch.setattr('app.api.v1.candidates.CandidateService.create_candidate', _fake_create)
    client = TestClient(app)
    response = client.post(
        '/v1/candidates',
        json={
            'name': 'Candidate A',
            'approval_token': 'approval-token',
            'party': 'Independent',
            'office': 'US Senate',
            'state': 'TX',
            'election_cycle': 2026,
            'race_stage': 'primary',
        },
    )
    body = response.json()
    assert response.status_code == 409
    assert body['error']['code'] == 'candidate_dual_control_required'
    assert body['error']['details']['candidate_id'] is None
    assert body['error']['details']['approval_reviewer_id'] == 'admin@local'
    assert body['error']['details']['applying_reviewer_id'] == 'admin@local'
    assert body['error']['details']['action'] == 'candidate_create'
    app.dependency_overrides.clear()


def test_create_candidate_returns_401_for_invalid_dual_control_token(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    _mock_dual_control_token_error(
        monkeypatch,
        AppError('invalid_dual_control_token', 'Dual-control approval token is invalid.', status_code=401),
    )
    client = TestClient(app)
    response = client.post(
        '/v1/candidates',
        json={
            'name': 'Candidate A',
            'approval_token': 'bad-token',
            'party': 'Independent',
            'office': 'US Senate',
            'state': 'TX',
            'election_cycle': 2026,
            'race_stage': 'primary',
        },
    )
    body = response.json()
    assert response.status_code == 401
    assert body['error']['code'] == 'invalid_dual_control_token'
    app.dependency_overrides.clear()


def test_create_candidate_returns_401_for_expired_dual_control_token(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    _mock_dual_control_token_error(
        monkeypatch,
        AppError('token_expired', 'Authentication token has expired.', status_code=401),
    )
    client = TestClient(app)
    response = client.post(
        '/v1/candidates',
        json={
            'name': 'Candidate A',
            'approval_token': 'expired-token',
            'party': 'Independent',
            'office': 'US Senate',
            'state': 'TX',
            'election_cycle': 2026,
            'race_stage': 'primary',
        },
    )
    body = response.json()
    assert response.status_code == 401
    assert body['error']['code'] == 'token_expired'
    app.dependency_overrides.clear()
