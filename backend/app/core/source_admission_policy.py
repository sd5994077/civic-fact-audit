from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

MatchBehavior = Literal['contains', 'equals', 'suffix']


@dataclass(frozen=True)
class SourceAdmissionPolicy:
    version: str
    publisher_match: MatchBehavior
    domain_match: MatchBehavior
    partisan_publishers: tuple[str, ...]
    partisan_domains: tuple[str, ...]
    social_domains: tuple[str, ...]


DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / 'config' / 'source_admission_policy_v1.json'


@dataclass(frozen=True)
class SourcePolicyRuleMatch:
    field: Literal['publisher', 'domain']
    match_type: MatchBehavior
    pattern: str
    value: str


@lru_cache(maxsize=1)
def get_source_admission_policy(path: str | None = None) -> SourceAdmissionPolicy:
    policy_path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    payload = json.loads(policy_path.read_text(encoding='utf-8'))

    matching = payload.get('matching', {})
    publisher_match = str(matching.get('publisher', 'contains')).strip().lower()
    domain_match = str(matching.get('domain', 'suffix')).strip().lower()
    if publisher_match not in {'contains', 'equals', 'suffix'}:
        raise ValueError(f'Unsupported publisher matching behavior: {publisher_match}')
    if domain_match not in {'contains', 'equals', 'suffix'}:
        raise ValueError(f'Unsupported domain matching behavior: {domain_match}')

    def _normalize_list(key: str) -> tuple[str, ...]:
        values = payload.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f'Policy key {key} must be a list')
        return tuple(str(item).strip().lower() for item in values if str(item).strip())

    return SourceAdmissionPolicy(
        version=str(payload.get('version', 'source_admission_unversioned')).strip() or 'source_admission_unversioned',
        publisher_match=publisher_match,
        domain_match=domain_match,
        partisan_publishers=_normalize_list('partisan_publishers'),
        partisan_domains=_normalize_list('partisan_domains'),
        social_domains=_normalize_list('social_domains'),
    )


def _matches(value: str, pattern: str, behavior: MatchBehavior) -> bool:
    if behavior == 'equals':
        return value == pattern
    if behavior == 'contains':
        return pattern in value
    if behavior == 'suffix':
        return value == pattern or value.endswith(f'.{pattern}')
    return False


def _normalized_hostname(url: str) -> str:
    parsed = urlparse(url.strip())
    hostname = parsed.hostname
    if hostname is None and parsed.netloc:
        hostname = urlparse(f'//{parsed.netloc}').hostname
    if hostname is None and parsed.path and '://' not in url:
        hostname = urlparse(f'//{url.strip()}').hostname
    return (hostname or '').strip().lower().rstrip('.')


def find_partisan_rule_match(*, publisher: str | None, url: str) -> SourcePolicyRuleMatch | None:
    policy = get_source_admission_policy()
    lowered_publisher = (publisher or '').strip().lower()
    host = _normalized_hostname(url)

    if lowered_publisher:
        for pattern in policy.partisan_publishers:
            if _matches(lowered_publisher, pattern, policy.publisher_match):
                return SourcePolicyRuleMatch(
                    field='publisher',
                    match_type=policy.publisher_match,
                    pattern=pattern,
                    value=lowered_publisher,
                )

    if host:
        for pattern in policy.partisan_domains:
            if _matches(host, pattern, policy.domain_match):
                return SourcePolicyRuleMatch(
                    field='domain',
                    match_type=policy.domain_match,
                    pattern=pattern,
                    value=host,
                )

    return None


def is_social_url(url: str) -> bool:
    policy = get_source_admission_policy()
    host = _normalized_hostname(url)
    return any(_matches(host, pattern, 'suffix') for pattern in policy.social_domains)
