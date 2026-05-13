from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.admin_job_allowlist import AdminJobAllowlist, AdminJobDefinition, get_admin_job_allowlist
from app.core.errors import AppError
from app.core.intake_profiles import IntakeProfile, get_intake_profiles_config
from app.models.entities import AdminJobRun
from app.models.enums import AdminJobStatus
from app.schemas.api import AdminJobRunCreateRequest
from app.services.admin_audit_service import AdminAuditService

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_INTAKE_ROSTER_JOB_TYPE = 'ingest_candidate_roster'
_INTAKE_STATEMENT_BATCH_JOB_TYPE = 'ingest_statement_batch'
_JOB_EXECUTION_TIMEOUT_SECONDS = 300


class AdminJobService:
    @staticmethod
    def _allowlisted_modules_for_job(job: AdminJobDefinition) -> list[str]:
        modules = [job.module, *job.allowed_modules]
        deduped: list[str] = []
        seen: set[str] = set()
        for module in modules:
            normalized = str(module).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    @staticmethod
    def _get_job_schema_fields(job: AdminJobDefinition) -> tuple[list[str], list[str]]:
        raw_schema = job.input_schema if isinstance(job.input_schema, dict) else {}
        required_fields = sorted({str(item).strip() for item in raw_schema.get('required_fields', []) if str(item).strip()})
        allowed_fields = sorted({str(item).strip() for item in raw_schema.get('allowed_fields', []) if str(item).strip()})
        return required_fields, allowed_fields

    @staticmethod
    def _job_uses_profile_id(job: AdminJobDefinition) -> bool:
        required_fields, allowed_fields = AdminJobService._get_job_schema_fields(job)
        return 'profile_id' in required_fields or 'profile_id' in allowed_fields

    @staticmethod
    def _profile_ids_supporting_job(job_type: str, *, intake_config: Any | None = None) -> list[str]:
        config = intake_config if intake_config is not None else get_intake_profiles_config()
        return sorted(
            profile_id
            for profile_id, profile in config.profiles_by_id.items()
            if profile.admin_job_modules.get(job_type)
        )

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _to_json_text(payload: dict[str, Any]) -> str:
        return json.dumps(payload, separators=(',', ':'), sort_keys=True)

    @staticmethod
    def _parse_json_text(payload: str | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        text = payload.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {'raw': text}
        if isinstance(parsed, dict):
            return parsed
        return {'value': parsed}

    @staticmethod
    def _get_allowlist() -> AdminJobAllowlist:
        return get_admin_job_allowlist()

    @staticmethod
    def _get_job_definition(job_type: str) -> tuple[AdminJobDefinition, str]:
        allowlist = AdminJobService._get_allowlist()
        job = allowlist.jobs_by_type.get(job_type)
        if job is None:
            raise AppError(
                'job_type_not_allowed',
                'Job type is not allowlisted for admin execution.',
                status_code=422,
                details={
                    'job_type': job_type,
                    'allowlist_version': allowlist.version,
                    'allowed_job_types': sorted(allowlist.jobs_by_type.keys()),
                },
            )
        return job, allowlist.version

    @staticmethod
    def _raise_job_input_invalid(
        message: str,
        *,
        required_fields: list[str],
        allowed_fields: list[str],
        missing_fields: list[str],
        unsupported_fields: list[str],
        allowed_values: dict[str, list[Any]],
    ) -> None:
        raise AppError(
            'job_input_invalid',
            message,
            status_code=422,
            details={
                'required_fields': required_fields,
                'allowed_fields': allowed_fields,
                'missing_fields': missing_fields,
                'unsupported_fields': unsupported_fields,
                'allowed_values': allowed_values,
            },
        )

    @staticmethod
    def _normalize_string_field(
        payload: dict[str, Any],
        field_name: str,
        *,
        required_fields: list[str],
        allowed_fields: list[str],
        allowed_values: dict[str, list[Any]],
    ) -> str:
        raw = payload.get(field_name)
        if not isinstance(raw, str):
            AdminJobService._raise_job_input_invalid(
                f'{field_name} must be a non-empty string.',
                required_fields=required_fields,
                allowed_fields=allowed_fields,
                missing_fields=[],
                unsupported_fields=[],
                allowed_values=allowed_values,
            )
        value = raw.strip()
        if not value:
            AdminJobService._raise_job_input_invalid(
                f'{field_name} must be a non-empty string.',
                required_fields=required_fields,
                allowed_fields=allowed_fields,
                missing_fields=[],
                unsupported_fields=[],
                allowed_values=allowed_values,
            )
        return value

    @staticmethod
    def _normalize_boolean_field(
        payload: dict[str, Any],
        field_name: str,
        *,
        default: bool,
        required_fields: list[str],
        allowed_fields: list[str],
        allowed_values: dict[str, list[Any]],
    ) -> bool:
        if field_name not in payload:
            return default
        raw = payload.get(field_name)
        if not isinstance(raw, bool):
            AdminJobService._raise_job_input_invalid(
                f'{field_name} must be a boolean when provided.',
                required_fields=required_fields,
                allowed_fields=allowed_fields,
                missing_fields=[],
                unsupported_fields=[],
                allowed_values=allowed_values,
            )
        return raw

    @staticmethod
    def _normalize_input_payload(payload: dict[str, Any], job: AdminJobDefinition) -> dict[str, Any]:
        raw_schema = job.input_schema if isinstance(job.input_schema, dict) else {}
        required_fields = sorted({str(item).strip() for item in raw_schema.get('required_fields', []) if str(item).strip()})
        allowed_fields = sorted({str(item).strip() for item in raw_schema.get('allowed_fields', []) if str(item).strip()})
        field_types_raw = raw_schema.get('field_types', {})
        field_types = dict(field_types_raw) if isinstance(field_types_raw, dict) else {}
        allowed_values_raw = raw_schema.get('allowed_values', {})
        allowed_values = dict(allowed_values_raw) if isinstance(allowed_values_raw, dict) else {}
        normalized_allowed_values: dict[str, list[Any]] = {}
        for key, values in allowed_values.items():
            if isinstance(values, list):
                normalized_allowed_values[str(key)] = values

        if job.supports_dry_run and 'dry_run' not in allowed_fields:
            allowed_fields.append('dry_run')
        if job.supports_dry_run and 'dry_run' not in field_types:
            field_types['dry_run'] = 'boolean'
        if not job.supports_dry_run and 'dry_run' in payload:
            AdminJobService._raise_job_input_invalid(
                'This job type does not support dry_run execution.',
                required_fields=required_fields,
                allowed_fields=allowed_fields,
                missing_fields=[],
                unsupported_fields=['dry_run'],
                allowed_values=normalized_allowed_values,
            )

        payload_by_normalized_key: dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            payload_by_normalized_key[normalized_key] = value

        payload_fields = set(payload_by_normalized_key.keys())
        missing_fields = sorted(field for field in required_fields if field not in payload_fields)
        unsupported_fields = sorted(field for field in payload_fields if field not in set(allowed_fields))
        if missing_fields or unsupported_fields:
            AdminJobService._raise_job_input_invalid(
                'Job input payload is missing required fields or includes unsupported fields.',
                required_fields=required_fields,
                allowed_fields=allowed_fields,
                missing_fields=missing_fields,
                unsupported_fields=unsupported_fields,
                allowed_values=normalized_allowed_values,
            )

        normalized: dict[str, Any] = {}
        for field_name in allowed_fields:
            if field_name not in payload_by_normalized_key and field_name != 'dry_run':
                continue
            expected_type = str(field_types.get(field_name, '')).strip().lower()
            if expected_type == 'string':
                normalized[field_name] = AdminJobService._normalize_string_field(
                    payload_by_normalized_key,
                    field_name,
                    required_fields=required_fields,
                    allowed_fields=allowed_fields,
                    allowed_values=normalized_allowed_values,
                )
            elif expected_type == 'boolean':
                normalized[field_name] = AdminJobService._normalize_boolean_field(
                    payload_by_normalized_key,
                    field_name,
                    default=False,
                    required_fields=required_fields,
                    allowed_fields=allowed_fields,
                    allowed_values=normalized_allowed_values,
                )
            elif field_name in payload_by_normalized_key:
                normalized[field_name] = payload_by_normalized_key[field_name]

        if job.supports_dry_run and 'dry_run' not in normalized:
            normalized['dry_run'] = False

        for field_name, values in normalized_allowed_values.items():
            if field_name not in normalized:
                continue
            if normalized[field_name] not in values:
                AdminJobService._raise_job_input_invalid(
                    f'{field_name} must be one of the allowed values.',
                    required_fields=required_fields,
                    allowed_fields=allowed_fields,
                    missing_fields=[],
                    unsupported_fields=[],
                    allowed_values=normalized_allowed_values,
                )

        return normalized

    @staticmethod
    def get_job_metadata() -> dict[str, Any]:
        allowlist = AdminJobService._get_allowlist()
        intake_config = get_intake_profiles_config()
        profile_ids = sorted(intake_config.profiles_by_id.keys())

        jobs: list[dict[str, Any]] = []
        for job in allowlist.jobs_by_type.values():
            raw_schema = job.input_schema if isinstance(job.input_schema, dict) else {}
            required_fields = sorted({str(item).strip() for item in raw_schema.get('required_fields', []) if str(item).strip()})
            allowed_fields = sorted({str(item).strip() for item in raw_schema.get('allowed_fields', []) if str(item).strip()})
            field_types_raw = raw_schema.get('field_types', {})
            field_types = dict(field_types_raw) if isinstance(field_types_raw, dict) else {}
            allowed_values_raw = raw_schema.get('allowed_values', {})
            allowed_values: dict[str, list[str]] = {}
            if isinstance(allowed_values_raw, dict):
                for field_name, values in allowed_values_raw.items():
                    if isinstance(values, list):
                        allowed_values[str(field_name)] = [str(value) for value in values]

            if job.supports_dry_run and 'dry_run' not in allowed_fields:
                allowed_fields.append('dry_run')
            if job.supports_dry_run and 'dry_run' not in field_types:
                field_types['dry_run'] = 'boolean'

            if job.job_type in {_INTAKE_ROSTER_JOB_TYPE, _INTAKE_STATEMENT_BATCH_JOB_TYPE}:
                allowed_values['profile_id'] = profile_ids
            elif AdminJobService._job_uses_profile_id(job):
                allowed_values['profile_id'] = AdminJobService._profile_ids_supporting_job(
                    job.job_type,
                    intake_config=intake_config,
                )

            jobs.append(
                {
                    'job_type': job.job_type,
                    'description': job.description,
                    'input_schema': {
                        'required_fields': required_fields,
                        'allowed_fields': allowed_fields,
                        'field_types': {str(key): str(value) for key, value in field_types.items()},
                        'allowed_values': allowed_values,
                        'supports_dry_run': job.supports_dry_run,
                    },
                }
            )

        intake_profiles: list[dict[str, Any]] = []
        for profile_id in profile_ids:
            profile = intake_config.profiles_by_id[profile_id]
            intake_profiles.append(
                {
                    'profile_id': profile.profile_id,
                    'label': profile.label,
                    'state': profile.state,
                    'office': profile.office,
                    'election_cycle': profile.election_cycle,
                    'race_stage': profile.race_stage,
                    'statement_batches': sorted(profile.statement_batch_modules.keys()),
                }
            )

        return {
            'allowlist_version': allowlist.version,
            'intake_profile_version': intake_config.version,
            'synchronous_execution': True,
            'jobs': jobs,
            'intake_profiles': intake_profiles,
        }

    @staticmethod
    def _get_intake_profile(profile_id: str) -> tuple[IntakeProfile, str]:
        config = get_intake_profiles_config()
        profile = config.profiles_by_id.get(profile_id)
        if profile is None:
            allowed_profile_ids = sorted(config.profiles_by_id.keys())
            AdminJobService._raise_job_input_invalid(
                'profile_id is not recognized.',
                required_fields=['profile_id'],
                allowed_fields=['profile_id'],
                missing_fields=[],
                unsupported_fields=[],
                allowed_values={'profile_id': allowed_profile_ids},
            )
        return profile, config.version

    @staticmethod
    def _resolve_job_module(job: AdminJobDefinition, normalized_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if job.job_type == _INTAKE_ROSTER_JOB_TYPE:
            profile_id = str(normalized_payload.get('profile_id', '')).strip()
            profile, config_version = AdminJobService._get_intake_profile(profile_id)
            return profile.roster_seed_module, {'intake_profile_version': config_version, 'intake_profile_id': profile.profile_id}

        if job.job_type == _INTAKE_STATEMENT_BATCH_JOB_TYPE:
            profile_id = str(normalized_payload.get('profile_id', '')).strip()
            profile, config_version = AdminJobService._get_intake_profile(profile_id)
            statement_batch = str(normalized_payload.get('statement_batch', '')).strip()
            module = profile.statement_batch_modules.get(statement_batch)
            if module is None:
                AdminJobService._raise_job_input_invalid(
                    'statement_batch is not supported for the selected profile.',
                    required_fields=['profile_id', 'statement_batch'],
                    allowed_fields=['profile_id', 'statement_batch'],
                    missing_fields=[],
                    unsupported_fields=[],
                    allowed_values={'statement_batch': sorted(profile.statement_batch_modules.keys())},
                )
            return module, {
                'intake_profile_version': config_version,
                'intake_profile_id': profile.profile_id,
                'statement_batch': statement_batch,
            }

        if AdminJobService._job_uses_profile_id(job):
            profile_id = str(normalized_payload.get('profile_id', '')).strip()
            profile, config_version = AdminJobService._get_intake_profile(profile_id)
            module = profile.admin_job_modules.get(job.job_type)
            if module is None:
                allowed_profile_ids = AdminJobService._profile_ids_supporting_job(job.job_type)
                AdminJobService._raise_job_input_invalid(
                    'profile_id is not supported for the selected job type.',
                    required_fields=['profile_id'],
                    allowed_fields=['profile_id'],
                    missing_fields=[],
                    unsupported_fields=[],
                    allowed_values={'profile_id': allowed_profile_ids},
                )
            return module, {'intake_profile_version': config_version, 'intake_profile_id': profile.profile_id}

        return job.module, {}

    @staticmethod
    def _assert_resolved_module_allowlisted(
        job: AdminJobDefinition,
        *,
        resolved_module: str,
        allowlist_version: str,
        module_metadata: dict[str, Any],
    ) -> list[str]:
        allowlisted_modules = AdminJobService._allowlisted_modules_for_job(job)
        if resolved_module not in allowlisted_modules:
            raise AppError(
                'job_module_not_allowlisted',
                'Resolved module is not allowlisted for admin execution.',
                status_code=409,
                details={
                    'job_type': job.job_type,
                    'resolved_module': resolved_module,
                    'allowlisted_modules': allowlisted_modules,
                    'allowlist_version': allowlist_version,
                    **module_metadata,
                },
            )
        return allowlisted_modules

    @staticmethod
    def _mark_running(db: Session, job_run: AdminJobRun) -> None:
        job_run.status = AdminJobStatus.running.value
        job_run.started_at = AdminJobService._utcnow()
        db.commit()
        db.refresh(job_run)

    @staticmethod
    def _mark_succeeded(db: Session, job_run: AdminJobRun, result_summary: dict[str, Any]) -> None:
        job_run.status = AdminJobStatus.succeeded.value
        job_run.finished_at = AdminJobService._utcnow()
        job_run.result_summary = AdminJobService._to_json_text(result_summary)
        job_run.error_details = None
        db.commit()
        db.refresh(job_run)

    @staticmethod
    def _mark_failed(db: Session, job_run: AdminJobRun, error_details: dict[str, Any]) -> None:
        job_run.status = AdminJobStatus.failed.value
        job_run.finished_at = AdminJobService._utcnow()
        job_run.error_details = AdminJobService._to_json_text(error_details)
        db.commit()
        db.refresh(job_run)

    @staticmethod
    def _run_job_command(module: str, *, dry_run: bool) -> dict[str, Any]:
        command = [sys.executable, '-m', module]
        if dry_run:
            command.append('--dry-run')

        started = time.time()
        try:
            completed = subprocess.run(
                command,
                cwd=str(_BACKEND_ROOT),
                capture_output=True,
                text=True,
                check=False,
                timeout=_JOB_EXECUTION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_seconds = round(time.time() - started, 3)
            stdout_tail = ''
            stderr_tail = ''
            if exc.stdout:
                stdout_tail = str(exc.stdout)[-4000:]
            if exc.stderr:
                stderr_tail = str(exc.stderr)[-4000:]
            raise AppError(
                'job_execution_failed',
                'Admin job execution timed out.',
                status_code=500,
                details={
                    'command': command,
                    'elapsed_seconds': elapsed_seconds,
                    'timeout_seconds': _JOB_EXECUTION_TIMEOUT_SECONDS,
                    'timed_out': True,
                    'stdout_tail': stdout_tail,
                    'stderr_tail': stderr_tail,
                },
            ) from exc
        elapsed_seconds = round(time.time() - started, 3)

        result = {
            'command': command,
            'return_code': completed.returncode,
            'elapsed_seconds': elapsed_seconds,
            'stdout_tail': completed.stdout[-4000:],
            'stderr_tail': completed.stderr[-4000:],
        }
        if completed.returncode != 0:
            raise AppError(
                'job_execution_failed',
                'Admin job execution failed.',
                status_code=500,
                details=result,
            )
        return result

    @staticmethod
    def _to_read_model(job_run: AdminJobRun) -> dict[str, Any]:
        return {
            'id': job_run.id,
            'job_type': job_run.job_type,
            'status': job_run.status,
            'requested_by_reviewer_id': job_run.requested_by_reviewer_id,
            'input_payload': AdminJobService._parse_json_text(job_run.input_payload) or {},
            'started_at': job_run.started_at,
            'finished_at': job_run.finished_at,
            'result_summary': AdminJobService._parse_json_text(job_run.result_summary),
            'error_details': AdminJobService._parse_json_text(job_run.error_details),
            'created_at': job_run.created_at,
            'updated_at': job_run.updated_at,
        }

    @staticmethod
    def create_and_run_job(db: Session, payload: AdminJobRunCreateRequest, *, requested_by_reviewer_id: str) -> dict[str, Any]:
        job, allowlist_version = AdminJobService._get_job_definition(payload.job_type)
        normalized_payload = AdminJobService._normalize_input_payload(payload.input_payload, job)
        resolved_module, module_metadata = AdminJobService._resolve_job_module(job, normalized_payload)
        allowlisted_modules = AdminJobService._assert_resolved_module_allowlisted(
            job,
            resolved_module=resolved_module,
            allowlist_version=allowlist_version,
            module_metadata=module_metadata,
        )
        job_run = AdminJobRun(
            job_type=job.job_type,
            status=AdminJobStatus.queued.value,
            requested_by_reviewer_id=requested_by_reviewer_id,
            input_payload=AdminJobService._to_json_text(normalized_payload),
        )
        db.add(job_run)
        db.flush()
        AdminAuditService.record_event(
            db,
            actor_reviewer_id=requested_by_reviewer_id,
            action='admin_job_triggered',
            entity_type='admin_job_run',
            entity_id=str(job_run.id),
            before_payload=None,
            after_payload={
                'job_run_id': str(job_run.id),
                'job_type': job_run.job_type,
                'status': job_run.status,
                'input_payload': normalized_payload,
            },
            metadata={
                'allowlist_version': allowlist_version,
                **module_metadata,
                'resolved_module': resolved_module,
                'allowlisted_modules': allowlisted_modules,
                'module_allowlist_enforced': True,
            },
            commit=False,
        )
        db.commit()
        db.refresh(job_run)

        try:
            AdminJobService._mark_running(db, job_run)
            result_summary = AdminJobService._run_job_command(resolved_module, dry_run=bool(normalized_payload.get('dry_run', False)))
            result_summary['allowlist_version'] = allowlist_version
            result_summary['resolved_module'] = resolved_module
            result_summary.update(module_metadata)
            AdminJobService._mark_succeeded(db, job_run, result_summary)
            return AdminJobService._to_read_model(job_run)
        except AppError as exc:
            AdminJobService._mark_failed(
                db,
                job_run,
                {
                    'code': exc.code,
                    'message': exc.message,
                    'details': exc.details,
                    'allowlist_version': allowlist_version,
                },
            )
            raise
        except Exception as exc:
            AdminJobService._mark_failed(
                db,
                job_run,
                {
                    'code': 'job_execution_failed',
                    'message': 'Admin job execution failed.',
                    'details': {'reason': exc.__class__.__name__},
                    'allowlist_version': allowlist_version,
                },
            )
            raise AppError('job_execution_failed', 'Admin job execution failed.', status_code=500) from exc

    @staticmethod
    def get_job_run(db: Session, job_run_id: uuid.UUID) -> dict[str, Any]:
        job_run = db.get(AdminJobRun, job_run_id)
        if job_run is None:
            raise AppError('admin_job_not_found', 'Admin job run does not exist.', status_code=404)
        return AdminJobService._to_read_model(job_run)

    @staticmethod
    def list_job_runs(
        db: Session,
        *,
        status: AdminJobStatus | None = None,
        job_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: Select[tuple[AdminJobRun]] = select(AdminJobRun).order_by(AdminJobRun.created_at.desc())
        if status is not None:
            query = query.where(AdminJobRun.status == status.value)
        if job_type is not None:
            query = query.where(AdminJobRun.job_type == job_type.strip())
        rows = db.execute(query.limit(limit)).scalars().all()
        return [AdminJobService._to_read_model(row) for row in rows]
