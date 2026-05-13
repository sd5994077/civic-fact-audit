import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.db.database import get_db
from app.main import app
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity


class _FakeDb:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, object] = {}

    def add(self, obj: object) -> None:
        obj_id = getattr(obj, 'id', None)
        if obj_id is None:
            setattr(obj, 'id', uuid.uuid4())
            obj_id = getattr(obj, 'id')
        now = datetime.now(timezone.utc)
        if getattr(obj, 'created_at', None) is None:
            setattr(obj, 'created_at', now)
        setattr(obj, 'updated_at', now)
        self.rows[obj_id] = obj

    def commit(self) -> None:
        return None

    def flush(self) -> None:
        return None

    def refresh(self, obj: object) -> None:
        setattr(obj, 'updated_at', datetime.now(timezone.utc))


_FAKE_DB = _FakeDb()


def _override_admin() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='admin@local', role='admin')


def _override_db():  # type: ignore[no-untyped-def]
    yield object()


def _override_fake_db():  # type: ignore[no-untyped-def]
    yield _FAKE_DB


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> None:
    yield
    app.dependency_overrides.clear()


def test_create_admin_job_requires_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_admin, None)

    client = TestClient(app)
    response = client.post('/v1/admin/jobs', json={'job_type': 'generate_publish_queue_report', 'input_payload': {}})

    assert response.status_code == 401


def test_create_admin_job_returns_422_for_bad_job_type(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin

    def _fake_create(_db, _payload, *, requested_by_reviewer_id):  # type: ignore[no-untyped-def]
        assert requested_by_reviewer_id == 'admin@local'
        raise AppError('job_type_not_allowed', 'Job type is not allowlisted for admin execution.', status_code=422)

    monkeypatch.setattr('app.api.v1.admin_jobs.AdminJobService.enqueue_job', _fake_create)

    client = TestClient(app)
    response = client.post('/v1/admin/jobs', json={'job_type': 'bad_job_type', 'input_payload': {}})

    assert response.status_code == 422
    assert response.json()['error']['code'] == 'job_type_not_allowed'


def test_create_admin_job_success(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    job_id = uuid.uuid4()
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)

    def _fake_create(_db, _payload, *, requested_by_reviewer_id):  # type: ignore[no-untyped-def]
        assert requested_by_reviewer_id == 'admin@local'
        return {
            'id': job_id,
            'job_type': 'generate_publish_queue_report',
            'status': 'queued',
            'requested_by_reviewer_id': 'admin@local',
            'input_payload': {},
            'started_at': now,
            'finished_at': now,
            'attempt_count': 0,
            'max_attempts': 3,
            'next_attempt_at': now,
            'lease_expires_at': None,
            'last_error_code': None,
            'result_summary': None,
            'error_details': None,
            'created_at': now,
            'updated_at': now,
        }

    monkeypatch.setattr('app.api.v1.admin_jobs.AdminJobService.enqueue_job', _fake_create)

    client = TestClient(app)
    response = client.post('/v1/admin/jobs', json={'job_type': 'generate_publish_queue_report', 'input_payload': {}})

    assert response.status_code == 200
    body = response.json()
    assert body['id'] == str(job_id)
    assert body['status'] == 'queued'


def test_list_admin_jobs_success(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    job_id = uuid.uuid4()
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)

    def _fake_list(_db, *, status, job_type, limit):  # type: ignore[no-untyped-def]
        assert status is None
        assert job_type is None
        assert limit == 100
        return [
            {
                'id': job_id,
                'job_type': 'generate_publish_queue_report',
                'status': 'queued',
                'requested_by_reviewer_id': 'admin@local',
                'input_payload': {},
                'started_at': now,
                'finished_at': now,
                'attempt_count': 0,
                'max_attempts': 3,
                'next_attempt_at': now,
                'lease_expires_at': None,
                'last_error_code': None,
                'result_summary': None,
                'error_details': None,
                'created_at': now,
                'updated_at': now,
            }
        ]

    monkeypatch.setattr('app.api.v1.admin_jobs.AdminJobService.list_job_runs', _fake_list)

    client = TestClient(app)
    response = client.get('/v1/admin/jobs')

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]['id'] == str(job_id)


def test_get_admin_job_metadata_success(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin

    def _fake_metadata():  # type: ignore[no-untyped-def]
        return {
            'allowlist_version': 'allowlist_v_test',
            'intake_profile_version': 'profiles_v_test',
            'synchronous_execution': False,
            'jobs': [
                {
                    'job_type': 'ingest_candidate_roster',
                    'description': 'Roster',
                    'input_schema': {
                        'required_fields': ['profile_id'],
                        'allowed_fields': ['profile_id'],
                        'field_types': {'profile_id': 'string'},
                        'allowed_values': {'profile_id': ['tx_2026_senate']},
                        'supports_dry_run': False,
                    },
                }
            ],
            'intake_profiles': [
                {
                    'profile_id': 'tx_2026_senate',
                    'label': 'Texas 2026 U.S. Senate',
                    'state': 'TX',
                    'office': 'US Senate',
                    'election_cycle': 2026,
                    'race_stage': 'primary',
                    'statement_batches': ['starter', 'round2', 'round3', 'round4'],
                }
            ],
        }

    monkeypatch.setattr('app.api.v1.admin_jobs.AdminJobService.get_job_metadata', _fake_metadata)

    client = TestClient(app)
    response = client.get('/v1/admin/jobs/metadata')

    assert response.status_code == 200
    body = response.json()
    assert body['allowlist_version'] == 'allowlist_v_test'
    assert body['intake_profile_version'] == 'profiles_v_test'
    assert len(body['jobs']) == 1
    assert body['jobs'][0]['job_type'] == 'ingest_candidate_roster'
    assert len(body['intake_profiles']) == 1


def test_get_admin_job_success(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    job_id = uuid.uuid4()
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)

    def _fake_get(_db, _job_run_id):  # type: ignore[no-untyped-def]
        assert _job_run_id == job_id
        return {
            'id': job_id,
            'job_type': 'generate_publish_queue_report',
            'status': 'queued',
            'requested_by_reviewer_id': 'admin@local',
            'input_payload': {},
            'started_at': now,
            'finished_at': now,
            'attempt_count': 0,
            'max_attempts': 3,
            'next_attempt_at': now,
            'lease_expires_at': None,
            'last_error_code': None,
            'result_summary': None,
            'error_details': None,
            'created_at': now,
            'updated_at': now,
        }

    monkeypatch.setattr('app.api.v1.admin_jobs.AdminJobService.get_job_run', _fake_get)

    client = TestClient(app)
    response = client.get(f'/v1/admin/jobs/{job_id}')

    assert response.status_code == 200
    assert response.json()['id'] == str(job_id)


def test_admin_jobs_metadata_and_enqueue_routing_sync(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_fake_db
    app.dependency_overrides[require_admin] = _override_admin
    _FAKE_DB.rows.clear()

    client = TestClient(app)

    metadata_response = client.get('/v1/admin/jobs/metadata')
    assert metadata_response.status_code == 200
    metadata = metadata_response.json()

    intake_profile = next((item for item in metadata['intake_profiles'] if item['profile_id'] == 'tx_2026_senate'), None)
    assert intake_profile is not None
    available_batches = intake_profile['statement_batches']
    assert available_batches
    selected_batch = 'round4' if 'round4' in available_batches else available_batches[0]

    assert any(item['job_type'] == 'ingest_statement_batch' for item in metadata['jobs'])

    create_response = client.post(
        '/v1/admin/jobs',
        json={
            'job_type': 'ingest_statement_batch',
            'input_payload': {'profile_id': intake_profile['profile_id'], 'statement_batch': selected_batch},
        },
    )

    assert create_response.status_code == 200
    body = create_response.json()
    assert body['status'] == 'queued'
    assert body['input_payload'] == {'profile_id': intake_profile['profile_id'], 'statement_batch': selected_batch}
    assert body['result_summary'] is None


def test_create_admin_job_rejects_invalid_profile_batch_pairing_with_allowed_values() -> None:
    app.dependency_overrides[get_db] = _override_fake_db
    app.dependency_overrides[require_admin] = _override_admin
    _FAKE_DB.rows.clear()

    client = TestClient(app)

    metadata_response = client.get('/v1/admin/jobs/metadata')
    assert metadata_response.status_code == 200
    metadata = metadata_response.json()

    intake_profile = next((item for item in metadata['intake_profiles'] if item['profile_id'] == 'tx_2026_ag_runoff'), None)
    assert intake_profile is not None
    allowed_batches = intake_profile['statement_batches']
    assert allowed_batches
    unsupported_batch = 'round3'
    if unsupported_batch in allowed_batches:
        unsupported_batch = 'unsupported_batch_for_test'

    response = client.post(
        '/v1/admin/jobs',
        json={
            'job_type': 'ingest_statement_batch',
            'input_payload': {'profile_id': intake_profile['profile_id'], 'statement_batch': unsupported_batch},
        },
    )

    assert response.status_code == 422
    error = response.json()['error']
    assert error['code'] == 'job_input_invalid'
    details = error['details']
    assert isinstance(details.get('missing_fields'), list)
    assert isinstance(details.get('unsupported_fields'), list)
    assert details.get('allowed_values', {}).get('statement_batch') == allowed_batches


def test_create_admin_job_routes_profile_scoped_report_for_ag_runoff(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_fake_db
    app.dependency_overrides[require_admin] = _override_admin
    _FAKE_DB.rows.clear()
    client = TestClient(app)

    response = client.post(
        '/v1/admin/jobs',
        json={
            'job_type': 'generate_publish_queue_report',
            'input_payload': {'profile_id': 'tx_2026_ag_runoff'},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'queued'


def test_get_worker_health_requires_admin_auth() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_admin, None)

    client = TestClient(app)
    response = client.get('/v1/admin/jobs/worker-health')

    assert response.status_code == 401


def test_get_worker_health_success(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin
    now = datetime(2026, 5, 13, tzinfo=timezone.utc)
    failure_id = uuid.uuid4()

    def _fake_health(_db):  # type: ignore[no-untyped-def]
        return {
            'worker_alive': True,
            'queue_depth': 2,
            'due_depth': 1,
            'retry_queue_depth': 1,
            'oldest_queued_age_seconds': 45.0,
            'oldest_due_age_seconds': 45.0,
            'running_count': 0,
            'terminal_failure_count': 3,
            'recent_terminal_failures': [
                {
                    'id': failure_id,
                    'job_type': 'extract_claims_batch',
                    'attempt_count': 3,
                    'max_attempts': 3,
                    'last_error_code': 'job_execution_failed',
                    'finished_at': now,
                    'created_at': now,
                }
            ],
            'checked_at': now,
        }

    monkeypatch.setattr('app.api.v1.admin_jobs.AdminJobService.get_worker_health', _fake_health)

    client = TestClient(app)
    response = client.get('/v1/admin/jobs/worker-health')

    assert response.status_code == 200
    body = response.json()
    assert body['worker_alive'] is True
    assert body['queue_depth'] == 2
    assert body['due_depth'] == 1
    assert body['retry_queue_depth'] == 1
    assert body['oldest_queued_age_seconds'] == 45.0
    assert body['running_count'] == 0
    assert body['terminal_failure_count'] == 3
    assert len(body['recent_terminal_failures']) == 1
    failure = body['recent_terminal_failures'][0]
    assert failure['id'] == str(failure_id)
    assert failure['job_type'] == 'extract_claims_batch'
    assert failure['attempt_count'] == 3
    assert failure['last_error_code'] == 'job_execution_failed'
