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
