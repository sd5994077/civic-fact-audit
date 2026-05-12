import uuid

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.enums import ProposalStatus, ProposalType
from app.services.auth_dependency_service import require_reviewer_or_admin
from app.services.auth_service import AuthIdentity


def _override_identity() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='reviewer@local', role='reviewer')


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def test_create_proposal_requires_reviewer_or_admin() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    client = TestClient(app)

    response = client.post(
        f'/v1/claims/{uuid.uuid4()}/proposals',
        json={
            'proposal_type': ProposalType.issue_frame_mapping.value,
            'proposed_by': 'system:ai',
            'proposal_payload': {'issue_frame_id': str(uuid.uuid4())},
        },
    )
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_list_proposals_filters_forwarded(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_identity

    captured = {}

    def _fake_list_proposals(_db, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return []

    monkeypatch.setattr('app.api.v1.claims.ProposalService.list_proposals', _fake_list_proposals)

    client = TestClient(app)
    response = client.get(
        '/v1/claims/proposals?status=approved&proposal_type=draft_verdict&state=TX&office=US%20Senate&election_cycle=2026&limit=5'
    )
    assert response.status_code == 200
    assert captured['status'] == ProposalStatus.approved
    assert captured['proposal_type'] == ProposalType.draft_verdict
    assert captured['state'] == 'TX'
    assert captured['office'] == 'US Senate'
    assert captured['election_cycle'] == 2026
    assert captured['limit'] == 5
    app.dependency_overrides.clear()


def test_apply_proposal_response_shape(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_identity
    proposal_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.status = ProposalStatus.applied

    def _fake_apply(_db, _proposal_id, *, reviewer_id, review_notes=None):  # type: ignore[no-untyped-def]
        assert reviewer_id == 'reviewer@local'
        assert review_notes == 'looks good'
        return {'proposal': _FakeProposal(), 'applied_effect': 'source_attached'}

    monkeypatch.setattr('app.api.v1.claims.ProposalService.apply_proposal', _fake_apply)

    client = TestClient(app)
    response = client.post(f'/v1/claims/proposals/{proposal_id}/apply', json={'review_notes': 'looks good'})
    body = response.json()
    assert response.status_code == 200
    assert body['proposal_id'] == str(proposal_id)
    assert body['status'] == ProposalStatus.applied.value
    assert body['applied_effect'] == 'source_attached'
    app.dependency_overrides.clear()


def test_list_proposals_invalid_filter_returns_422() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_identity
    client = TestClient(app)
    response = client.get('/v1/claims/proposals?status=not-a-status')
    assert response.status_code == 422
    app.dependency_overrides.clear()
