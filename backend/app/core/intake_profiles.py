from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class IntakeProfile:
    profile_id: str
    label: str
    state: str
    office: str
    election_cycle: int
    race_stage: str
    roster_seed_module: str
    statement_batch_modules: dict[str, str]


@dataclass(frozen=True)
class IntakeProfilesConfig:
    version: str
    profiles_by_id: dict[str, IntakeProfile]


DEFAULT_INTAKE_PROFILES_PATH = Path(__file__).resolve().parent.parent / 'config' / 'intake_profiles_v1.json'


@lru_cache(maxsize=1)
def get_intake_profiles_config(path: str | None = None) -> IntakeProfilesConfig:
    config_path = Path(path) if path is not None else DEFAULT_INTAKE_PROFILES_PATH
    payload = json.loads(config_path.read_text(encoding='utf-8'))

    version = str(payload.get('version', 'intake_profiles_unversioned')).strip() or 'intake_profiles_unversioned'
    raw_profiles = payload.get('profiles', [])
    if not isinstance(raw_profiles, list):
        raise ValueError('intake profile config profiles must be a list')

    profiles_by_id: dict[str, IntakeProfile] = {}
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            continue
        profile_id = str(raw_profile.get('profile_id', '')).strip()
        label = str(raw_profile.get('label', '')).strip()
        state = str(raw_profile.get('state', '')).strip()
        office = str(raw_profile.get('office', '')).strip()
        race_stage = str(raw_profile.get('race_stage', '')).strip()
        roster_seed_module = str(raw_profile.get('roster_seed_module', '')).strip()
        election_cycle_raw = raw_profile.get('election_cycle')
        batch_modules_raw = raw_profile.get('statement_batch_modules', {})

        if (
            not profile_id
            or not label
            or not state
            or not office
            or not race_stage
            or not roster_seed_module
            or not isinstance(election_cycle_raw, int)
            or not isinstance(batch_modules_raw, dict)
        ):
            continue

        statement_batch_modules: dict[str, str] = {}
        for batch_key, module in batch_modules_raw.items():
            normalized_batch_key = str(batch_key).strip()
            normalized_module = str(module).strip()
            if not normalized_batch_key or not normalized_module:
                continue
            statement_batch_modules[normalized_batch_key] = normalized_module
        if not statement_batch_modules:
            continue

        profiles_by_id[profile_id] = IntakeProfile(
            profile_id=profile_id,
            label=label,
            state=state,
            office=office,
            election_cycle=election_cycle_raw,
            race_stage=race_stage,
            roster_seed_module=roster_seed_module,
            statement_batch_modules=statement_batch_modules,
        )

    return IntakeProfilesConfig(version=version, profiles_by_id=profiles_by_id)
