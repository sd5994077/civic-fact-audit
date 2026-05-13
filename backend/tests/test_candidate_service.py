import uuid
from datetime import datetime, timezone

from app.core.errors import AppError
from app.models.enums import RaceStage
from app.services.candidate_service import CandidateRosterUpsert, CandidateService
from app.schemas.api import CandidateCreate
from app.schemas.api import CandidateUpdate


def test_build_candidate_query_applies_all_filters() -> None:
    query = CandidateService._build_candidate_query(
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=RaceStage.primary,
    )

    compiled = str(query)
    assert 'lower(candidates.state)' in compiled
    assert 'lower(candidates.office)' in compiled
    assert 'candidates.election_cycle =' in compiled
    assert 'candidates.race_stage =' in compiled


def test_build_candidate_query_without_optional_filters() -> None:
    query = CandidateService._build_candidate_query(
        state=None,
        office=None,
        election_cycle=None,
        race_stage=None,
    )

    compiled = str(query)
    assert 'WHERE' not in compiled


def test_get_candidate_raises_not_found() -> None:
    class _FakeDb:
        def get(self, _model, _candidate_id):  # type: ignore[no-untyped-def]
            return None

    try:
        CandidateService.get_candidate(_FakeDb(), uuid.uuid4())  # type: ignore[arg-type]
        assert False, 'Expected candidate_not_found'
    except AppError as exc:
        assert exc.code == 'candidate_not_found'


def test_update_candidate_blocks_race_context_changes_after_statements() -> None:
    candidate_id = uuid.uuid4()

    class _FakeCandidate:
        def __init__(self) -> None:
            self.id = candidate_id
            self.name = 'Candidate A'
            self.party = 'Independent'
            self.office = 'US Senate'
            self.state = 'TX'
            self.election_cycle = 2026
            self.race_stage = RaceStage.primary

    class _ScalarResult:
        def scalar_one(self):  # type: ignore[no-untyped-def]
            return 1

    class _FakeDb:
        def __init__(self) -> None:
            self.commit_called = False
            self.candidate = _FakeCandidate()

        def get(self, _model, _candidate_id):  # type: ignore[no-untyped-def]
            return self.candidate

        def execute(self, _query):  # type: ignore[no-untyped-def]
            return _ScalarResult()

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_called = True

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    payload = CandidateUpdate(approval_reviewer_id='approver@local', state='CA')
    db = _FakeDb()
    try:
        CandidateService.update_candidate(db, candidate_id, payload)  # type: ignore[arg-type]
        assert False, 'Expected candidate_update_conflict'
    except AppError as exc:
        assert exc.code == 'candidate_update_conflict'
    assert db.commit_called is False
    assert db.candidate.state == 'TX'


def test_update_candidate_allows_non_race_context_changes_after_statements() -> None:
    candidate_id = uuid.uuid4()

    class _FakeCandidate:
        def __init__(self) -> None:
            self.id = candidate_id
            self.name = 'Candidate A'
            self.party = 'Independent'
            self.office = 'US Senate'
            self.state = 'TX'
            self.election_cycle = 2026
            self.race_stage = RaceStage.primary

    class _ScalarResult:
        def scalar_one(self):  # type: ignore[no-untyped-def]
            return 2

    class _FakeDb:
        def __init__(self) -> None:
            self.commit_called = False
            self.candidate = _FakeCandidate()

        def get(self, _model, _candidate_id):  # type: ignore[no-untyped-def]
            return self.candidate

        def execute(self, _query):  # type: ignore[no-untyped-def]
            return _ScalarResult()

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_called = True

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    payload = CandidateUpdate(approval_reviewer_id='approver@local', party='Nonpartisan')
    db = _FakeDb()
    updated = CandidateService.update_candidate(db, candidate_id, payload)  # type: ignore[arg-type]
    assert db.commit_called is True
    assert updated.party == 'Nonpartisan'


def test_create_candidate_rejects_blank_name_after_trim() -> None:
    class _FakeDb:
        def add(self, _candidate):  # type: ignore[no-untyped-def]
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            return None

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    payload = CandidateCreate(name='   ', approval_reviewer_id='approver@local')
    try:
        CandidateService.create_candidate(_FakeDb(), payload)  # type: ignore[arg-type]
        assert False, 'Expected candidate_invalid'
    except AppError as exc:
        assert exc.code == 'candidate_invalid'


def test_create_candidate_flushes_before_audit_event(monkeypatch) -> None:
    captured = {}
    candidate_id = uuid.uuid4()

    class _FakeDb:
        def __init__(self) -> None:
            self.candidate = None
            self.flush_called = False

        def add(self, candidate):  # type: ignore[no-untyped-def]
            self.candidate = candidate

        def flush(self):  # type: ignore[no-untyped-def]
            self.flush_called = True
            if self.candidate is not None:
                self.candidate.id = candidate_id

        def commit(self):  # type: ignore[no-untyped-def]
            return None

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    def _fake_record_event(
        _db,
        *,
        actor_reviewer_id,
        action,
        entity_type,
        entity_id,
        before_payload,
        after_payload,
        metadata,
        commit,
    ):  # type: ignore[no-untyped-def]
        captured['actor_reviewer_id'] = actor_reviewer_id
        captured['action'] = action
        captured['entity_type'] = entity_type
        captured['entity_id'] = entity_id
        captured['after_payload'] = after_payload
        captured['commit'] = commit

    monkeypatch.setattr('app.services.candidate_service.AdminAuditService.record_event', _fake_record_event)

    db = _FakeDb()
    payload = CandidateCreate(
        name='Candidate A',
        approval_reviewer_id='approver@local',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary,
    )
    CandidateService.create_candidate(db, payload, actor_reviewer_id='admin@local')  # type: ignore[arg-type]

    assert db.flush_called is True
    assert captured['actor_reviewer_id'] == 'admin@local'
    assert captured['action'] == 'candidate_created'
    assert captured['entity_type'] == 'candidate'
    assert captured['entity_id'] == str(candidate_id)
    assert captured['after_payload']['id'] == str(candidate_id)
    assert captured['commit'] is False


def test_update_candidate_rejects_blank_name_after_trim() -> None:
    candidate_id = uuid.uuid4()

    class _FakeCandidate:
        def __init__(self) -> None:
            self.id = candidate_id
            self.name = 'Candidate A'
            self.party = 'Independent'
            self.office = 'US Senate'
            self.state = 'TX'
            self.election_cycle = 2026
            self.race_stage = RaceStage.primary

    class _FakeDb:
        def __init__(self) -> None:
            self.candidate = _FakeCandidate()

        def get(self, _model, _candidate_id):  # type: ignore[no-untyped-def]
            return self.candidate

        def execute(self, _query):  # type: ignore[no-untyped-def]
            raise AssertionError('execute should not be called when validation fails first')

        def commit(self):  # type: ignore[no-untyped-def]
            raise AssertionError('commit should not be called when validation fails')

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    try:
        CandidateService.update_candidate(
            _FakeDb(), candidate_id, CandidateUpdate(approval_reviewer_id='approver@local', name='   ')
        )  # type: ignore[arg-type]
        assert False, 'Expected candidate_invalid'
    except AppError as exc:
        assert exc.code == 'candidate_invalid'


def test_update_candidate_rejects_null_is_active() -> None:
    candidate_id = uuid.uuid4()

    class _FakeCandidate:
        def __init__(self) -> None:
            self.id = candidate_id
            self.name = 'Candidate A'
            self.party = 'Independent'
            self.office = 'US Senate'
            self.state = 'TX'
            self.election_cycle = 2026
            self.race_stage = RaceStage.primary
            self.is_active = True
            self.roster_status = None
            self.roster_source_url = None
            self.roster_checked_at = None
            self.roster_notes = None

    class _FakeDb:
        def __init__(self) -> None:
            self.candidate = _FakeCandidate()

        def get(self, _model, _candidate_id):  # type: ignore[no-untyped-def]
            return self.candidate

        def execute(self, _query):  # type: ignore[no-untyped-def]
            raise AssertionError('execute should not be called when validation fails first')

        def commit(self):  # type: ignore[no-untyped-def]
            raise AssertionError('commit should not be called when validation fails')

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    try:
        CandidateService.update_candidate(
            _FakeDb(), candidate_id, CandidateUpdate(approval_reviewer_id='approver@local', is_active=None)
        )  # type: ignore[arg-type]
        assert False, 'Expected candidate_update_invalid'
    except AppError as exc:
        assert exc.code == 'candidate_update_invalid'


def test_upsert_roster_candidates_persists_roster_metadata(monkeypatch) -> None:
    class _FakeDb:
        def __init__(self) -> None:
            self.added = []
            self.commit_called = False

        def add(self, candidate):  # type: ignore[no-untyped-def]
            self.added.append(candidate)

        def commit(self):  # type: ignore[no-untyped-def]
            self.commit_called = True

    monkeypatch.setattr(
        CandidateService,
        '_get_existing_candidate_by_race_context',
        staticmethod(lambda _db, _entry: None),
    )
    checked_at = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    roster = [
        CandidateRosterUpsert(
            name='Candidate A',
            party='Independent',
            office='US Senate',
            state='TX',
            election_cycle=2026,
            race_stage=RaceStage.primary,
            roster_status='runoff_reported',
            roster_source_url='https://example.org/roster',
            roster_checked_at=checked_at,
            roster_notes='Snapshot captured.',
            is_active=True,
        )
    ]

    db = _FakeDb()
    created, updated = CandidateService.upsert_roster_candidates(db, roster)  # type: ignore[arg-type]

    assert db.commit_called is True
    assert created == 1
    assert updated == 0
    assert len(db.added) == 1
    assert db.added[0].roster_status == 'runoff_reported'
    assert db.added[0].roster_source_url == 'https://example.org/roster'
    assert db.added[0].roster_checked_at == checked_at


def test_create_candidate_blocks_when_approval_and_applying_reviewer_match() -> None:
    class _FakeDb:
        def add(self, _candidate):  # type: ignore[no-untyped-def]
            return None

        def commit(self):  # type: ignore[no-untyped-def]
            raise AssertionError('commit should not be called when dual-control blocks')

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    payload = CandidateCreate(name='Candidate A', approval_reviewer_id='admin@local')
    try:
        CandidateService.create_candidate(_FakeDb(), payload, actor_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected candidate_dual_control_required'
    except AppError as exc:
        assert exc.code == 'candidate_dual_control_required'
        assert exc.status_code == 409
        assert exc.details['approval_reviewer_id'] == 'admin@local'
        assert exc.details['applying_reviewer_id'] == 'admin@local'
        assert exc.details['action'] == 'candidate_create'


def test_update_candidate_blocks_when_approval_and_applying_reviewer_match() -> None:
    candidate_id = uuid.uuid4()

    class _FakeCandidate:
        def __init__(self) -> None:
            self.id = candidate_id
            self.name = 'Candidate A'
            self.party = 'Independent'
            self.office = 'US Senate'
            self.state = 'TX'
            self.election_cycle = 2026
            self.race_stage = RaceStage.primary
            self.is_active = True
            self.roster_status = None
            self.roster_source_url = None
            self.roster_checked_at = None
            self.roster_notes = None

    class _FakeDb:
        def __init__(self) -> None:
            self.candidate = _FakeCandidate()

        def get(self, _model, _candidate_id):  # type: ignore[no-untyped-def]
            return self.candidate

        def execute(self, _query):  # type: ignore[no-untyped-def]
            class _ScalarResult:
                def scalar_one(self):  # type: ignore[no-untyped-def]
                    return 0

            return _ScalarResult()

        def commit(self):  # type: ignore[no-untyped-def]
            raise AssertionError('commit should not be called when dual-control blocks')

        def refresh(self, _candidate):  # type: ignore[no-untyped-def]
            return None

    try:
        CandidateService.update_candidate(
            _FakeDb(),
            candidate_id,
            CandidateUpdate(approval_reviewer_id='ADMIN@LOCAL', party='Democratic'),
            actor_reviewer_id=' admin@local ',
        )  # type: ignore[arg-type]
        assert False, 'Expected candidate_dual_control_required'
    except AppError as exc:
        assert exc.code == 'candidate_dual_control_required'
        assert exc.status_code == 409
        assert exc.details['candidate_id'] == str(candidate_id)
        assert exc.details['approval_reviewer_id'] == 'admin@local'
        assert exc.details['applying_reviewer_id'] == 'admin@local'
        assert exc.details['action'] == 'candidate_update'
