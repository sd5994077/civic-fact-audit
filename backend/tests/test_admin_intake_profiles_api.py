from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
import pytest

from app.db.database import get_db
from app.main import app
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity


class _FakeApprovalIdentity:
    reviewer_id = 'approver@local'


class _FakeDb:
    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None


_FAKE_DB = _FakeDb()


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _override_admin() -> AuthIdentity:
    return AuthIdentity(reviewer_user_id=uuid.uuid4(), reviewer_id='admin@local', role='admin')


def _override_db():  # type: ignore[no-untyped-def]
    yield _FAKE_DB


def test_list_intake_profiles_requires_admin() -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(require_admin, None)

    client = TestClient(app)
    response = client.get('/v1/admin/intake-profiles')

    assert response.status_code == 401


def test_create_intake_profile_route(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin

    def _fake_identity_from_token(_db, _token, *, expected_action):  # type: ignore[no-untyped-def]
        assert expected_action == 'intake_profile_mutation'
        return _FakeApprovalIdentity()

    monkeypatch.setattr('app.api.v1.admin_intake_profiles.AuthService.identity_from_dual_control_approval_token', _fake_identity_from_token)
    monkeypatch.setattr(
        'app.api.v1.admin_intake_profiles.IntakeProfileService.create_profile',
        lambda *_args, **_kwargs: {
            'version': 'intake_profiles_v5_2026_05_14',
            'profiles': [
                {
                    'profile_id': 'tx_2026_governor',
                    'label': 'Texas 2026 Governor',
                    'state': 'TX',
                    'office': 'Governor',
                    'election_cycle': 2026,
                    'race_stage': 'general',
                    'statement_batches': ['starter'],
                    'roster_seed_module': 'app.scripts.ingest_tx_2026_governor_roster',
                    'statement_batch_modules': {'starter': 'app.scripts.ingest_tx_2026_governor_statement_batch'},
                    'admin_job_modules': {},
                }
            ],
        },
    )

    client = TestClient(app)
    response = client.post(
        '/v1/admin/intake-profiles',
        json={
            'approval_token': 'token',
            'profile_id': 'tx_2026_governor',
            'label': 'Texas 2026 Governor',
            'state': 'TX',
            'office': 'Governor',
            'election_cycle': 2026,
            'race_stage': 'general',
            'roster_seed_module': 'app.scripts.ingest_tx_2026_governor_roster',
            'statement_batch_modules': {'starter': 'app.scripts.ingest_tx_2026_governor_statement_batch'},
            'admin_job_modules': {},
        },
    )

    assert response.status_code == 200
    assert response.json()['profiles'][0]['profile_id'] == 'tx_2026_governor'


def test_update_intake_profile_route(monkeypatch) -> None:
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_admin] = _override_admin

    def _fake_identity_from_token(_db, _token, *, expected_action):  # type: ignore[no-untyped-def]
        assert expected_action == 'intake_profile_mutation'
        return _FakeApprovalIdentity()

    monkeypatch.setattr('app.api.v1.admin_intake_profiles.AuthService.identity_from_dual_control_approval_token', _fake_identity_from_token)
    monkeypatch.setattr(
        'app.api.v1.admin_intake_profiles.IntakeProfileService.update_profile',
        lambda *_args, **_kwargs: {
            'version': 'intake_profiles_v6_2026_05_14',
            'profiles': [
                {
                    'profile_id': 'tx_2026_governor',
                    'label': 'Texas 2026 Governor Updated',
                    'state': 'TX',
                    'office': 'Governor',
                    'election_cycle': 2026,
                    'race_stage': 'general',
                    'statement_batches': ['starter'],
                    'roster_seed_module': 'app.scripts.ingest_tx_2026_governor_roster',
                    'statement_batch_modules': {'starter': 'app.scripts.ingest_tx_2026_governor_statement_batch'},
                    'admin_job_modules': {},
                }
            ],
        },
    )

    client = TestClient(app)
    response = client.patch(
        '/v1/admin/intake-profiles/tx_2026_governor',
        json={
            'approval_token': 'token',
            'label': 'Texas 2026 Governor Updated',
        },
    )

    assert response.status_code == 200
    assert response.json()['profiles'][0]['label'] == 'Texas 2026 Governor Updated'
