import json

import pytest

from app.core.source_recommendation_policy import get_source_recommendation_policy


def test_policy_parser_defaults_source_category_from_source_class(tmp_path) -> None:
    policy_path = tmp_path / 'policy.json'
    payload = {
        'version': 'test-policy-v1',
        'default_limit': 6,
        'templates': [
            {
                'id': 'primary-template',
                'source_class': 'primary',
                'publisher': 'Congress.gov',
                'url_template': 'https://www.congress.gov/search?q={query}',
                'rationale': 'primary record',
                'priority': 10,
            },
            {
                'id': 'secondary-template',
                'source_class': 'secondary',
                'publisher': 'Reuters',
                'url_template': 'https://www.reuters.com/site-search/?query={query}',
                'rationale': 'secondary corroboration',
                'priority': 20,
            },
        ],
    }
    policy_path.write_text(json.dumps(payload), encoding='utf-8')

    get_source_recommendation_policy.cache_clear()
    policy = get_source_recommendation_policy(str(policy_path))

    categories = {template.template_id: template.source_category for template in policy.templates}
    assert categories['primary-template'] == 'primary_record'
    assert categories['secondary-template'] == 'secondary_news'


def test_policy_parser_rejects_invalid_source_category(tmp_path) -> None:
    policy_path = tmp_path / 'policy.json'
    payload = {
        'version': 'test-policy-v1',
        'default_limit': 6,
        'templates': [
            {
                'id': 'bad-template',
                'source_class': 'secondary',
                'source_category': 'unsupported_category',
                'publisher': 'Reuters',
                'url_template': 'https://www.reuters.com/site-search/?query={query}',
                'rationale': 'secondary corroboration',
                'priority': 20,
            }
        ],
    }
    policy_path.write_text(json.dumps(payload), encoding='utf-8')

    get_source_recommendation_policy.cache_clear()
    with pytest.raises(ValueError, match='Unsupported source_category'):
        get_source_recommendation_policy(str(policy_path))
