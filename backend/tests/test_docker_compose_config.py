from pathlib import Path


def test_api_service_receives_anthropic_and_degraded_mode_settings() -> None:
    compose_text = (Path(__file__).parents[2] / 'docker-compose.yml').read_text(encoding='utf-8')

    expected_settings = {
        'ANTHROPIC_API_KEY': '${ANTHROPIC_API_KEY:-}',
        'ANTHROPIC_ESCALATION_MODEL': '${ANTHROPIC_ESCALATION_MODEL:-claude-sonnet-4-6}',
        'ANTHROPIC_ESCALATION_MAX_TOKENS': '${ANTHROPIC_ESCALATION_MAX_TOKENS:-2500}',
        'CIVIC_AI_DEGRADED_MODE': '${CIVIC_AI_DEGRADED_MODE:-false}',
    }
    for setting, interpolation in expected_settings.items():
        assert f'      {setting}: {interpolation}' in compose_text


def test_api_service_receives_authentication_and_bootstrap_settings() -> None:
    compose_text = (Path(__file__).parents[2] / 'docker-compose.yml').read_text(encoding='utf-8')

    expected_settings = {
        'AUTH_SECRET_KEY': '${AUTH_SECRET_KEY:-change-me-in-prod}',
        'AUTH_TOKEN_TTL_MINUTES': '${AUTH_TOKEN_TTL_MINUTES:-480}',
        'REVIEWER_BOOTSTRAP_EMAIL': '${REVIEWER_BOOTSTRAP_EMAIL:-reviewer@local}',
        'REVIEWER_BOOTSTRAP_PASSWORD': '${REVIEWER_BOOTSTRAP_PASSWORD:-change-me}',
        'REVIEWER_BOOTSTRAP_NAME': '${REVIEWER_BOOTSTRAP_NAME:-Local Reviewer}',
        'REVIEWER_BOOTSTRAP_ROLE': '${REVIEWER_BOOTSTRAP_ROLE:-admin}',
    }
    for setting, interpolation in expected_settings.items():
        assert f'      {setting}: {interpolation}' in compose_text
