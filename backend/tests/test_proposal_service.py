import uuid

from app.core.errors import AppError
from app.models.enums import ProposalStatus, ProposalType, SourceClass, SourceOrigin
from app.services.proposal_service import ProposalService


def test_validate_payload_mapping_requires_issue_frame_id() -> None:
    try:
        ProposalService._validate_payload(ProposalType.issue_frame_mapping, {})
        assert False, 'Expected invalid_proposal_payload'
    except AppError as exc:
        assert exc.code == 'invalid_proposal_payload'


def test_validate_payload_source_requires_fields() -> None:
    try:
        ProposalService._validate_payload(
            ProposalType.verification_source_suggestion,
            {'url': 'https://example.com'},
        )
        assert False, 'Expected invalid_proposal_payload'
    except AppError as exc:
        assert exc.code == 'invalid_proposal_payload'
        assert 'missing_fields' in exc.details


def test_validate_payload_draft_verdict_requires_fields() -> None:
    try:
        ProposalService._validate_payload(
            ProposalType.draft_verdict,
            {'verdict': 'supported', 'confidence': 0.8},
        )
        assert False, 'Expected invalid_proposal_payload'
    except AppError as exc:
        assert exc.code == 'invalid_proposal_payload'


def test_validate_payload_draft_verdict_rejects_moderation_violation() -> None:
    try:
        ProposalService._validate_payload(
            ProposalType.draft_verdict,
            {
                'verdict': 'supported',
                'confidence': 0.8,
                'rationale': 'You should vote for this candidate.',
                'citation_notes': 'official report',
            },
        )
        assert False, 'Expected moderation_policy_violation'
    except AppError as exc:
        assert exc.code == 'moderation_policy_violation'


def test_status_transition_guards() -> None:
    class _FakeProposal:
        def __init__(self, status: ProposalStatus) -> None:
            self.status = status

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal(ProposalStatus.rejected)

        def get(self, _model, _id):  # type: ignore[no-untyped-def]
            return self.proposal

    db = _FakeDb()
    try:
        ProposalService.approve_proposal(db, uuid.uuid4(), reviewer_id='reviewer@local')  # type: ignore[arg-type]
        assert False, 'Expected invalid transition'
    except AppError as exc:
        assert exc.code == 'invalid_proposal_transition'


def test_apply_draft_verdict_has_no_official_evaluation_effect(monkeypatch) -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.draft_verdict
            self.status = ProposalStatus.approved
            self.proposal_payload = '{"verdict":"supported","confidence":0.81,"rationale":"draft text","citation_notes":"notes"}'
            self.reviewed_by = None
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()
            self.commit_count = 0

        def add(self, _item):  # type: ignore[no-untyped-def]
            return None

        def get(self, model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    db = _FakeDb()
    called = {'source_add_called': False}

    def _blocked_source_add(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        called['source_add_called'] = True
        raise AssertionError('source add should not be called for draft verdict apply')

    monkeypatch.setattr('app.services.proposal_service.SourceService.add_source', _blocked_source_add)
    result = ProposalService.apply_proposal(db, proposal_id, reviewer_id='reviewer@local')  # type: ignore[arg-type]
    assert result['applied_effect'] == 'draft_verdict_retained_for_reviewer_evaluate_flow'
    assert db.proposal.status == ProposalStatus.applied
    assert called['source_add_called'] is False
    assert db.commit_count == 1


def test_source_payload_accepts_expected_values() -> None:
    ProposalService._validate_payload(
        ProposalType.candidate_source_capture,
        {
            'url': 'https://example.com',
            'source_class': SourceClass.primary.value,
            'source_origin': SourceOrigin.candidate.value,
            'quality_score': 0.75,
        },
    )


def test_create_proposal_rejects_partisan_verification_source_payload() -> None:
    claim_id = uuid.uuid4()

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id

    class _FakeDb:
        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return _FakeClaim()
            return None

    payload = type(
        'Payload',
        (),
        {
            'proposal_type': ProposalType.verification_source_suggestion,
            'proposed_by': 'system:ai',
            'proposal_payload': {
                'url': 'https://www.dailykos.com/stories/example',
                'source_class': SourceClass.secondary.value,
                'source_origin': SourceOrigin.verification.value,
                'quality_score': 0.5,
                'publisher': 'Daily Kos',
            },
        },
    )()
    try:
        ProposalService.create_proposal(_FakeDb(), claim_id, payload)  # type: ignore[arg-type]
        assert False, 'Expected source_admission_policy_violation'
    except AppError as exc:
        assert exc.code == 'source_admission_policy_violation'


def test_create_proposal_rejects_blank_proposed_by() -> None:
    claim_id = uuid.uuid4()

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id

    class _FakeDb:
        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return _FakeClaim()
            return None

    payload = type(
        'Payload',
        (),
        {
            'proposal_type': ProposalType.issue_frame_mapping,
            'proposed_by': '   ',
            'proposal_payload': {'issue_frame_id': str(uuid.uuid4())},
        },
    )()
    try:
        ProposalService.create_proposal(_FakeDb(), claim_id, payload)  # type: ignore[arg-type]
        assert False, 'Expected invalid_proposal_payload'
    except AppError as exc:
        assert exc.code == 'invalid_proposal_payload'


def test_apply_source_proposal_uses_single_transaction(monkeypatch) -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.verification_source_suggestion
            self.status = ProposalStatus.approved
            self.proposal_payload = (
                '{"url":"https://example.com","source_class":"primary","source_origin":"verification","quality_score":0.9}'
            )
            self.reviewed_by = None
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()
            self.commit_count = 0
            self.rollback_count = 0

        def add(self, _item):  # type: ignore[no-untyped-def]
            return None

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def rollback(self):  # type: ignore[no-untyped-def]
            self.rollback_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    add_source_calls = []

    def _fake_add_source(_db, _claim_id, _payload, *, commit=True):  # type: ignore[no-untyped-def]
        add_source_calls.append(commit)
        return []

    monkeypatch.setattr('app.services.proposal_service.SourceService.add_source', _fake_add_source)
    db = _FakeDb()
    result = ProposalService.apply_proposal(db, proposal_id, reviewer_id='reviewer@local')  # type: ignore[arg-type]
    assert result['applied_effect'] == 'source_attached'
    assert add_source_calls == [False]
    assert db.commit_count == 1
    assert db.rollback_count == 0


def test_apply_source_proposal_policy_violation_keeps_status_approved() -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.verification_source_suggestion
            self.status = ProposalStatus.approved
            self.proposal_payload = (
                '{\"url\":\"https://www.dailykos.com/stories/example\",\"source_class\":\"secondary\",'
                '\"source_origin\":\"verification\",\"quality_score\":0.5,\"publisher\":\"Daily Kos\"}'
            )
            self.reviewed_by = None
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()
            self.commit_count = 0
            self.rollback_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def rollback(self):  # type: ignore[no-untyped-def]
            self.rollback_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    db = _FakeDb()
    try:
        ProposalService.apply_proposal(db, proposal_id, reviewer_id='reviewer@local')  # type: ignore[arg-type]
        assert False, 'Expected source_admission_policy_violation'
    except AppError as exc:
        assert exc.code == 'source_admission_policy_violation'
    assert db.proposal.status == ProposalStatus.approved
    assert db.commit_count == 0
    assert db.rollback_count == 0
