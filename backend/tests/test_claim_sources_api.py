import uuid

from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.database import get_db
from app.main import app
from app.models.enums import SourceClass, SourceOrigin
from app.services.auth_dependency_service import require_reviewer_or_admin
from app.services.auth_service import AuthIdentity


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def _override_reviewer() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='reviewer@local', role='reviewer')


def _mock_dual_control_token(monkeypatch, *, reviewer_id: str) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        'app.api.v1.claims.AuthService.identity_from_dual_control_approval_token',
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
        'app.api.v1.claims.AuthService.identity_from_dual_control_approval_token',
        _raise,
    )


def test_add_source_returns_422_for_policy_violation(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer

    def _fake_add_source(_db, _claim_id, _payload):  # type: ignore[no-untyped-def]
        raise AppError(
            'source_admission_policy_violation',
            'Partisan/advocacy sources cannot be added as verification evidence.',
            status_code=422,
            details={'rejection_field': 'source_origin', 'matched_rule': {'field': 'domain'}},
        )

    monkeypatch.setattr('app.api.v1.claims.SourceService.add_source', _fake_add_source)

    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{uuid.uuid4()}/sources',
        json={
            'url': 'https://www.dailykos.com/stories/example',
            'source_class': SourceClass.secondary.value,
            'source_origin': SourceOrigin.verification.value,
            'publisher': 'Daily Kos',
            'quality_score': 0.5,
            'is_direct_candidate_quote': False,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body['error']['code'] == 'source_admission_policy_violation'
    assert body['error']['details']['rejection_field'] == 'source_origin'
    app.dependency_overrides.clear()


def test_add_source_returns_422_for_discovery_link_not_attachable(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer

    def _fake_add_source(_db, _claim_id, _payload):  # type: ignore[no-untyped-def]
        raise AppError(
            'source_discovery_link_not_attachable',
            'Search page: useful for discovery, not attachable evidence.',
            status_code=422,
            details={'rejection_field': 'url', 'page_type': 'search_results'},
        )

    monkeypatch.setattr('app.api.v1.claims.SourceService.add_source', _fake_add_source)

    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{uuid.uuid4()}/sources',
        json={
            'url': 'https://www.congress.gov/search?q=example',
            'source_class': SourceClass.primary.value,
            'source_origin': SourceOrigin.verification.value,
            'publisher': 'Congress.gov',
            'quality_score': 0.5,
            'is_direct_candidate_quote': False,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body['error']['code'] == 'source_discovery_link_not_attachable'
    assert body['error']['details']['page_type'] == 'search_results'
    app.dependency_overrides.clear()


def test_add_source_requires_reviewer_or_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{uuid.uuid4()}/sources',
        json={
            'url': 'https://example.gov/record',
            'source_class': SourceClass.primary.value,
            'source_origin': SourceOrigin.verification.value,
            'quality_score': 0.95,
        },
    )
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_add_sources_bulk_returns_mixed_policy_results(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    _mock_dual_control_token(monkeypatch, reviewer_id='approver@local')

    def _fake_attach_bulk(_db, *, approval_reviewer_id, applying_reviewer_id, items):  # type: ignore[no-untyped-def]
        assert approval_reviewer_id == 'approver@local'
        assert applying_reviewer_id == 'reviewer@local'
        assert len(items) == 2
        return {
            'bulk_operation_id': 'bulk-op-1',
            'total': 2,
            'attached': 1,
            'failed': 1,
            'results': [
                {
                    'claim_id': claim_id,
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary,
                    'source_origin': SourceOrigin.verification,
                    'status': 'attached',
                    'error': None,
                },
                {
                    'claim_id': claim_id,
                    'url': 'https://www.dailykos.com/stories/example',
                    'source_class': SourceClass.secondary,
                    'source_origin': SourceOrigin.verification,
                    'status': 'policy_violation',
                    'error': {
                        'code': 'source_admission_policy_violation',
                        'message': 'Partisan/advocacy sources cannot be added as verification evidence.',
                        'details': {'rejection_field': 'source_origin'},
                    },
                },
            ],
        }

    monkeypatch.setattr('app.api.v1.claims.SourceService.attach_sources_bulk', _fake_attach_bulk)

    client = TestClient(app)
    response = client.post(
        '/v1/claims/sources/bulk',
        json={
            'approval_token': 'approval-token',
            'items': [
                {
                    'claim_id': str(claim_id),
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary.value,
                    'source_origin': SourceOrigin.verification.value,
                    'quality_score': 0.95,
                },
                {
                    'claim_id': str(claim_id),
                    'url': 'https://www.dailykos.com/stories/example',
                    'source_class': SourceClass.secondary.value,
                    'source_origin': SourceOrigin.verification.value,
                    'publisher': 'Daily Kos',
                    'quality_score': 0.4,
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body['bulk_operation_id'] == 'bulk-op-1'
    assert body['total'] == 2
    assert body['attached'] == 1
    assert body['failed'] == 1
    assert body['results'][1]['status'] == 'policy_violation'
    assert body['results'][1]['error']['code'] == 'source_admission_policy_violation'
    app.dependency_overrides.clear()


def test_add_sources_bulk_requires_reviewer_or_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    claim_id = uuid.uuid4()
    client = TestClient(app)
    response = client.post(
        '/v1/claims/sources/bulk',
        json={
            'approval_token': 'approval-token',
            'items': [
                {
                    'claim_id': str(claim_id),
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary.value,
                    'source_origin': SourceOrigin.verification.value,
                    'quality_score': 0.95,
                }
            ],
        },
    )
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_add_sources_bulk_returns_409_for_dual_control_conflict(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    _mock_dual_control_token(monkeypatch, reviewer_id='reviewer@local')

    def _fake_attach_bulk(_db, *, approval_reviewer_id, applying_reviewer_id, items):  # type: ignore[no-untyped-def]
        assert approval_reviewer_id == 'reviewer@local'
        assert applying_reviewer_id == 'reviewer@local'
        assert len(items) == 1
        raise AppError(
            'bulk_attach_dual_control_required',
            'Verification-source bulk attach operations require different reviewers for approval and final mutation.',
            status_code=409,
            details={
                'bulk_operation_id': 'bulk-op-2',
                'approval_reviewer_id': 'reviewer@local',
                'applying_reviewer_id': 'reviewer@local',
                'action': 'bulk_attach_verification_sources',
            },
        )

    monkeypatch.setattr('app.api.v1.claims.SourceService.attach_sources_bulk', _fake_attach_bulk)

    claim_id = uuid.uuid4()
    client = TestClient(app)
    response = client.post(
        '/v1/claims/sources/bulk',
        json={
            'approval_token': 'approval-token',
            'items': [
                {
                    'claim_id': str(claim_id),
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary.value,
                    'source_origin': SourceOrigin.verification.value,
                    'quality_score': 0.95,
                }
            ],
        },
    )
    body = response.json()
    assert response.status_code == 409
    assert body['error']['code'] == 'bulk_attach_dual_control_required'
    assert body['error']['details']['bulk_operation_id'] == 'bulk-op-2'
    assert body['error']['details']['approval_reviewer_id'] == 'reviewer@local'
    assert body['error']['details']['applying_reviewer_id'] == 'reviewer@local'
    assert body['error']['details']['action'] == 'bulk_attach_verification_sources'
    app.dependency_overrides.clear()


def test_add_sources_bulk_mixed_batch_same_reviewer_returns_partial_results(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    _mock_dual_control_token(monkeypatch, reviewer_id='reviewer@local')

    def _fake_attach_bulk(_db, *, approval_reviewer_id, applying_reviewer_id, items):  # type: ignore[no-untyped-def]
        assert approval_reviewer_id == 'reviewer@local'
        assert applying_reviewer_id == 'reviewer@local'
        assert len(items) == 2
        return {
            'bulk_operation_id': 'bulk-op-3',
            'total': 2,
            'attached': 1,
            'failed': 1,
            'results': [
                {
                    'claim_id': claim_id,
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary,
                    'source_origin': SourceOrigin.verification,
                    'status': 'error',
                    'error': {
                        'code': 'bulk_attach_dual_control_required',
                        'message': 'Verification-source bulk attach operations require different reviewers for approval and final mutation.',
                        'details': {'action': 'bulk_attach_verification_sources'},
                    },
                },
                {
                    'claim_id': claim_id,
                    'url': 'https://x.com/candidate/status/1',
                    'source_class': SourceClass.primary,
                    'source_origin': SourceOrigin.candidate,
                    'status': 'attached',
                    'error': None,
                },
            ],
        }

    monkeypatch.setattr('app.api.v1.claims.SourceService.attach_sources_bulk', _fake_attach_bulk)

    client = TestClient(app)
    response = client.post(
        '/v1/claims/sources/bulk',
        json={
            'approval_token': 'approval-token',
            'items': [
                {
                    'claim_id': str(claim_id),
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary.value,
                    'source_origin': SourceOrigin.verification.value,
                    'quality_score': 0.95,
                },
                {
                    'claim_id': str(claim_id),
                    'url': 'https://x.com/candidate/status/1',
                    'source_class': SourceClass.primary.value,
                    'source_origin': SourceOrigin.candidate.value,
                    'quality_score': 0.6,
                    'is_direct_candidate_quote': True,
                },
            ],
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body['bulk_operation_id'] == 'bulk-op-3'
    assert body['attached'] == 1
    assert body['failed'] == 1
    assert body['results'][0]['error']['code'] == 'bulk_attach_dual_control_required'
    assert body['results'][1]['status'] == 'attached'
    app.dependency_overrides.clear()


def test_add_sources_bulk_returns_401_for_invalid_dual_control_token(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    _mock_dual_control_token_error(
        monkeypatch,
        AppError('invalid_dual_control_token', 'Dual-control approval token is invalid.', status_code=401),
    )
    claim_id = uuid.uuid4()
    client = TestClient(app)
    response = client.post(
        '/v1/claims/sources/bulk',
        json={
            'approval_token': 'bad-token',
            'items': [
                {
                    'claim_id': str(claim_id),
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary.value,
                    'source_origin': SourceOrigin.verification.value,
                    'quality_score': 0.95,
                }
            ],
        },
    )
    body = response.json()
    assert response.status_code == 401
    assert body['error']['code'] == 'invalid_dual_control_token'
    app.dependency_overrides.clear()


def test_add_sources_bulk_returns_401_for_expired_dual_control_token(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    _mock_dual_control_token_error(
        monkeypatch,
        AppError('token_expired', 'Authentication token has expired.', status_code=401),
    )
    claim_id = uuid.uuid4()
    client = TestClient(app)
    response = client.post(
        '/v1/claims/sources/bulk',
        json={
            'approval_token': 'expired-token',
            'items': [
                {
                    'claim_id': str(claim_id),
                    'url': 'https://example.gov/record',
                    'source_class': SourceClass.primary.value,
                    'source_origin': SourceOrigin.verification.value,
                    'quality_score': 0.95,
                }
            ],
        },
    )
    body = response.json()
    assert response.status_code == 401
    assert body['error']['code'] == 'token_expired'
    app.dependency_overrides.clear()
