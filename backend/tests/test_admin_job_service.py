import uuid
from datetime import datetime, timezone

from app.core.errors import AppError
from app.models.entities import AdminAuditEvent, AdminJobRun
from app.services.admin_job_service import AdminJobService
from app.schemas.api import AdminJobRunCreateRequest


class _FakeDb:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, object] = {}

    def add(self, obj):  # type: ignore[no-untyped-def]
        if obj.id is None:
            obj.id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        if getattr(obj, 'created_at', None) is None:
            obj.created_at = now
        obj.updated_at = now
        self.rows[obj.id] = obj

    def commit(self):  # type: ignore[no-untyped-def]
        return None

    def flush(self):  # type: ignore[no-untyped-def]
        return None

    def refresh(self, obj):  # type: ignore[no-untyped-def]
        obj.updated_at = datetime.now(timezone.utc)
        return None


def test_create_and_run_job_rejects_not_allowlisted_job_type() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='not_allowlisted_job', input_payload={})

    try:
        AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_type_not_allowed'
    except AppError as exc:
        assert exc.code == 'job_type_not_allowed'


def test_create_and_run_job_rejects_missing_intake_profile_id() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='ingest_candidate_roster', input_payload={})

    try:
        AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_input_invalid'
    except AppError as exc:
        assert exc.code == 'job_input_invalid'
        assert 'profile_id' in exc.details.get('missing_fields', [])


def test_create_and_run_job_accepts_whitespace_profile_key_after_normalization(monkeypatch) -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='ingest_candidate_roster', input_payload={'profile_id ': 'tx_2026_senate'})

    monkeypatch.setattr(
        AdminJobService,
        '_run_job_command',
        staticmethod(lambda _module, *, dry_run: {'return_code': 0, 'dry_run': dry_run}),
    )

    row = AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
    assert row['status'] == 'succeeded'
    assert row['input_payload'] == {'profile_id': 'tx_2026_senate'}


def test_create_and_run_job_rejects_unknown_profile_id() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(
        job_type='ingest_statement_batch',
        input_payload={'profile_id': 'unknown_profile', 'statement_batch': 'starter'},
    )

    try:
        AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_input_invalid'
    except AppError as exc:
        assert exc.code == 'job_input_invalid'
        assert 'profile_id' in exc.details.get('allowed_values', {})


def test_create_and_run_job_rejects_unsupported_statement_batch_for_profile() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(
        job_type='ingest_statement_batch',
        input_payload={'profile_id': 'tx_2026_ag_runoff', 'statement_batch': 'round3'},
    )

    try:
        AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_input_invalid'
    except AppError as exc:
        assert exc.code == 'job_input_invalid'
        assert exc.details.get('allowed_values', {}).get('statement_batch') == ['starter']


def test_create_and_run_job_routes_roster_job_to_selected_profile_module(monkeypatch) -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='ingest_candidate_roster', input_payload={'profile_id': 'tx_2026_ag_runoff'})
    called: dict[str, object] = {}

    def _fake_run(module: str, *, dry_run: bool) -> dict[str, object]:
        called['module'] = module
        called['dry_run'] = dry_run
        return {'return_code': 0}

    monkeypatch.setattr(AdminJobService, '_run_job_command', staticmethod(_fake_run))

    row = AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]

    assert row['status'] == 'succeeded'
    assert called['module'] == 'app.scripts.ingest_tx_2026_attorney_general_runoff_roster'
    assert called['dry_run'] is False
    assert row['input_payload'] == {'profile_id': 'tx_2026_ag_runoff'}


def test_create_and_run_job_routes_statement_job_to_selected_profile_batch_module(monkeypatch) -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(
        job_type='ingest_statement_batch',
        input_payload={'profile_id': 'tx_2026_senate', 'statement_batch': 'round3'},
    )
    called: dict[str, object] = {}

    def _fake_run(module: str, *, dry_run: bool) -> dict[str, object]:
        called['module'] = module
        called['dry_run'] = dry_run
        return {'return_code': 0}

    monkeypatch.setattr(AdminJobService, '_run_job_command', staticmethod(_fake_run))

    row = AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]

    assert row['status'] == 'succeeded'
    assert called['module'] == 'app.scripts.ingest_tx_2026_statement_batch_round3'
    assert called['dry_run'] is False
    assert row['input_payload'] == {'profile_id': 'tx_2026_senate', 'statement_batch': 'round3'}


def test_create_and_run_job_marks_succeeded(monkeypatch) -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='generate_publish_queue_report', input_payload={})

    monkeypatch.setattr(
        AdminJobService,
        '_run_job_command',
        staticmethod(lambda _module, *, dry_run: {'return_code': 0, 'dry_run': dry_run}),
    )

    row = AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]

    assert row['job_type'] == 'generate_publish_queue_report'
    assert row['status'] == 'succeeded'
    assert row['requested_by_reviewer_id'] == 'admin@local'
    assert row['result_summary'] is not None
    assert row['result_summary']['return_code'] == 0


def test_create_and_run_job_records_admin_job_triggered_audit_event(monkeypatch) -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='generate_publish_queue_report', input_payload={})

    monkeypatch.setattr(
        AdminJobService,
        '_run_job_command',
        staticmethod(lambda _module, *, dry_run: {'return_code': 0, 'dry_run': dry_run}),
    )

    row = AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]

    audit_rows = [saved for saved in db.rows.values() if isinstance(saved, AdminAuditEvent)]
    assert len(audit_rows) == 1
    saved_event = audit_rows[0]
    assert saved_event.action == 'admin_job_triggered'
    assert saved_event.entity_type == 'admin_job_run'
    assert saved_event.entity_id == str(row['id'])
    assert saved_event.after_payload is not None


def test_create_and_run_job_marks_failed_on_execution_error(monkeypatch) -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='generate_publish_queue_report', input_payload={})

    def _raise_exec_error(_module: str, *, dry_run: bool):  # type: ignore[no-untyped-def]
        raise AppError(
            'job_execution_failed',
            'Admin job execution failed.',
            status_code=500,
            details={'return_code': 1, 'dry_run': dry_run},
        )

    monkeypatch.setattr(AdminJobService, '_run_job_command', staticmethod(_raise_exec_error))

    try:
        AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_execution_failed'
    except AppError as exc:
        assert exc.code == 'job_execution_failed'

    job_rows = [row for row in db.rows.values() if isinstance(row, AdminJobRun)]
    assert len(job_rows) == 1
    saved = job_rows[0]
    assert saved.status == 'failed'
    assert saved.error_details is not None


def test_get_job_metadata_includes_profiles_and_schemas() -> None:
    metadata = AdminJobService.get_job_metadata()
    assert 'allowlist_version' in metadata
    assert 'intake_profile_version' in metadata
    assert metadata.get('synchronous_execution') is True
    assert isinstance(metadata.get('jobs'), list)
    assert isinstance(metadata.get('intake_profiles'), list)
    roster_schema = next((item for item in metadata['jobs'] if item.get('job_type') == 'ingest_candidate_roster'), None)
    assert roster_schema is not None
    assert 'profile_id' in roster_schema['input_schema'].get('allowed_values', {})
