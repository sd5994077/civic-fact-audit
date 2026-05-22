from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.core.intake_profiles import get_intake_profiles_config
from app.schemas.api import AdminIntakeProfileCreateRequest, AdminIntakeProfileUpdateRequest
from app.services.intake_profile_service import IntakeProfileService


class _FakeDb:
    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _clear_intake_profile_cache() -> None:
    get_intake_profiles_config.cache_clear()
    yield
    get_intake_profiles_config.cache_clear()


def _write_base_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                'version': 'intake_profiles_v4_2026_05_13',
                'profiles': [],
            },
            indent=2,
        )
        + '\n',
        encoding='utf-8',
    )


def test_create_and_update_intake_profile_round_trip(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _write_base_config(config_path)

    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))
    monkeypatch.setattr(
        'app.services.intake_profile_service.IntakeProfileService._enforce_dual_control',
        lambda _db, **_kwargs: ('approver@local', 'actor@local'),
    )
    monkeypatch.setattr('app.services.intake_profile_service.AdminAuditService.record_event', lambda *args, **kwargs: None)

    db = _FakeDb()
    create_payload = AdminIntakeProfileCreateRequest(
        approval_token='token',
        profile_id='tx_2026_governor',
        label='Texas 2026 Governor',
        state='TX',
        office='Governor',
        election_cycle=2026,
        race_stage='general',
        roster_seed_module='app.scripts.ingest_tx_2026_governor_roster',
        statement_batch_modules={'starter': 'app.scripts.ingest_tx_2026_governor_statement_batch'},
        admin_job_modules={},
    )

    created = IntakeProfileService.create_profile(
        db,
        create_payload,
        actor_reviewer_id='actor@local',
        approval_reviewer_id='approver@local',
    )
    assert created['version'].startswith('intake_profiles_v5_')
    profile = created['profiles'][0]
    assert profile['profile_id'] == 'tx_2026_governor'
    assert profile['statement_batches'] == ['starter']
    assert profile['statement_batch_modules']['starter'] == 'app.scripts.ingest_tx_2026_governor_statement_batch'

    update_payload = AdminIntakeProfileUpdateRequest(
        approval_token='token',
        label='Texas 2026 Governor Updated',
        admin_job_modules={'extract_claims_batch': 'app.scripts.extract_tx_2026_governor_claims_batch'},
    )
    updated = IntakeProfileService.update_profile(
        db,
        'tx_2026_governor',
        update_payload,
        actor_reviewer_id='actor@local',
        approval_reviewer_id='approver@local',
    )
    assert updated['version'].startswith('intake_profiles_v6_')
    updated_profile = updated['profiles'][0]
    assert updated_profile['label'] == 'Texas 2026 Governor Updated'
    assert updated_profile['admin_job_modules']['extract_claims_batch'] == 'app.scripts.extract_tx_2026_governor_claims_batch'

    raw = json.loads(config_path.read_text(encoding='utf-8'))
    assert raw['version'].startswith('intake_profiles_v6_')
    assert raw['profiles'][0]['profile_id'] == 'tx_2026_governor'
    assert raw['profiles'][0]['admin_job_modules']['extract_claims_batch'] == 'app.scripts.extract_tx_2026_governor_claims_batch'


def _make_base_profile_config(config_path: Path) -> None:
    config_path.write_text(
        json.dumps(
            {
                'version': 'intake_profiles_v4_2026_05_13',
                'profiles': [
                    {
                        'profile_id': 'tx_2026_governor',
                        'label': 'Texas 2026 Governor',
                        'state': 'TX',
                        'office': 'Governor',
                        'election_cycle': 2026,
                        'race_stage': 'general',
                        'roster_seed_module': 'app.scripts.ingest_tx_2026_governor_roster',
                        'statement_batch_modules': {'starter': 'app.scripts.ingest_tx_2026_governor_statement_batch'},
                        'admin_job_modules': {},
                    }
                ],
            },
            indent=2,
        )
        + '\n',
        encoding='utf-8',
    )


def test_create_duplicate_profile_id_raises_conflict(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _make_base_profile_config(config_path)
    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))

    duplicate_payload = AdminIntakeProfileCreateRequest(
        approval_token='token',
        profile_id='tx_2026_governor',
        label='Duplicate',
        state='TX',
        office='Governor',
        election_cycle=2026,
        race_stage='general',
        roster_seed_module='app.scripts.ingest_tx_2026_governor_roster',
        statement_batch_modules={'starter': 'app.scripts.ingest_tx_2026_governor_statement_batch'},
        admin_job_modules={},
    )
    db = _FakeDb()
    with pytest.raises(AppError) as exc_info:
        IntakeProfileService.create_profile(db, duplicate_payload)
    assert exc_info.value.code == 'intake_profile_conflict'


def test_create_empty_statement_batch_modules_raises(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _write_base_config(config_path)
    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))

    payload = AdminIntakeProfileCreateRequest(
        approval_token='token',
        profile_id='tx_2026_ag',
        label='Texas 2026 AG',
        state='TX',
        office='Attorney General',
        election_cycle=2026,
        race_stage='primary',
        roster_seed_module='app.scripts.ingest_tx_2026_ag_roster',
        statement_batch_modules={},
        admin_job_modules={},
    )
    db = _FakeDb()
    with pytest.raises(AppError) as exc_info:
        IntakeProfileService.create_profile(db, payload)
    assert exc_info.value.code == 'intake_profile_invalid'


def test_update_profile_not_found_raises(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _write_base_config(config_path)
    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))

    payload = AdminIntakeProfileUpdateRequest(label='Does Not Matter')
    db = _FakeDb()
    with pytest.raises(AppError) as exc_info:
        IntakeProfileService.update_profile(db, 'nonexistent_profile', payload)
    assert exc_info.value.code == 'intake_profile_not_found'


def test_update_profile_no_mutable_fields_raises(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _make_base_profile_config(config_path)
    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))

    payload = AdminIntakeProfileUpdateRequest(approval_token='token')
    db = _FakeDb()
    with pytest.raises(AppError) as exc_info:
        IntakeProfileService.update_profile(db, 'tx_2026_governor', payload)
    assert exc_info.value.code == 'intake_profile_update_empty'


def test_update_noop_returns_existing_list(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _make_base_profile_config(config_path)
    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))

    original_version = json.loads(config_path.read_text(encoding='utf-8'))['version']
    payload = AdminIntakeProfileUpdateRequest(label='Texas 2026 Governor')
    db = _FakeDb()
    result = IntakeProfileService.update_profile(db, 'tx_2026_governor', payload)

    assert result['profiles'][0]['label'] == 'Texas 2026 Governor'
    assert json.loads(config_path.read_text(encoding='utf-8'))['version'] == original_version


def test_invalid_race_stage_raises(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _write_base_config(config_path)
    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))

    with pytest.raises(Exception):
        AdminIntakeProfileCreateRequest(
            approval_token='token',
            profile_id='tx_2026_bad',
            label='Bad Stage',
            state='TX',
            office='Governor',
            election_cycle=2026,
            race_stage='not_a_valid_stage',
            roster_seed_module='app.scripts.ingest_tx_2026_governor_roster',
            statement_batch_modules={'starter': 'app.scripts.ingest_tx_2026_governor_statement_batch'},
            admin_job_modules={},
        )


def test_list_profiles_reads_from_overridden_config_path(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / 'intake_profiles_v1.json'
    _make_base_profile_config(config_path)
    monkeypatch.setattr(IntakeProfileService, '_config_path', staticmethod(lambda: config_path))

    profiles = IntakeProfileService.list_profiles()
    assert profiles['profiles'][0]['profile_id'] == 'tx_2026_governor'
