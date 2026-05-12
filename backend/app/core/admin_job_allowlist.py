from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AdminJobDefinition:
    job_type: str
    module: str
    supports_dry_run: bool
    input_schema: dict[str, Any]
    description: str | None = None


@dataclass(frozen=True)
class AdminJobAllowlist:
    version: str
    jobs_by_type: dict[str, AdminJobDefinition]


DEFAULT_ALLOWLIST_PATH = Path(__file__).resolve().parent.parent / 'config' / 'admin_jobs_allowlist_v1.json'


@lru_cache(maxsize=1)
def get_admin_job_allowlist(path: str | None = None) -> AdminJobAllowlist:
    allowlist_path = Path(path) if path is not None else DEFAULT_ALLOWLIST_PATH
    payload = json.loads(allowlist_path.read_text(encoding='utf-8'))

    version = str(payload.get('version', 'admin_jobs_allowlist_unversioned')).strip() or 'admin_jobs_allowlist_unversioned'
    raw_job_types = payload.get('job_types', [])
    if not isinstance(raw_job_types, list):
        raise ValueError('admin job allowlist job_types must be a list')

    jobs_by_type: dict[str, AdminJobDefinition] = {}
    for raw_job in raw_job_types:
        if not isinstance(raw_job, dict):
            continue
        job_type = str(raw_job.get('job_type', '')).strip()
        module = str(raw_job.get('module', '')).strip()
        if not job_type or not module:
            continue
        jobs_by_type[job_type] = AdminJobDefinition(
            job_type=job_type,
            module=module,
            supports_dry_run=bool(raw_job.get('supports_dry_run', False)),
            input_schema=raw_job.get('input_schema', {}) if isinstance(raw_job.get('input_schema', {}), dict) else {},
            description=str(raw_job.get('description')).strip() if raw_job.get('description') is not None else None,
        )

    return AdminJobAllowlist(version=version, jobs_by_type=jobs_by_type)
