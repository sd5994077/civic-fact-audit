import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
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
