import json
import tempfile
from pathlib import Path

from app.core.source_admission_policy import get_source_admission_policy, is_review_draft_fetch_allowed


def _write_temp_policy(payload: dict) -> Path:
    with tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        suffix='.json',
        dir=Path(__file__).resolve().parent,
        delete=False,
    ) as handle:
        handle.write(json.dumps(payload))
        return Path(handle.name)


def test_policy_parser_loads_review_draft_fetch_allowlist() -> None:
    payload = {
        'version': 'source_admission_test_v1',
        'matching': {'publisher': 'contains', 'domain': 'suffix'},
        'partisan_publishers': [],
        'partisan_domains': [],
        'social_domains': ['x.com'],
        'review_draft_fetch_allowed_domains': ['congress.gov', 'reuters.com'],
    }
    policy_path = _write_temp_policy(payload)
    get_source_admission_policy.cache_clear()
    try:
        policy = get_source_admission_policy(str(policy_path))
        assert policy.review_draft_fetch_allowed_domains == ('congress.gov', 'reuters.com')
    finally:
        policy_path.unlink(missing_ok=True)


def test_review_draft_fetch_allowlist_suffix_match() -> None:
    payload = {
        'version': 'source_admission_test_v1',
        'matching': {'publisher': 'contains', 'domain': 'suffix'},
        'partisan_publishers': [],
        'partisan_domains': [],
        'social_domains': ['x.com'],
        'review_draft_fetch_allowed_domains': ['congress.gov'],
    }
    policy_path = _write_temp_policy(payload)
    get_source_admission_policy.cache_clear()
    try:
        get_source_admission_policy(str(policy_path))
        assert is_review_draft_fetch_allowed('https://www.congress.gov/bill/...')
        assert is_review_draft_fetch_allowed('https://sub.congress.gov/records')
        assert not is_review_draft_fetch_allowed('https://example.com/records')
    finally:
        policy_path.unlink(missing_ok=True)
