import json

from app.models.entities import AdminAuditEvent
from app.models.enums import ClaimStatus, RaceStage
from app.services.evaluation_service import EvaluationService
from app.models.enums import Verdict
from unittest.mock import patch
import uuid

from app.core.errors import AppError
from app.schemas.api import EvaluateClaimRequest


class _FakeClaim:
    def __init__(self, *, fact_checkable: bool = True) -> None:
        self.fact_checkable = fact_checkable
        self.id = 'claim-id'


class _FakeEval:
    def __init__(
        self,
        *,
        verdict: Verdict = Verdict.supported,
        rationale: str = 'rationale',
        citation_notes: str = 'notes',
        reviewer_id: str = 'reviewer@local',
    ) -> None:
        self.verdict = verdict
        self.rationale = rationale
        self.citation_notes = citation_notes
        self.reviewer_id = reviewer_id


def test_build_review_queue_query_has_race_filters_and_minimum_evidence_having() -> None:
    query = EvaluationService._build_review_queue_query(
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        require_minimum_evidence=True,
    )

    compiled = str(query)
    assert 'lower(candidates.state)' in compiled
    assert 'lower(candidates.office)' in compiled
    assert 'candidates.election_cycle =' in compiled
    assert 'candidates.race_stage =' in compiled
    assert 'claims.fact_checkable' in compiled
    assert 'sources.source_origin' in compiled
    assert 'sources.source_class' in compiled
    assert 'sources.policy_flagged' in compiled
    assert 'HAVING' in compiled


def test_build_review_queue_query_without_minimum_evidence_has_no_having() -> None:
    query = EvaluationService._build_review_queue_query(
        state=None,
        office=None,
        election_cycle=None,
        race_stage=None,
        require_minimum_evidence=False,
    )

    compiled = str(query)
    assert 'HAVING' not in compiled


def test_publish_gate_failures_empty_when_all_rules_pass() -> None:
    claim = _FakeClaim(fact_checkable=True)
    latest_eval = _FakeEval(verdict=Verdict.supported, rationale='Looks good', citation_notes='Cited.')
    with patch('app.services.evaluation_service.SourceService.has_source_class', return_value=True):
        failures = EvaluationService._publish_gate_failures(None, claim, latest_eval)  # type: ignore[arg-type]
    assert failures == []


def test_publish_gate_failures_include_expected_rules() -> None:
    claim = _FakeClaim(fact_checkable=False)
    latest_eval = _FakeEval(verdict=Verdict.insufficient, rationale=' ', citation_notes=' ')
    with patch('app.services.evaluation_service.SourceService.has_source_class', return_value=False):
        failures = EvaluationService._publish_gate_failures(None, claim, latest_eval)  # type: ignore[arg-type]
    assert EvaluationService._PUBLISH_GATE_FACT_CHECKABLE in failures
    assert EvaluationService._PUBLISH_GATE_VERDICT in failures
    assert EvaluationService._PUBLISH_GATE_RATIONALE in failures
    assert EvaluationService._PUBLISH_GATE_CITATION_NOTES in failures
    assert EvaluationService._PUBLISH_GATE_VERIFICATION_PRIMARY in failures
    assert EvaluationService._PUBLISH_GATE_VERIFICATION_SECONDARY in failures


def test_publish_gate_failures_include_moderation_policy_rule() -> None:
    claim = _FakeClaim(fact_checkable=True)
    latest_eval = _FakeEval(
        verdict=Verdict.supported,
        rationale='You should vote for this candidate.',
        citation_notes='Voters should choose this person.',
    )
    with patch('app.services.evaluation_service.SourceService.has_source_class', return_value=True):
        failures = EvaluationService._publish_gate_failures(None, claim, latest_eval)  # type: ignore[arg-type]
    assert EvaluationService._PUBLISH_GATE_MODERATION_POLICY in failures
    assert failures.count(EvaluationService._PUBLISH_GATE_MODERATION_POLICY) == 1


def test_publish_claim_moderation_failure_returns_violation_details(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _Db:
        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return _FakeClaim(fact_checkable=True)
            return None

    latest_eval = _FakeEval(
        verdict=Verdict.supported,
        rationale='You should vote for Candidate A.',
        citation_notes='Vote against Candidate B.',
    )
    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation_for_publish',
        lambda *_args, **_kwargs: latest_eval,
    )
    monkeypatch.setattr(
        'app.services.evaluation_service.SourceService.has_source_class',
        lambda _db, _claim_id, _source_class, source_origin=None: True,
    )
    try:
        EvaluationService.publish_claim(_Db(), claim_id, approver_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected publish_gate_moderation_failure'
    except AppError as exc:
        assert exc.code == 'publish_gate_moderation_failure'
        assert 'latest_evaluation_moderation_policy_violation' in exc.details['failed_checks']
        violations = exc.details.get('moderation_violations', [])
        assert len(violations) == 2
        assert {item['rejection_field'] for item in violations} == {'rationale', 'citation_notes'}


def test_list_publish_queue_uses_verification_counts_from_review_row(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _PublishClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.is_published = False
            self.published_at = None
            self.published_by_reviewer_id = None

    class _Db:
        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return _PublishClaim()
            return None

    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService.list_review_queue',
        lambda *_args, **_kwargs: [
            {
                'claim_id': claim_id,
                'claim_text': 'Claim text',
                'issue_tag': 'Economy',
                'candidate_name': 'Candidate A',
                'candidate_party': 'Independent',
                'statement_source_url': 'https://example.com/statement',
                'statement_published_at': None,
                'latest_verdict': None,
                'latest_confidence': None,
                'latest_rationale': None,
                'latest_citation_notes': None,
                'latest_reviewer_id': None,
                'primary_source_count': 5,
                'secondary_source_count': 4,
                'verification_primary_count': 3,
                'verification_secondary_count': 2,
            }
        ],
    )
    monkeypatch.setattr('app.services.evaluation_service.EvaluationService._latest_evaluation', lambda *_args, **_kwargs: None)
    monkeypatch.setattr('app.services.evaluation_service.EvaluationService._publish_gate_failures', lambda *_args, **_kwargs: [])

    rows = EvaluationService.list_publish_queue(_Db())  # type: ignore[arg-type]

    assert len(rows) == 1
    assert rows[0]['verification_primary_count'] == 3
    assert rows[0]['verification_secondary_count'] == 2


def test_publish_claim_blocks_when_approval_and_apply_reviewer_match(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _PublishableClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.reviewed
            self.fact_checkable = True
            self.is_published = False
            self.published_at = None
            self.published_by_reviewer_id = None

    class _Db:
        def __init__(self) -> None:
            self.claim = _PublishableClaim()

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return self.claim
            return None

    latest_eval = _FakeEval(reviewer_id='reviewer@local')
    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation_for_publish',
        lambda *_args, **_kwargs: latest_eval,
    )
    monkeypatch.setattr(
        'app.services.evaluation_service.SourceService.has_source_class',
        lambda _db, _claim_id, _source_class, source_origin=None: True,
    )
    try:
        EvaluationService.publish_claim(_Db(), claim_id, approver_id='reviewer@local')  # type: ignore[arg-type]
        assert False, 'Expected publish_dual_control_required'
    except AppError as exc:
        assert exc.code == 'publish_dual_control_required'
        assert exc.status_code == 409
        assert exc.details['claim_id'] == str(claim_id)
        assert exc.details['approval_reviewer_id'] == 'reviewer@local'
        assert exc.details['applying_reviewer_id'] == 'reviewer@local'
        assert exc.details['action'] == 'publish'


def test_unpublish_claim_blocks_when_approval_and_apply_reviewer_match(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _PublishedClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.published
            self.fact_checkable = True
            self.is_published = True
            self.published_at = None
            self.published_by_reviewer_id = 'publisher@local'

    class _Db:
        def __init__(self) -> None:
            self.claim = _PublishedClaim()

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return self.claim
            return None

    latest_eval = _FakeEval(reviewer_id='reviewer@local')
    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation_for_publish',
        lambda *_args, **_kwargs: latest_eval,
    )
    try:
        EvaluationService.unpublish_claim(_Db(), claim_id, approver_id='reviewer@local')  # type: ignore[arg-type]
        assert False, 'Expected publish_dual_control_required'
    except AppError as exc:
        assert exc.code == 'publish_dual_control_required'
        assert exc.status_code == 409
        assert exc.details['claim_id'] == str(claim_id)
        assert exc.details['approval_reviewer_id'] == 'reviewer@local'
        assert exc.details['applying_reviewer_id'] == 'reviewer@local'
        assert exc.details['action'] == 'unpublish'


def test_publish_claim_allows_different_reviewers_and_records_audit_metadata(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _PublishableClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.reviewed
            self.fact_checkable = True
            self.is_published = False
            self.published_at = None
            self.published_by_reviewer_id = None

    class _Db:
        def __init__(self) -> None:
            self.claim = _PublishableClaim()
            self.added: list[object] = []
            self.commit_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return self.claim
            return None

        def add(self, item):  # type: ignore[no-untyped-def]
            self.added.append(item)

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    latest_eval = _FakeEval(reviewer_id='approver@local')
    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation_for_publish',
        lambda *_args, **_kwargs: latest_eval,
    )
    monkeypatch.setattr(
        'app.services.evaluation_service.SourceService.has_source_class',
        lambda _db, _claim_id, _source_class, source_origin=None: True,
    )

    db = _Db()
    claim = EvaluationService.publish_claim(db, claim_id, approver_id='Applier@Local')  # type: ignore[arg-type]

    assert claim.is_published is True
    assert claim.status == ClaimStatus.published
    assert claim.published_by_reviewer_id == 'applier@local'
    assert db.commit_count == 1
    events = [item for item in db.added if isinstance(item, AdminAuditEvent)]
    assert len(events) == 1
    metadata = json.loads(events[0].metadata_payload or '{}')
    assert metadata['approval_reviewer_id'] == 'approver@local'
    assert metadata['applying_reviewer_id'] == 'applier@local'
    assert metadata['dual_control_enforced'] is True


def test_unpublish_claim_allows_different_reviewers_and_records_audit_metadata(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _PublishedClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.published
            self.fact_checkable = True
            self.is_published = True
            self.published_at = None
            self.published_by_reviewer_id = 'publisher@local'

    class _Db:
        def __init__(self) -> None:
            self.claim = _PublishedClaim()
            self.added: list[object] = []
            self.commit_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return self.claim
            return None

        def add(self, item):  # type: ignore[no-untyped-def]
            self.added.append(item)

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    latest_eval = _FakeEval(reviewer_id='approver@local')
    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation_for_publish',
        lambda *_args, **_kwargs: latest_eval,
    )

    db = _Db()
    claim = EvaluationService.unpublish_claim(db, claim_id, approver_id='Applier@Local')  # type: ignore[arg-type]

    assert claim.is_published is False
    assert claim.status == ClaimStatus.reviewed
    assert claim.published_by_reviewer_id is None
    assert db.commit_count == 1
    events = [item for item in db.added if isinstance(item, AdminAuditEvent)]
    assert len(events) == 1
    metadata = json.loads(events[0].metadata_payload or '{}')
    assert metadata['approval_reviewer_id'] == 'approver@local'
    assert metadata['applying_reviewer_id'] == 'applier@local'
    assert metadata['dual_control_enforced'] is True


def test_unpublish_claim_uses_published_by_reviewer_when_latest_evaluation_missing(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _PublishedClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.published
            self.fact_checkable = True
            self.is_published = True
            self.published_at = None
            self.published_by_reviewer_id = 'publisher@local'

    class _Db:
        def __init__(self) -> None:
            self.claim = _PublishedClaim()
            self.added: list[object] = []
            self.commit_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return self.claim
            return None

        def add(self, item):  # type: ignore[no-untyped-def]
            self.added.append(item)

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation_for_publish',
        lambda *_args, **_kwargs: None,
    )

    db = _Db()
    claim = EvaluationService.unpublish_claim(db, claim_id, approver_id='Applier@Local')  # type: ignore[arg-type]

    assert claim.is_published is False
    assert claim.status == ClaimStatus.reviewed
    assert claim.published_by_reviewer_id is None
    assert db.commit_count == 1
    events = [item for item in db.added if isinstance(item, AdminAuditEvent)]
    assert len(events) == 1
    metadata = json.loads(events[0].metadata_payload or '{}')
    assert metadata['approval_reviewer_id'] == 'publisher@local'
    assert metadata['applying_reviewer_id'] == 'applier@local'
    assert metadata['dual_control_enforced'] is True


def test_publish_claim_uses_lock_aware_latest_evaluation_lookup(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _PublishableClaim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.reviewed
            self.fact_checkable = True
            self.is_published = False
            self.published_at = None
            self.published_by_reviewer_id = None

    class _Db:
        def __init__(self) -> None:
            self.claim = _PublishableClaim()
            self.added: list[object] = []
            self.commit_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return self.claim
            return None

        def add(self, item):  # type: ignore[no-untyped-def]
            self.added.append(item)

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    calls: list[tuple[uuid.UUID, bool]] = []

    def _fake_latest_for_publish(_db, incoming_claim_id, *, lock):  # type: ignore[no-untyped-def]
        calls.append((incoming_claim_id, lock))
        return _FakeEval(reviewer_id='approver@local')

    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation_for_publish',
        _fake_latest_for_publish,
    )
    monkeypatch.setattr(
        'app.services.evaluation_service.SourceService.has_source_class',
        lambda _db, _claim_id, _source_class, source_origin=None: True,
    )

    db = _Db()
    EvaluationService.publish_claim(db, claim_id, approver_id='Applier@Local')  # type: ignore[arg-type]
    assert calls == [(claim_id, True)]


def test_evaluate_claim_first_write_allows_missing_approval_reviewer(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _Claim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.draft

    class _Db:
        def __init__(self) -> None:
            self.claim = _Claim()
            self.added: list[object] = []
            self.commit_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            return self.claim if id_ == claim_id else None

        def add(self, item):  # type: ignore[no-untyped-def]
            self.added.append(item)

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr('app.services.evaluation_service.EvaluationService._latest_evaluation', lambda *_args, **_kwargs: None)
    monkeypatch.setattr('app.services.evaluation_service.SourceService.has_minimum_evidence', lambda *_args, **_kwargs: True)

    db = _Db()
    evaluation = EvaluationService.evaluate_claim(
        db,  # type: ignore[arg-type]
        claim_id,
        EvaluateClaimRequest(
            verdict=Verdict.supported,
            confidence=0.8,
            rationale='Record-backed explanation is provided.',
            citation_notes='Source packet A',
        ),
        reviewer_id='reviewer@local',
    )

    assert evaluation.reviewer_id == 'reviewer@local'
    assert db.commit_count == 1
    assert db.claim.status == ClaimStatus.reviewed
    audit_events = [item for item in db.added if isinstance(item, AdminAuditEvent)]
    assert len(audit_events) == 0


def test_evaluate_claim_overwrite_blocks_same_reviewer_after_normalization(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _Claim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.reviewed

    class _LatestEval:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.claim_id = claim_id
            self.verdict = Verdict.mixed
            self.confidence = 0.5
            self.rationale = 'Prior rationale'
            self.citation_notes = 'Prior notes'
            self.reviewer_id = 'approver@local'
            from datetime import datetime, timezone

            self.created_at = datetime(2026, 5, 12, tzinfo=timezone.utc)

    class _Db:
        def __init__(self) -> None:
            self.claim = _Claim()

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            return self.claim if id_ == claim_id else None

        def add(self, _item):  # type: ignore[no-untyped-def]
            raise AssertionError('add should not be called when overwrite dual-control blocks')

        def commit(self):  # type: ignore[no-untyped-def]
            raise AssertionError('commit should not be called when overwrite dual-control blocks')

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation',
        lambda *_args, **_kwargs: _LatestEval(),
    )
    monkeypatch.setattr('app.services.evaluation_service.SourceService.has_minimum_evidence', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        'app.services.evaluation_service.AuthService.resolve_active_reviewer_id',
        lambda _db, reviewer_id, *, allowed_roles=None: reviewer_id.strip().lower() if reviewer_id else None,
    )

    try:
        EvaluationService.evaluate_claim(
            _Db(),  # type: ignore[arg-type]
            claim_id,
            EvaluateClaimRequest(
                verdict=Verdict.supported,
                confidence=0.81,
                rationale='Updated rationale references neutral records.',
                citation_notes='Source packet B',
            ),
            reviewer_id=' approver@local ',
            approval_reviewer_id='  APPROVER@LOCAL ',
        )
        assert False, 'Expected evaluation_overwrite_dual_control_required'
    except AppError as exc:
        assert exc.code == 'evaluation_overwrite_dual_control_required'
        assert exc.status_code == 409
        assert exc.details['claim_id'] == str(claim_id)
        assert exc.details['approval_reviewer_id'] == 'approver@local'
        assert exc.details['applying_reviewer_id'] == 'approver@local'
        assert exc.details['action'] == 'evaluate_overwrite'


def test_evaluate_claim_overwrite_allows_different_reviewer_and_writes_audit(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _Claim:
        def __init__(self) -> None:
            self.id = claim_id
            self.status = ClaimStatus.reviewed

    class _LatestEval:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.claim_id = claim_id
            self.verdict = Verdict.unsupported
            self.confidence = 0.33
            self.rationale = 'Prior rationale'
            self.citation_notes = 'Prior notes'
            self.reviewer_id = 'approver@local'
            from datetime import datetime, timezone

            self.created_at = datetime(2026, 5, 12, tzinfo=timezone.utc)

    class _Db:
        def __init__(self) -> None:
            self.claim = _Claim()
            self.added: list[object] = []
            self.commit_count = 0

        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            return self.claim if id_ == claim_id else None

        def add(self, item):  # type: ignore[no-untyped-def]
            self.added.append(item)

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_count += 1

        def refresh(self, _item):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr(
        'app.services.evaluation_service.EvaluationService._latest_evaluation',
        lambda *_args, **_kwargs: _LatestEval(),
    )
    monkeypatch.setattr('app.services.evaluation_service.SourceService.has_minimum_evidence', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        'app.services.evaluation_service.AuthService.resolve_active_reviewer_id',
        lambda _db, reviewer_id, *, allowed_roles=None: reviewer_id.strip().lower() if reviewer_id else None,
    )

    db = _Db()
    evaluation = EvaluationService.evaluate_claim(
        db,  # type: ignore[arg-type]
        claim_id,
        EvaluateClaimRequest(
            verdict=Verdict.supported,
            confidence=0.86,
            rationale='Updated rationale references neutral records.',
            citation_notes='Source packet C',
        ),
        reviewer_id='applier@local',
        approval_reviewer_id=' APPROVER@LOCAL ',
    )

    assert evaluation.reviewer_id == 'applier@local'
    assert db.commit_count == 1
    events = [item for item in db.added if isinstance(item, AdminAuditEvent)]
    assert len(events) == 1
    metadata = json.loads(events[0].metadata_payload or '{}')
    assert metadata['approval_reviewer_id'] == 'approver@local'
    assert metadata['applying_reviewer_id'] == 'applier@local'
    assert metadata['dual_control_enforced'] is True
