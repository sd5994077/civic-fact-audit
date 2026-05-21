import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.core.errors import AppError
from app.models.enums import ClaimStatus
from app.services.auth_dependency_service import require_reviewer_or_admin
from app.services.auth_service import AuthIdentity


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def _override_reviewer() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='reviewer@local', role='reviewer')


def test_extract_claims_requires_reviewer_or_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    client = TestClient(app)
    response = client.post(
        '/v1/claims/extract',
        json={
            'statement_id': str(uuid.uuid4()),
            'max_claims': 5,
        },
    )
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_extract_claims_allows_reviewer_auth(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    statement_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    class _Claim:
        def __init__(self) -> None:
            self.id = claim_id
            self.statement_id = statement_id
            self.claim_text = 'Claim text'
            self.issue_tag = 'economy'
            self.extraction_confidence = 0.91
            self.extraction_method = 'llm'
            self.status = ClaimStatus.draft
            self.is_published = False
            self.published_at = None
            self.published_by_reviewer_id = None
            self.created_at = datetime.now(timezone.utc)

    def _fake_extract_claims(_db, incoming_statement_id, incoming_max_claims):  # type: ignore[no-untyped-def]
        assert incoming_statement_id == statement_id
        assert incoming_max_claims == 5
        return [_Claim()]

    monkeypatch.setattr('app.api.v1.claims.ClaimExtractionService.extract_claims', _fake_extract_claims)

    client = TestClient(app)
    response = client.post(
        '/v1/claims/extract',
        json={
            'statement_id': str(statement_id),
            'max_claims': 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body['statement_id'] == str(statement_id)
    assert len(body['created_claims']) == 1
    assert body['created_claims'][0]['id'] == str(claim_id)
    app.dependency_overrides.clear()


def test_list_sources_requires_reviewer_or_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    client = TestClient(app)
    response = client.get(f'/v1/claims/{uuid.uuid4()}/sources')
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_list_sources_allows_reviewer_auth(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    class _Source:
        def __init__(self) -> None:
            self.id = source_id
            self.claim_id = claim_id
            self.url = 'https://example.com/source'
            self.source_class = 'primary'
            self.source_origin = 'verification'
            self.publisher = 'Example'
            self.quality_score = 0.8
            self.created_at = now

    from app.models.enums import SourceClass, SourceOrigin

    src = _Source()
    src.source_class = SourceClass.primary
    src.source_origin = SourceOrigin.verification
    monkeypatch.setattr('app.api.v1.claims.SourceService.list_sources', lambda _db, _claim_id: [src])

    client = TestClient(app)
    response = client.get(f'/v1/claims/{claim_id}/sources')
    assert response.status_code == 200
    body = response.json()
    assert body['claim_id'] == str(claim_id)
    assert len(body['sources']) == 1
    assert body['sources'][0]['id'] == str(source_id)
    app.dependency_overrides.clear()


def test_delete_source_allows_reviewer_auth(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    class _Source:
        def __init__(self) -> None:
            self.id = source_id
            self.claim_id = claim_id
            self.url = 'https://example.com/source'
            self.publisher = 'Example'
            self.quality_score = 0.8
            self.created_at = now

    from app.models.enums import SourceClass, SourceOrigin

    src = _Source()
    src.source_class = SourceClass.primary
    src.source_origin = SourceOrigin.verification

    captured: dict[str, object] = {}

    def _fake_delete_source(_db, *, claim_id, source_id, reviewer_id):  # type: ignore[no-untyped-def]
        captured['claim_id'] = claim_id
        captured['source_id'] = source_id
        captured['reviewer_id'] = reviewer_id
        return [src]

    monkeypatch.setattr('app.api.v1.claims.SourceService.delete_source', _fake_delete_source)

    client = TestClient(app)
    response = client.delete(f'/v1/claims/{claim_id}/sources/{source_id}')
    assert response.status_code == 200
    body = response.json()
    assert body['claim_id'] == str(claim_id)
    assert len(body['sources']) == 1
    assert captured['reviewer_id'] == 'reviewer@local'
    app.dependency_overrides.clear()


def test_delete_source_returns_409_when_published_block(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()

    def _fake_delete_source(_db, *, claim_id, source_id, reviewer_id):  # type: ignore[no-untyped-def]
        raise AppError(
            'source_delete_not_allowed_for_published_claim',
            'Sources cannot be deleted after a claim is published.',
            status_code=409,
            details={'claim_id': str(claim_id), 'source_id': str(source_id)},
        )

    monkeypatch.setattr('app.api.v1.claims.SourceService.delete_source', _fake_delete_source)

    client = TestClient(app)
    response = client.delete(f'/v1/claims/{claim_id}/sources/{source_id}')
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'source_delete_not_allowed_for_published_claim'
    app.dependency_overrides.clear()


def test_delete_source_returns_404_when_source_missing(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()

    def _fake_delete_source(_db, *, claim_id, source_id, reviewer_id):  # type: ignore[no-untyped-def]
        raise AppError(
            'source_not_found',
            'Source does not exist for this claim.',
            status_code=404,
            details={'claim_id': str(claim_id), 'source_id': str(source_id)},
        )

    monkeypatch.setattr('app.api.v1.claims.SourceService.delete_source', _fake_delete_source)

    client = TestClient(app)
    response = client.delete(f'/v1/claims/{claim_id}/sources/{source_id}')
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'source_not_found'
    app.dependency_overrides.clear()


def test_openapi_includes_claim_source_routes_and_methods() -> None:
    schema = app.openapi()
    paths = schema.get('paths', {})
    claim_sources_path = '/v1/claims/{claim_id}/sources'
    claim_source_path = '/v1/claims/{claim_id}/sources/{source_id}'
    assert claim_sources_path in paths
    assert claim_source_path in paths
    assert 'post' in paths[claim_sources_path]
    assert 'get' in paths[claim_sources_path]
    assert 'delete' in paths[claim_source_path]
