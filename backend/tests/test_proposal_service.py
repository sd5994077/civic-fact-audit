import uuid
import json

from app.core.errors import AppError
from app.models.entities import AdminAuditEvent
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


def test_apply_proposal_checks_locked_status_snapshot_when_available() -> None:
    proposal_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self, status: ProposalStatus) -> None:
            self.id = proposal_id
            self.claim_id = uuid.uuid4()
            self.proposal_type = ProposalType.draft_verdict
            self.status = status
            self.proposal_payload = '{"verdict":"supported","confidence":0.81,"rationale":"draft text","citation_notes":"notes"}'
            self.reviewed_by = 'approver@local'
            self.reviewed_at = None
            self.review_notes = None

    class _FakeResult:
        def __init__(self, proposal: _FakeProposal) -> None:
            self._proposal = proposal

        def scalars(self):  # type: ignore[no-untyped-def]
            return self

        def first(self):  # type: ignore[no-untyped-def]
            return self._proposal

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal_via_get = _FakeProposal(ProposalStatus.approved)
            self.proposal_via_lock = _FakeProposal(ProposalStatus.rejected)
            self.execute_calls = 0

        def get(self, _model, _id):  # type: ignore[no-untyped-def]
            return self.proposal_via_get

        def execute(self, _stmt):  # type: ignore[no-untyped-def]
            self.execute_calls += 1
            return _FakeResult(self.proposal_via_lock)

    db = _FakeDb()
    try:
        ProposalService.apply_proposal(db, proposal_id, reviewer_id='reviewer@local')  # type: ignore[arg-type]
        assert False, 'Expected invalid_proposal_transition'
    except AppError as exc:
        assert exc.code == 'invalid_proposal_transition'
    assert db.execute_calls == 1


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
            self.reviewed_by = 'approver@local'
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
        ProposalService.create_proposal(_FakeDb(), claim_id, payload, proposed_by='reviewer@local')  # type: ignore[arg-type]
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
            'proposal_payload': {'issue_frame_id': str(uuid.uuid4())},
        },
    )()
    try:
        ProposalService.create_proposal(_FakeDb(), claim_id, payload, proposed_by='   ')  # type: ignore[arg-type]
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
                '{"url":"https://example.com/record","source_class":"primary","source_origin":"verification","quality_score":0.9}'
            )
            self.reviewed_by = 'approver@local'
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


def test_apply_verification_source_proposal_blocks_self_apply_dual_control() -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.verification_source_suggestion
            self.status = ProposalStatus.approved
            self.proposal_payload = (
                '{"url":"https://example.com/record","source_class":"primary","source_origin":"verification","quality_score":0.9}'
            )
            self.reviewed_by = 'reviewer@local'
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            return None

    db = _FakeDb()
    try:
        ProposalService.apply_proposal(db, proposal_id, reviewer_id='reviewer@local')  # type: ignore[arg-type]
        assert False, 'Expected proposal_dual_control_required'
    except AppError as exc:
        assert exc.code == 'proposal_dual_control_required'
        assert exc.details['approval_reviewer_id'] == 'reviewer@local'
        assert exc.details['applying_reviewer_id'] == 'reviewer@local'


def test_apply_verification_source_proposal_blocks_self_apply_case_insensitive() -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.verification_source_suggestion
            self.status = ProposalStatus.approved
            self.proposal_payload = (
                '{"url":"https://example.com/record","source_class":"primary","source_origin":"verification","quality_score":0.9}'
            )
            self.reviewed_by = 'Reviewer@Local'
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            return None

    db = _FakeDb()
    try:
        ProposalService.apply_proposal(db, proposal_id, reviewer_id='reviewer@local')  # type: ignore[arg-type]
        assert False, 'Expected proposal_dual_control_required'
    except AppError as exc:
        assert exc.code == 'proposal_dual_control_required'
        assert exc.details['approval_reviewer_id'] == 'reviewer@local'
        assert exc.details['applying_reviewer_id'] == 'reviewer@local'


def test_apply_issue_frame_proposal_allows_same_reviewer(monkeypatch) -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    frame_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.issue_frame_mapping
            self.status = ProposalStatus.approved
            self.proposal_payload = f'{{"issue_frame_id":"{frame_id}"}}'
            self.reviewed_by = 'reviewer@local'
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.issue_frame_id = None

    class _FakeFrame:
        def __init__(self) -> None:
            self.id = frame_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()
            self.frame = _FakeFrame()
            self.commit_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            if id_ == frame_id:
                return self.frame
            return None

        def add(self, _item):  # type: ignore[no-untyped-def]
            return None

        def flush(self):  # type: ignore[no-untyped-def]
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    def _noop_audit(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr('app.services.proposal_service.AdminAuditService.record_event', _noop_audit)
    db = _FakeDb()
    result = ProposalService.apply_proposal(db, proposal_id, reviewer_id='reviewer@local')  # type: ignore[arg-type]
    assert result['applied_effect'] == 'issue_frame_mapped'
    assert db.claim.issue_frame_id == frame_id
    assert db.commit_count == 1


def test_approve_proposal_records_audit_metadata_with_reviewer_linkage(monkeypatch) -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.verification_source_suggestion
            self.status = ProposalStatus.proposed
            self.proposal_payload = '{}'
            self.reviewed_by = 'approver@local'
            self.reviewed_at = None
            self.review_notes = None

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            return None

        def add(self, _item):  # type: ignore[no-untyped-def]
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            return None

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    captured = {}

    def _capture_audit(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs.get('metadata', {}))
        return None

    monkeypatch.setattr('app.services.proposal_service.AdminAuditService.record_event', _capture_audit)
    db = _FakeDb()
    ProposalService.approve_proposal(db, proposal_id, reviewer_id='APPROVER@LOCAL')  # type: ignore[arg-type]
    assert db.proposal.reviewed_by == 'approver@local'
    assert captured['proposal_type'] == ProposalType.verification_source_suggestion.value
    assert captured['approval_reviewer_id'] == 'approver@local'


def test_apply_proposal_records_audit_metadata_with_reviewer_linkage(monkeypatch) -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    frame_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.issue_frame_mapping
            self.status = ProposalStatus.approved
            self.proposal_payload = f'{{"issue_frame_id":"{frame_id}"}}'
            self.reviewed_by = 'approver@local'
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.issue_frame_id = None

    class _FakeFrame:
        def __init__(self) -> None:
            self.id = frame_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()
            self.frame = _FakeFrame()

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            if id_ == frame_id:
                return self.frame
            return None

        def add(self, _item):  # type: ignore[no-untyped-def]
            return None

        def flush(self):  # type: ignore[no-untyped-def]
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            return None

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    captured = {}

    def _capture_audit(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs.get('metadata', {}))
        return None

    monkeypatch.setattr('app.services.proposal_service.AdminAuditService.record_event', _capture_audit)
    db = _FakeDb()
    ProposalService.apply_proposal(db, proposal_id, reviewer_id='applier@local')  # type: ignore[arg-type]
    assert captured['proposal_type'] == ProposalType.issue_frame_mapping.value
    assert captured['approval_reviewer_id'] == 'approver@local'
    assert captured['applying_reviewer_id'] == 'applier@local'


def test_proposal_audit_events_persist_metadata_for_approve_and_apply() -> None:
    proposal_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    frame_id = uuid.uuid4()

    class _FakeProposal:
        def __init__(self) -> None:
            self.id = proposal_id
            self.claim_id = claim_id
            self.proposal_type = ProposalType.issue_frame_mapping
            self.status = ProposalStatus.proposed
            self.proposal_payload = f'{{"issue_frame_id":"{frame_id}"}}'
            self.reviewed_by = 'approver@local'
            self.reviewed_at = None
            self.review_notes = None

    class _FakeClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.issue_frame_id = None

    class _FakeFrame:
        def __init__(self) -> None:
            self.id = frame_id

    class _FakeDb:
        def __init__(self) -> None:
            self.proposal = _FakeProposal()
            self.claim = _FakeClaim()
            self.frame = _FakeFrame()
            self.added: list[object] = []

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == proposal_id:
                return self.proposal
            if id_ == claim_id:
                return self.claim
            if id_ == frame_id:
                return self.frame
            return None

        def add(self, item):  # type: ignore[no-untyped-def]
            self.added.append(item)

        def flush(self):  # type: ignore[no-untyped-def]
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            return None

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    db = _FakeDb()
    ProposalService.approve_proposal(db, proposal_id, reviewer_id='approver@local')  # type: ignore[arg-type]
    ProposalService.apply_proposal(db, proposal_id, reviewer_id='applier@local')  # type: ignore[arg-type]
    events = [item for item in db.added if isinstance(item, AdminAuditEvent)]
    assert len(events) == 2
    approve_event = next(item for item in events if item.action == 'proposal_approved')
    apply_event = next(item for item in events if item.action == 'proposal_applied')
    approve_meta = json.loads(approve_event.metadata_payload or '{}')
    apply_meta = json.loads(apply_event.metadata_payload or '{}')
    assert approve_meta['proposal_type'] == ProposalType.issue_frame_mapping.value
    assert approve_meta['approval_reviewer_id'] == 'approver@local'
    assert apply_meta['proposal_type'] == ProposalType.issue_frame_mapping.value
    assert apply_meta['approval_reviewer_id'] == 'approver@local'
    assert apply_meta['applying_reviewer_id'] == 'applier@local'
