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


def _mock_dual_control_token(monkeypatch, *, reviewer_id: str) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        'app.api.v1.evaluations.AuthService.identity_from_dual_control_approval_token',
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
        'app.api.v1.evaluations.AuthService.identity_from_dual_control_approval_token',
        _raise,
    )


def test_evaluate_claim_returns_422_for_moderation_violation(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer

    def _fake_evaluate(_db, _claim_id, _payload, *, reviewer_id, approval_reviewer_id=None):  # type: ignore[no-untyped-def]
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


def test_review_draft_requires_reviewer_or_admin_auth(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    monkeypatch.setattr('app.api.v1.evaluations.ReviewDraftService.generate_review_draft', lambda *_args, **_kwargs: {})

    client = TestClient(app)
    response = client.post(f'/v1/claims/{uuid.uuid4()}/review-draft')
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_review_queue_does_not_expose_unpublished_review_notes_anonymously(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)

    def _must_not_query_queue(*_args: object, **_kwargs: object) -> None:
        raise AssertionError('Anonymous requests must be rejected before loading review-queue data.')

    monkeypatch.setattr('app.api.v1.evaluations.EvaluationService.list_review_queue', _must_not_query_queue)

    client = TestClient(app)
    response = client.get('/v1/claims/review-queue')

    assert response.status_code == 401
    response_text = response.text
    assert 'Unpublished reviewer rationale' not in response_text
    assert 'Private citation notes' not in response_text
    app.dependency_overrides.clear()


def test_review_queue_returns_review_notes_to_authenticated_reviewer(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    monkeypatch.setattr(
        'app.api.v1.evaluations.EvaluationService.list_review_queue',
        lambda *_args, **_kwargs: [
            {
                'claim_id': claim_id,
                'claim_text': 'A factual claim.',
                'issue_tag': 'Public records',
                'status': 'reviewed',
                'statement_source_url': 'https://example.gov/statement',
                'statement_published_at': '2026-08-01T00:00:00Z',
                'candidate_id': candidate_id,
                'candidate_name': 'Candidate A',
                'candidate_party': None,
                'candidate_office': 'Governor',
                'candidate_state': 'TX',
                'election_cycle': 2026,
                'race_stage': None,
                'primary_source_count': 1,
                'secondary_source_count': 1,
                'candidate_source_count': 0,
                'verification_source_count': 2,
                'latest_verdict': 'supported',
                'latest_confidence': 0.9,
                'latest_rationale': 'Unpublished reviewer rationale',
                'latest_citation_notes': 'Private citation notes',
                'latest_reviewer_id': 'reviewer@local',
                'latest_evaluated_at': '2026-08-02T00:00:00Z',
                'warnings': [],
            }
        ],
    )

    client = TestClient(app)
    response = client.get('/v1/claims/review-queue')

    assert response.status_code == 200
    assert response.json()[0]['latest_rationale'] == 'Unpublished reviewer rationale'
    assert response.json()[0]['latest_citation_notes'] == 'Private citation notes'
    app.dependency_overrides.clear()


def test_review_draft_returns_structured_payload(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()
    claim_id_arg = claim_id

    def _fake_review_draft(_db, *, claim_id: uuid.UUID):  # type: ignore[no-untyped-def]
        assert claim_id == claim_id_arg
        return {
            'claim_id': claim_id,
            'suggested_verdict': 'mixed',
            'suggested_confidence': 0.73,
            'model_confidence': 0.9,
            'evidence_sufficiency': 0.84,
            'green_lane_ready': False,
            'rationale': 'Evidence supports one component of the claim but not the superlative framing.',
            'citation_notes': 'Primary legislative record and secondary analysis were reviewed.',
            'subclaims': [
                {
                    'text': 'Candidate voted for the bill.',
                    'judgment': 'supported',
                    'notes': 'Roll call shows a yes vote.',
                }
            ],
            'source_assessments': [
                {
                    'source_id': source_id,
                    'url': 'https://www.senate.gov/legislative/LIS/roll_call_votes/vote1151/vote_115_1_00323.htm',
                    'source_class': 'primary',
                    'source_origin': 'verification',
                    'publisher': 'U.S. Senate',
                    'supports_claim': 'supports',
                    'summary': 'Roll call includes the candidate as Yea.',
                    'excerpt': 'Cornyn (R-TX), Yea',
                }
            ],
            'warnings': [{'code': 'methodology_context_missing', 'message': 'Comparative denominator is not explicit.', 'severity': 'warning'}],
            'missing_evidence': ['comparative_denominator_unresolved'],
        }

    monkeypatch.setattr('app.api.v1.evaluations.ReviewDraftService.generate_review_draft', _fake_review_draft)
    recorded_calls: list[dict] = []
    monkeypatch.setattr(
        'app.api.v1.evaluations.ClaimAiDraftService.record_draft',
        lambda _db, *, claim_id, payload: recorded_calls.append({'claim_id': claim_id, 'payload': payload}),
    )

    client = TestClient(app)
    response = client.post(f'/v1/claims/{claim_id}/review-draft')
    body = response.json()
    assert response.status_code == 200
    assert body['claim_id'] == str(claim_id)
    assert body['suggested_verdict'] == 'mixed'
    assert body['source_assessments'][0]['supports_claim'] == 'supports'
    assert len(recorded_calls) == 1
    assert recorded_calls[0]['claim_id'] == claim_id
    app.dependency_overrides.clear()


def test_review_draft_history_requires_reviewer_or_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)

    client = TestClient(app)
    response = client.get(f'/v1/claims/{uuid.uuid4()}/review-drafts')
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_review_draft_history_returns_list(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    monkeypatch.setattr(
        'app.api.v1.evaluations.ClaimAiDraftService.list_draft_history',
        lambda _db, *, claim_id, limit=20: [
            {
                'id': draft_id,
                'claim_id': claim_id,
                'model': 'gpt-4o-mini',
                'suggested_verdict': 'supported',
                'suggested_confidence': 0.9,
                'model_confidence': 0.9,
                'evidence_sufficiency': 0.9,
                'green_lane_ready': False,
                'rationale': 'Supported by primary record.',
                'citation_notes': 'Senate roll call record.',
                'subclaims': [],
                'source_assessments': [],
                'warnings': [],
                'missing_evidence': [],
                'created_at': '2026-07-01T00:00:00Z',
            }
        ],
    )

    client = TestClient(app)
    response = client.get(f'/v1/claims/{claim_id}/review-drafts')
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]['id'] == str(draft_id)
    assert body[0]['model'] == 'gpt-4o-mini'
    app.dependency_overrides.clear()


def test_review_draft_diff_requires_reviewer_or_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)

    client = TestClient(app)
    response = client.get(f'/v1/claims/{uuid.uuid4()}/review-draft-diff')
    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_review_draft_diff_returns_comparison(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    eval_id = uuid.uuid4()

    monkeypatch.setattr(
        'app.api.v1.evaluations.ClaimAiDraftService.get_draft_diff',
        lambda _db, *, claim_id: {
            'claim_id': claim_id,
            'draft': {
                'id': draft_id,
                'claim_id': claim_id,
                'model': 'gpt-4o-mini',
                'suggested_verdict': 'supported',
                'suggested_confidence': 0.9,
                'model_confidence': 0.9,
                'evidence_sufficiency': 0.9,
                'green_lane_ready': False,
                'rationale': 'Draft rationale.',
                'citation_notes': 'Draft citation.',
                'subclaims': [],
                'source_assessments': [],
                'warnings': [],
                'missing_evidence': [],
                'created_at': '2026-07-01T00:00:00Z',
            },
            'evaluation': {
                'id': eval_id,
                'verdict': 'mixed',
                'confidence': 0.8,
                'rationale': 'Reviewer rationale.',
                'citation_notes': 'Reviewer citation.',
                'reviewer_id': 'reviewer@local',
                'created_at': '2026-07-02T00:00:00Z',
            },
            'verdict_match': False,
            'confidence_delta': -0.1,
            'rationale_changed': True,
            'citation_notes_changed': True,
        },
    )

    client = TestClient(app)
    response = client.get(f'/v1/claims/{claim_id}/review-draft-diff')
    assert response.status_code == 200
    body = response.json()
    assert body['verdict_match'] is False
    assert body['confidence_delta'] == -0.1
    assert body['draft']['model'] == 'gpt-4o-mini'
    assert body['evaluation']['verdict'] == 'mixed'
    app.dependency_overrides.clear()


def test_workbench_requires_reviewer_or_admin_auth(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_reviewer_or_admin, None)
    monkeypatch.setattr('app.api.v1.evaluations.ClaimWorkbenchService.list_workbench', lambda *_args, **_kwargs: [])

    client = TestClient(app)
    response = client.get('/v1/claims/workbench')

    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_workbench_returns_rows_for_reviewer(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    captured: dict[str, object] = {}

    def _fake_workbench(
        _db,
        *,
        actor_reviewer_id,
        state=None,
        office=None,
        election_cycle=None,
        race_stage=None,
        include_non_fact_checkable=False,
        workbench_state=None,
        limit=200,
    ):  # type: ignore[no-untyped-def]
        captured.update(
            {
                'actor_reviewer_id': actor_reviewer_id,
                'state': state,
                'office': office,
                'election_cycle': election_cycle,
                'race_stage': race_stage,
                'include_non_fact_checkable': include_non_fact_checkable,
                'workbench_state': workbench_state,
                'limit': limit,
            }
        )
        return [
            {
                'claim_id': claim_id,
                'claim_text': 'Claim text',
                'issue_tag': 'Economy',
                'status': 'reviewed',
                'statement_source_url': 'https://example.com/statement',
                'statement_published_at': '2026-05-11T00:00:00+00:00',
                'candidate_id': candidate_id,
                'candidate_name': 'Candidate A',
                'candidate_party': 'Independent',
                'candidate_office': 'Governor',
                'candidate_state': 'TX',
                'election_cycle': 2026,
                'race_stage': None,
                'fact_checkable': True,
                'is_published': False,
                'published_at': None,
                'published_by_reviewer_id': None,
                'reviewer_state': 'Needs Review',
                'second_reviewer_action': None,
                'primary_source_count': 1,
                'secondary_source_count': 1,
                'candidate_source_count': 0,
                'verification_source_count': 2,
                'verification_primary_count': 1,
                'verification_secondary_count': 1,
                'latest_verdict': None,
                'latest_confidence': None,
                'latest_rationale': None,
                'latest_citation_notes': None,
                'latest_reviewer_id': None,
                'latest_evaluated_at': None,
                'publish_gate_passed': False,
                'publish_gate_failures': ['latest_verdict_must_be_supported_mixed_or_unsupported'],
                'checklist': [
                    {
                        'code': 'fact_checkable',
                        'label': 'Claim is fact-checkable',
                        'passed': True,
                        'blocking': True,
                    }
                ],
            }
        ]

    monkeypatch.setattr('app.api.v1.evaluations.ClaimWorkbenchService.list_workbench', _fake_workbench)

    client = TestClient(app)
    response = client.get(
        '/v1/claims/workbench?state=TX&office=Governor&election_cycle=2026&include_non_fact_checkable=true&workbench_state=Needs%20Review&limit=77'
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]['claim_id'] == str(claim_id)
    assert body[0]['reviewer_state'] == 'Needs Review'
    assert captured['actor_reviewer_id'] == 'reviewer@local'
    assert captured['state'] == 'TX'
    assert captured['office'] == 'Governor'
    assert captured['election_cycle'] == 2026
    assert captured['include_non_fact_checkable'] is True
    assert captured['workbench_state'] == 'Needs Review'
    assert captured['limit'] == 77
    app.dependency_overrides.clear()


def test_evaluate_claim_returns_409_for_overwrite_dual_control_conflict(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    claim_id = uuid.uuid4()
    _mock_dual_control_token(monkeypatch, reviewer_id='reviewer@local')

    def _fake_evaluate(_db, _claim_id, _payload, *, reviewer_id, approval_reviewer_id=None):  # type: ignore[no-untyped-def]
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
            'approval_token': 'approval-token',
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

    def _fake_evaluate(_db, _claim_id, payload, *, reviewer_id, approval_reviewer_id=None):  # type: ignore[no-untyped-def]
        assert _claim_id == claim_id
        assert reviewer_id == 'reviewer@local'
        captured['approval_reviewer_id'] = approval_reviewer_id
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


def test_evaluate_claim_returns_401_for_invalid_dual_control_token(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    _mock_dual_control_token_error(
        monkeypatch,
        AppError('invalid_dual_control_token', 'Dual-control approval token is invalid.', status_code=401),
    )
    claim_id = uuid.uuid4()
    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{claim_id}/evaluate',
        json={
            'verdict': 'supported',
            'confidence': 0.8,
            'rationale': 'Neutral rationale with enough detail.',
            'citation_notes': 'Source packet A',
            'approval_token': 'bad-token',
        },
    )
    body = response.json()
    assert response.status_code == 401
    assert body['error']['code'] == 'invalid_dual_control_token'
    app.dependency_overrides.clear()


def test_evaluate_claim_returns_401_for_expired_dual_control_token(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reviewer_or_admin] = _override_reviewer
    _mock_dual_control_token_error(
        monkeypatch,
        AppError('token_expired', 'Authentication token has expired.', status_code=401),
    )
    claim_id = uuid.uuid4()
    client = TestClient(app)
    response = client.post(
        f'/v1/claims/{claim_id}/evaluate',
        json={
            'verdict': 'supported',
            'confidence': 0.8,
            'rationale': 'Neutral rationale with enough detail.',
            'citation_notes': 'Source packet A',
            'approval_token': 'expired-token',
        },
    )
    body = response.json()
    assert response.status_code == 401
    assert body['error']['code'] == 'token_expired'
    app.dependency_overrides.clear()
