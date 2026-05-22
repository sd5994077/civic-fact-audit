from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.intake_profiles import DEFAULT_INTAKE_PROFILES_PATH, IntakeProfilesConfig, get_intake_profiles_config
from app.models.enums import RaceStage
from app.schemas.api import AdminIntakeProfileCreateRequest, AdminIntakeProfileUpdateRequest
from app.services.admin_audit_service import AdminAuditService
from app.services.auth_service import AuthService


class IntakeProfileService:
    _VERSION_PATTERN = re.compile(r'^intake_profiles_v(?P<number>\d+)_\d{4}_\d{2}_\d{2}$')

    @staticmethod
    def _enforce_dual_control(
        db: Session,
        *,
        approval_reviewer_id: str | None,
        applying_reviewer_id: str | None,
        action: str,
    ) -> tuple[str, str]:
        normalized_approval_reviewer_id = AuthService.resolve_active_reviewer_id(
            db,
            approval_reviewer_id,
            allowed_roles={'reviewer', 'admin'},
        )
        normalized_applying_reviewer_id = AuthService.resolve_active_reviewer_id(
            db,
            applying_reviewer_id,
            allowed_roles={'reviewer', 'admin'},
        )
        if (
            normalized_approval_reviewer_id is None
            or normalized_applying_reviewer_id is None
            or normalized_approval_reviewer_id == normalized_applying_reviewer_id
        ):
            raise AppError(
                'intake_profile_dual_control_required',
                'Intake profile mutations require different reviewers for approval and final mutation.',
                status_code=409,
                details={
                    'approval_reviewer_id': normalized_approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'action': action,
                },
            )
        return normalized_approval_reviewer_id, normalized_applying_reviewer_id

    @staticmethod
    def _config_path() -> Path:
        return DEFAULT_INTAKE_PROFILES_PATH

    @staticmethod
    def _read_raw_config() -> dict[str, Any]:
        payload = json.loads(IntakeProfileService._config_path().read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise AppError(
                'intake_profile_config_invalid',
                'Intake profile config must be a JSON object.',
                status_code=500,
            )
        return payload

    @staticmethod
    def _write_raw_config(payload: dict[str, Any]) -> None:
        path = IntakeProfileService._config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + '.tmp')
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        tmp_path.replace(path)
        get_intake_profiles_config.cache_clear()

    @staticmethod
    def _load_config() -> IntakeProfilesConfig:
        return get_intake_profiles_config(str(IntakeProfileService._config_path()))

    @staticmethod
    def _normalize_non_empty_text(value: object, field_name: str, *, max_length: int | None = None) -> str:
        text = str(value).strip()
        if not text:
            raise AppError('intake_profile_invalid', f'{field_name} is required.', status_code=422)
        if max_length is not None and len(text) > max_length:
            raise AppError(
                'intake_profile_invalid',
                f'{field_name} must be at most {max_length} characters.',
                status_code=422,
            )
        return text

    @staticmethod
    def _normalize_required_update_text(value: object | None, field_name: str, *, max_length: int | None = None) -> str:
        if value is None:
            raise AppError('intake_profile_invalid', f'{field_name} cannot be null.', status_code=422)
        return IntakeProfileService._normalize_non_empty_text(value, field_name, max_length=max_length)

    @staticmethod
    def _normalize_module_map(raw: dict[str, Any] | None, field_name: str) -> dict[str, str]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise AppError(
                'intake_profile_invalid',
                f'{field_name} must be a JSON object.',
                status_code=422,
            )
        normalized: dict[str, str] = {}
        for key, value in raw.items():
            normalized_key = str(key).strip()
            if not isinstance(value, str):
                raise AppError(
                    'intake_profile_invalid',
                    f'{field_name} values must be strings.',
                    status_code=422,
                )
            normalized_value = value.strip()
            if not normalized_key or not normalized_value:
                continue
            normalized[normalized_key] = normalized_value
        return normalized

    @staticmethod
    def _normalize_race_stage(value: object) -> RaceStage:
        try:
            return RaceStage(str(value).strip())
        except ValueError as exc:
            raise AppError(
                'intake_profile_invalid',
                'race_stage must be one of primary, primary_runoff, general, or special.',
                status_code=422,
            ) from exc

    @staticmethod
    def _bump_version(current_version: str | None) -> str:
        today = datetime.now(timezone.utc).strftime('%Y_%m_%d')
        number = 0
        if current_version:
            match = IntakeProfileService._VERSION_PATTERN.match(current_version)
            if match is not None:
                number = int(match.group('number'))
        return f'intake_profiles_v{number + 1}_{today}'

    @staticmethod
    def _profile_payload_from_create(payload: AdminIntakeProfileCreateRequest) -> dict[str, Any]:
        return {
            'profile_id': IntakeProfileService._normalize_non_empty_text(payload.profile_id, 'profile_id', max_length=128),
            'label': IntakeProfileService._normalize_non_empty_text(payload.label, 'label', max_length=255),
            'state': IntakeProfileService._normalize_non_empty_text(payload.state, 'state', max_length=32),
            'office': IntakeProfileService._normalize_non_empty_text(payload.office, 'office', max_length=255),
            'election_cycle': int(payload.election_cycle),
            'race_stage': IntakeProfileService._normalize_race_stage(payload.race_stage).value,
            'roster_seed_module': IntakeProfileService._normalize_non_empty_text(
                payload.roster_seed_module,
                'roster_seed_module',
                max_length=255,
            ),
            'statement_batch_modules': IntakeProfileService._normalize_module_map(
                payload.statement_batch_modules,
                'statement_batch_modules',
            ),
            'admin_job_modules': IntakeProfileService._normalize_module_map(
                payload.admin_job_modules,
                'admin_job_modules',
            ),
        }

    @staticmethod
    def _profile_payload_from_update(
        existing: dict[str, Any],
        payload: AdminIntakeProfileUpdateRequest,
    ) -> dict[str, Any]:
        updated = dict(existing)
        if 'label' in payload.model_fields_set:
            updated['label'] = IntakeProfileService._normalize_required_update_text(payload.label, 'label', max_length=255)
        if 'state' in payload.model_fields_set:
            updated['state'] = IntakeProfileService._normalize_required_update_text(payload.state, 'state', max_length=32)
        if 'office' in payload.model_fields_set:
            updated['office'] = IntakeProfileService._normalize_required_update_text(payload.office, 'office', max_length=255)
        if 'election_cycle' in payload.model_fields_set:
            if payload.election_cycle is None:
                raise AppError('intake_profile_invalid', 'election_cycle cannot be null.', status_code=422)
            updated['election_cycle'] = int(payload.election_cycle)
        if 'race_stage' in payload.model_fields_set:
            if payload.race_stage is None:
                raise AppError('intake_profile_invalid', 'race_stage cannot be null.', status_code=422)
            updated['race_stage'] = IntakeProfileService._normalize_race_stage(payload.race_stage).value
        if 'roster_seed_module' in payload.model_fields_set:
            updated['roster_seed_module'] = IntakeProfileService._normalize_required_update_text(
                payload.roster_seed_module,
                'roster_seed_module',
                max_length=255,
            )
        if 'statement_batch_modules' in payload.model_fields_set:
            updated['statement_batch_modules'] = IntakeProfileService._normalize_module_map(
                payload.statement_batch_modules,
                'statement_batch_modules',
            )
        if 'admin_job_modules' in payload.model_fields_set:
            updated['admin_job_modules'] = IntakeProfileService._normalize_module_map(
                payload.admin_job_modules,
                'admin_job_modules',
            )
        return updated

    @staticmethod
    def _ensure_required_profile_fields(payload: dict[str, Any]) -> None:
        if not payload.get('statement_batch_modules'):
            raise AppError(
                'intake_profile_invalid',
                'statement_batch_modules must include at least one batch entry.',
                status_code=422,
            )

    @staticmethod
    def _build_response_payload(config: IntakeProfilesConfig) -> dict[str, Any]:
        profiles: list[dict[str, Any]] = []
        for profile_id in sorted(config.profiles_by_id.keys()):
            profile = config.profiles_by_id[profile_id]
            profiles.append(
                {
                    'profile_id': profile.profile_id,
                    'label': profile.label,
                    'state': profile.state,
                    'office': profile.office,
                    'election_cycle': profile.election_cycle,
                    'race_stage': profile.race_stage,
                    'statement_batches': sorted(profile.statement_batch_modules.keys()),
                    'roster_seed_module': profile.roster_seed_module,
                    'statement_batch_modules': dict(profile.statement_batch_modules),
                    'admin_job_modules': dict(profile.admin_job_modules),
                }
            )
        return {'version': config.version, 'profiles': profiles}

    @staticmethod
    def list_profiles() -> dict[str, Any]:
        config = IntakeProfileService._load_config()
        return IntakeProfileService._build_response_payload(config)

    @staticmethod
    def create_profile(
        db: Session,
        payload: AdminIntakeProfileCreateRequest,
        *,
        actor_reviewer_id: str | None = None,
        approval_reviewer_id: str | None = None,
    ) -> dict[str, Any]:
        existing_config = IntakeProfileService._read_raw_config()
        raw_profiles = existing_config.get('profiles', [])
        if not isinstance(raw_profiles, list):
            raise AppError(
                'intake_profile_config_invalid',
                'Intake profile config profiles must be a list.',
                status_code=500,
            )

        normalized_profile = IntakeProfileService._profile_payload_from_create(payload)
        IntakeProfileService._ensure_required_profile_fields(normalized_profile)
        profile_id = normalized_profile['profile_id']

        for existing_profile in raw_profiles:
            if isinstance(existing_profile, dict) and str(existing_profile.get('profile_id', '')).strip() == profile_id:
                raise AppError(
                    'intake_profile_conflict',
                    'Intake profile already exists.',
                    status_code=409,
                    details={'profile_id': profile_id},
                )

        normalized_approval_reviewer_id: str | None = None
        normalized_applying_reviewer_id: str | None = None
        if actor_reviewer_id is not None:
            normalized_approval_reviewer_id, normalized_applying_reviewer_id = IntakeProfileService._enforce_dual_control(
                db,
                approval_reviewer_id=approval_reviewer_id,
                applying_reviewer_id=actor_reviewer_id,
                action='intake_profile_create',
            )

        raw_profiles.append(normalized_profile)
        next_version = IntakeProfileService._bump_version(str(existing_config.get('version', '')))
        updated_config = {'version': next_version, 'profiles': raw_profiles}
        IntakeProfileService._write_raw_config(updated_config)

        if actor_reviewer_id is not None:
            try:
                db.flush()
                AdminAuditService.record_event(
                    db,
                    actor_reviewer_id=normalized_applying_reviewer_id,
                    action='intake_profile_created',
                    entity_type='intake_profile',
                    entity_id=profile_id,
                    before_payload=None,
                    after_payload=normalized_profile,
                    metadata={
                        'source': 'admin_api',
                        'approval_reviewer_id': normalized_approval_reviewer_id,
                        'applying_reviewer_id': normalized_applying_reviewer_id,
                        'config_version': next_version,
                        'dual_control_enforced': True,
                    },
                    commit=False,
                )
                db.commit()
            except Exception:
                db.rollback()
                IntakeProfileService._write_raw_config(existing_config)
                raise

        return IntakeProfileService.list_profiles()

    @staticmethod
    def update_profile(
        db: Session,
        profile_id: str,
        payload: AdminIntakeProfileUpdateRequest,
        *,
        actor_reviewer_id: str | None = None,
        approval_reviewer_id: str | None = None,
    ) -> dict[str, Any]:
        existing_config = IntakeProfileService._read_raw_config()
        raw_profiles = existing_config.get('profiles', [])
        if not isinstance(raw_profiles, list):
            raise AppError(
                'intake_profile_config_invalid',
                'Intake profile config profiles must be a list.',
                status_code=500,
            )

        target_index = None
        existing_profile = None
        normalized_profile_id = IntakeProfileService._normalize_non_empty_text(profile_id, 'profile_id', max_length=128)
        for index, row in enumerate(raw_profiles):
            if isinstance(row, dict) and str(row.get('profile_id', '')).strip() == normalized_profile_id:
                target_index = index
                existing_profile = row
                break
        if target_index is None or existing_profile is None:
            raise AppError(
                'intake_profile_not_found',
                'Intake profile does not exist.',
                status_code=404,
                details={'profile_id': normalized_profile_id},
            )

        mutable_fields = set(payload.model_fields_set).difference({'approval_token'})
        if not mutable_fields:
            raise AppError(
                'intake_profile_update_empty',
                'Intake profile update requires at least one field.',
                status_code=422,
            )

        updated_profile = IntakeProfileService._profile_payload_from_update(existing_profile, payload)
        IntakeProfileService._ensure_required_profile_fields(updated_profile)

        if updated_profile == existing_profile:
            return IntakeProfileService.list_profiles()

        normalized_approval_reviewer_id: str | None = None
        normalized_applying_reviewer_id: str | None = None
        if actor_reviewer_id is not None:
            normalized_approval_reviewer_id, normalized_applying_reviewer_id = IntakeProfileService._enforce_dual_control(
                db,
                approval_reviewer_id=approval_reviewer_id,
                applying_reviewer_id=actor_reviewer_id,
                action='intake_profile_update',
            )

        raw_profiles[target_index] = updated_profile
        next_version = IntakeProfileService._bump_version(str(existing_config.get('version', '')))
        updated_config = {'version': next_version, 'profiles': raw_profiles}
        IntakeProfileService._write_raw_config(updated_config)

        if actor_reviewer_id is not None:
            try:
                db.flush()
                AdminAuditService.record_event(
                    db,
                    actor_reviewer_id=normalized_applying_reviewer_id,
                    action='intake_profile_updated',
                    entity_type='intake_profile',
                    entity_id=normalized_profile_id,
                    before_payload=existing_profile,
                    after_payload=updated_profile,
                    metadata={
                        'source': 'admin_api',
                        'approval_reviewer_id': normalized_approval_reviewer_id,
                        'applying_reviewer_id': normalized_applying_reviewer_id,
                        'config_version': next_version,
                        'dual_control_enforced': True,
                    },
                    commit=False,
                )
                db.commit()
            except Exception:
                db.rollback()
                IntakeProfileService._write_raw_config(existing_config)
                raise

        return IntakeProfileService.list_profiles()
