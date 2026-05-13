import uuid

from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.database import get_db
from app.main import app
from app.services.auth_dependency_service import require_admin, require_reviewer_or_admin
from app.services.auth_service import AuthIdentity


def _override_reviewer() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='reviewer@local', role='reviewer')


def _override_admin() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='admin@local', role='admin')


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def test_evaluate_claim_returns_422_for_moderation_violation(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer

    def _fake_evaluate(_db, _claim_id, _payload, *, reviewer_id):  # type: ignore[no-untyped-def]
        assert reviewer_id == 'reviewer@local'
        raise AppError(
            'moderation_policy_violation',
            'Rationale violates moderation policy boundaries.',
            status_code=422,
            details={
                'rejection_field': 'rationale',
                'matched_rule': 'endorsement_vote_for:vote for',
                'policy_version': 'moderation_policy_v1_2026_05_11',
                'violation_type': 'endorsement_or_recommendation',
            },
        )

    monkeypatch.setattr('app.api.v1.evaluations.EvaluationService.evaluate_claim', _fake_evaluate)

    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{uuid.uuid4()}/evaluate',
        json={
            'verdict': 'supported',
            'confidence': 0.8,
            'rationale': 'You should vote for this candidate.',
            'citation_notes': 'Source packet A',
        },
    )
    body = response.json()
    assert response.status_code == 422
    assert body['error']['code'] == 'moderation_policy_violation'
    assert body['error']['details']['rejection_field'] == 'rationale'
    app.dependency_overrides.clear()


def test_evaluate_claim_returns_409_for_overwrite_dual_control_conflict(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()

    def _fake_evaluate(_db, _claim_id, _payload, *, reviewer_id):  # type: ignore[no-untyped-def]
        assert reviewer_id == 'reviewer@local'
        assert _claim_id == claim_id
        raise AppError(
            'evaluation_overwrite_dual_control_required',
            'Evaluation overwrites require different reviewers for approval and final mutation.',
            status_code=409,
            details={
                'claim_id': str(claim_id),
                'approval_reviewer_id': 'reviewer@local',
                'applying_reviewer_id': 'reviewer@local',
                'action': 'evaluate_overwrite',
            },
        )

    monkeypatch.setattr('app.api.v1.evaluations.EvaluationService.evaluate_claim', _fake_evaluate)

    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{claim_id}/evaluate',
        json={
            'verdict': 'supported',
            'confidence': 0.8,
            'rationale': 'Neutral rationale with enough detail.',
            'citation_notes': 'Source packet A',
            'approval_reviewer_id': 'reviewer@local',
        },
    )
    body = response.json()
    assert response.status_code == 409
    assert body['error']['code'] == 'evaluation_overwrite_dual_control_required'
    assert body['error']['details']['claim_id'] == str(claim_id)
    assert body['error']['details']['approval_reviewer_id'] == 'reviewer@local'
    assert body['error']['details']['applying_reviewer_id'] == 'reviewer@local'
    assert body['error']['details']['action'] == 'evaluate_overwrite'
    app.dependency_overrides.clear()


def test_evaluate_claim_first_write_allows_blank_approval_reviewer(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    captured = {}

    class _Eval:
        def __init__(self) -> None:
            from datetime import datetime, timezone

            self.id = uuid.uuid4()
            self.claim_id = claim_id
            self.verdict = 'supported'
            self.confidence = 0.8
            self.rationale = 'Neutral rationale with enough detail.'
            self.citation_notes = 'Source packet A'
            self.reviewer_id = 'reviewer@local'
            self.created_at = datetime(2026, 5, 12, tzinfo=timezone.utc)

    def _fake_evaluate(_db, _claim_id, payload, *, reviewer_id):  # type: ignore[no-untyped-def]
        assert _claim_id == claim_id
        assert reviewer_id == 'reviewer@local'
        captured['approval_reviewer_id'] = payload.approval_reviewer_id
        return _Eval()

    monkeypatch.setattr('app.api.v1.evaluations.EvaluationService.evaluate_claim', _fake_evaluate)

    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{claim_id}/evaluate',
        json={
            'verdict': 'supported',
            'confidence': 0.8,
            'rationale': 'Neutral rationale with enough detail.',
            'citation_notes': 'Source packet A',
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert captured['approval_reviewer_id'] is None
    assert body['claim_id'] == str(claim_id)
    assert body['reviewer_id'] == 'reviewer@local'
    app.dependency_overrides.clear()


def test_publish_claim_returns_422_for_moderation_gate_failure(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin

    def _fake_publish(_db, _claim_id, *, approver_id):  # type: ignore[no-untyped-def]
        assert approver_id == 'admin@local'
        raise AppError(
            'publish_gate_moderation_failure',
            'Claim publish blocked by moderation policy boundaries.',
            status_code=422,
            details={'failed_checks': ['latest_evaluation_moderation_policy_violation']},
        )

    monkeypatch.setattr('app.api.v1.evaluations.EvaluationService.publish_claim', _fake_publish)

    client = TestClient(app)
    response = client.post(f'/v1/claims/{uuid.uuid4()}/publish')
    body = response.json()
    assert response.status_code == 422
    assert body['error']['code'] == 'publish_gate_moderation_failure'
    assert 'latest_evaluation_moderation_policy_violation' in body['error']['details']['failed_checks']
    app.dependency_overrides.clear()


def test_publish_claim_returns_409_for_dual_control_block(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    claim_id = uuid.uuid4()

    def _fake_publish(_db, _claim_id, *, approver_id):  # type: ignore[no-untyped-def]
        assert _claim_id == claim_id
        assert approver_id == 'admin@local'
        raise AppError(
            'publish_dual_control_required',
            'Publish and unpublish actions require different reviewers for approval and final mutation.',
            status_code=409,
            details={
                'claim_id': str(claim_id),
                'approval_reviewer_id': 'admin@local',
                'applying_reviewer_id': 'admin@local',
                'action': 'publish',
            },
        )

    monkeypatch.setattr('app.api.v1.evaluations.EvaluationService.publish_claim', _fake_publish)

    client = TestClient(app)
    response = client.post(f'/v1/claims/{claim_id}/publish')
    body = response.json()

    assert response.status_code == 409
    assert body['error']['code'] == 'publish_dual_control_required'
    assert body['error']['details']['claim_id'] == str(claim_id)
    assert body['error']['details']['approval_reviewer_id'] == 'admin@local'
    assert body['error']['details']['applying_reviewer_id'] == 'admin@local'
    assert body['error']['details']['action'] == 'publish'
    app.dependency_overrides.clear()


def test_unpublish_claim_returns_409_for_dual_control_block(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    claim_id = uuid.uuid4()

    def _fake_unpublish(_db, _claim_id, *, approver_id):  # type: ignore[no-untyped-def]
        assert _claim_id == claim_id
        assert approver_id == 'admin@local'
        raise AppError(
            'publish_dual_control_required',
            'Publish and unpublish actions require different reviewers for approval and final mutation.',
            status_code=409,
            details={
                'claim_id': str(claim_id),
                'approval_reviewer_id': 'admin@local',
                'applying_reviewer_id': 'admin@local',
                'action': 'unpublish',
            },
        )

    monkeypatch.setattr('app.api.v1.evaluations.EvaluationService.unpublish_claim', _fake_unpublish)

    client = TestClient(app)
    response = client.post(f'/v1/claims/{claim_id}/unpublish')
    body = response.json()

    assert response.status_code == 409
    assert body['error']['code'] == 'publish_dual_control_required'
    assert body['error']['details']['claim_id'] == str(claim_id)
    assert body['error']['details']['approval_reviewer_id'] == 'admin@local'
    assert body['error']['details']['applying_reviewer_id'] == 'admin@local'
    assert body['error']['details']['action'] == 'unpublish'
    app.dependency_overrides.clear()
