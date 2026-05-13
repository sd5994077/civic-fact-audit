import uuid
from datetime import datetime, timezone
import subprocess

from app.core.errors import AppError
from app.models.entities import AdminAuditEvent, AdminJobRun
from app.schemas.api import AdminJobRunCreateRequest
from app.services.admin_job_service import AdminJobService


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

    def get(self, model, obj_id):  # type: ignore[no-untyped-def]
        row = self.rows.get(obj_id)
        if row is not None and isinstance(row, model):
            return row
        return None

    def execute(self, _query):  # type: ignore[no-untyped-def]
        class _Result:
            def __init__(self, rows):  # type: ignore[no-untyped-def]
                self._rows = rows

            def scalars(self):  # type: ignore[no-untyped-def]
                return self

            def all(self):  # type: ignore[no-untyped-def]
                return [row for row in self._rows if isinstance(row, AdminJobRun)]

            def first(self):  # type: ignore[no-untyped-def]
                return None

        return _Result(self.rows.values())


def test_enqueue_job_rejects_not_allowlisted_job_type() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='not_allowlisted_job', input_payload={})

    try:
        AdminJobService.enqueue_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_type_not_allowed'
    except AppError as exc:
        assert exc.code == 'job_type_not_allowed'


def test_enqueue_job_rejects_missing_intake_profile_id() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='ingest_candidate_roster', input_payload={})

    try:
        AdminJobService.enqueue_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_input_invalid'
    except AppError as exc:
        assert exc.code == 'job_input_invalid'
        assert 'profile_id' in exc.details.get('missing_fields', [])


def test_enqueue_job_accepts_whitespace_profile_key_after_normalization() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='ingest_candidate_roster', input_payload={'profile_id ': 'tx_2026_senate'})

    row = AdminJobService.enqueue_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
    assert row['status'] == 'queued'
    assert row['input_payload'] == {'profile_id': 'tx_2026_senate'}
    assert row['attempt_count'] == 0


def test_enqueue_job_rejects_unsupported_statement_batch_for_profile() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(
        job_type='ingest_statement_batch',
        input_payload={'profile_id': 'tx_2026_ag_runoff', 'statement_batch': 'round3'},
    )

    try:
        AdminJobService.enqueue_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected job_input_invalid'
    except AppError as exc:
        assert exc.code == 'job_input_invalid'
        assert exc.details.get('allowed_values', {}).get('statement_batch') == ['round2', 'starter']


def test_enqueue_job_records_admin_job_triggered_audit_event() -> None:
    db = _FakeDb()
    payload = AdminJobRunCreateRequest(job_type='generate_publish_queue_report', input_payload={'profile_id': 'tx_2026_senate'})

    row = AdminJobService.enqueue_job(db, payload, requested_by_reviewer_id='admin@local')  # type: ignore[arg-type]

    audit_rows = [saved for saved in db.rows.values() if isinstance(saved, AdminAuditEvent)]
    assert len(audit_rows) == 1
    saved_event = audit_rows[0]
    assert saved_event.action == 'admin_job_triggered'
    assert saved_event.entity_type == 'admin_job_run'
    assert saved_event.entity_id == str(row['id'])


def test_mark_failed_or_requeued_requeues_before_max_attempts() -> None:
    db = _FakeDb()
    now = datetime.now(timezone.utc)
    job_run = AdminJobRun(
        job_type='generate_publish_queue_report',
        status='running',
        requested_by_reviewer_id='admin@local',
        input_payload='{}',
        attempt_count=1,
        max_attempts=3,
        next_attempt_at=None,
        lease_expires_at=now,
    )
    db.add(job_run)

    AdminJobService._mark_failed_or_requeued(
        db,  # type: ignore[arg-type]
        job_run,
        error_code='job_execution_failed',
        error_message='failed',
        error_details={'return_code': 1},
    )
    assert job_run.status == 'queued'
    assert job_run.next_attempt_at is not None
    assert job_run.finished_at is None
    assert job_run.last_error_code == 'job_execution_failed'


def test_mark_failed_or_requeued_marks_failed_after_max_attempts() -> None:
    db = _FakeDb()
    now = datetime.now(timezone.utc)
    job_run = AdminJobRun(
        job_type='generate_publish_queue_report',
        status='running',
        requested_by_reviewer_id='admin@local',
        input_payload='{}',
        attempt_count=3,
        max_attempts=3,
        next_attempt_at=None,
        lease_expires_at=now,
    )
    db.add(job_run)

    AdminJobService._mark_failed_or_requeued(
        db,  # type: ignore[arg-type]
        job_run,
        error_code='job_execution_failed',
        error_message='failed',
        error_details={'return_code': 1},
    )
    assert job_run.status == 'failed'
    assert job_run.next_attempt_at is None
    assert job_run.finished_at is not None


def test_get_job_metadata_is_async_flagged() -> None:
    metadata = AdminJobService.get_job_metadata()
    assert metadata.get('synchronous_execution') is False


def test_run_job_command_timeout_raises_job_execution_failed(monkeypatch) -> None:
    def _raise_timeout(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(
            cmd=['python', '-m', 'app.scripts.generate_tx_2026_publish_queue_report'],
            timeout=300,
            output='stdout before timeout',
            stderr='stderr before timeout',
        )

    monkeypatch.setattr('app.services.admin_job_service.subprocess.run', _raise_timeout)

    try:
        AdminJobService._run_job_command('app.scripts.generate_tx_2026_publish_queue_report', dry_run=False)
        assert False, 'Expected job_execution_failed timeout'
    except AppError as exc:
        assert exc.code == 'job_execution_failed'
        assert exc.details is not None
        assert exc.details.get('timed_out') is True


def test_health_failure_summary_serializes_job_run_fields() -> None:
    now = datetime(2026, 5, 13, tzinfo=timezone.utc)
    job_run = AdminJobRun(
        id=uuid.uuid4(),
        job_type='extract_claims_batch',
        status='failed',
        requested_by_reviewer_id='admin@local',
        input_payload='{}',
        attempt_count=3,
        max_attempts=3,
        last_error_code='job_execution_failed',
        finished_at=now,
        created_at=now,
        updated_at=now,
    )
    summary = AdminJobService._to_health_failure_summary(job_run)
    assert summary['job_type'] == 'extract_claims_batch'
    assert summary['attempt_count'] == 3
    assert summary['max_attempts'] == 3
    assert summary['last_error_code'] == 'job_execution_failed'
    assert summary['finished_at'] == now
    assert summary['created_at'] == now


def test_health_failure_summary_handles_zero_attempts() -> None:
    now = datetime(2026, 5, 13, tzinfo=timezone.utc)
    job_run = AdminJobRun(
        id=uuid.uuid4(),
        job_type='backfill_claim_reviewability',
        status='failed',
        requested_by_reviewer_id='admin@local',
        input_payload='{}',
        attempt_count=0,
        max_attempts=3,
        last_error_code=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
    )
    summary = AdminJobService._to_health_failure_summary(job_run)
    assert summary['attempt_count'] == 0
    assert summary['last_error_code'] is None
    assert summary['finished_at'] is None
