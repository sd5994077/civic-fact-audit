from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.core.errors import AppError

MatchMode = Literal['contains']


@dataclass(frozen=True)
class ModerationRule:
    rule_id: str
    violation_type: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ModerationPolicy:
    version: str
    mode: MatchMode
    rules: tuple[ModerationRule, ...]


@dataclass(frozen=True)
class ModerationViolation:
    rule_id: str
    violation_type: str
    matched_pattern: str
    policy_version: str

    def to_details(self, *, rejection_field: str) -> dict[str, str]:
        return {
            'rejection_field': rejection_field,
            'matched_rule': f'{self.rule_id}:{self.matched_pattern}',
            'policy_version': self.policy_version,
            'violation_type': self.violation_type,
        }


DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / 'config' / 'moderation_policy_v1.json'


@lru_cache(maxsize=1)
def get_moderation_policy(path: str | None = None) -> ModerationPolicy:
    policy_path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    payload = json.loads(policy_path.read_text(encoding='utf-8'))
    version = str(payload.get('version', 'moderation_policy_unversioned')).strip() or 'moderation_policy_unversioned'
    mode = str(payload.get('matching', {}).get('mode', 'contains')).strip().lower()
    if mode != 'contains':
        raise ValueError(f'Unsupported moderation matching mode: {mode}')

    rules_payload = payload.get('rules', [])
    if not isinstance(rules_payload, list):
        raise ValueError('Moderation policy rules must be a list')

    rules: list[ModerationRule] = []
    for raw_rule in rules_payload:
        if not isinstance(raw_rule, dict):
            continue
        rule_id = str(raw_rule.get('rule_id', '')).strip()
        violation_type = str(raw_rule.get('violation_type', '')).strip()
        patterns = raw_rule.get('patterns', [])
        if not rule_id or not violation_type or not isinstance(patterns, list):
            continue
        normalized_patterns = tuple(str(pattern).strip().lower() for pattern in patterns if str(pattern).strip())
        if not normalized_patterns:
            continue
        rules.append(ModerationRule(rule_id=rule_id, violation_type=violation_type, patterns=normalized_patterns))

    return ModerationPolicy(version=version, mode='contains', rules=tuple(rules))


def find_moderation_violation(text: str) -> ModerationViolation | None:
    normalized = text.strip().lower()
    if not normalized:
        return None
    policy = get_moderation_policy()
    for rule in policy.rules:
        for pattern in rule.patterns:
            if pattern in normalized:
                return ModerationViolation(
                    rule_id=rule.rule_id,
                    violation_type=rule.violation_type,
                    matched_pattern=pattern,
                    policy_version=policy.version,
                )
    return None


def enforce_boundary_safe_text(*, text: str, rejection_field: str) -> None:
    violation = find_moderation_violation(text)
    if violation is None:
        return
    raise AppError(
        'moderation_policy_violation',
        'Text violates moderation policy boundaries.',
        status_code=422,
        details=violation.to_details(rejection_field=rejection_field),
    )
