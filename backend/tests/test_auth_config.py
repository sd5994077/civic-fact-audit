from pydantic import ValidationError

from app.core.config import Settings


def test_non_development_rejects_default_auth_secret_key() -> None:
    try:
        Settings(app_env='production', reviewer_bootstrap_password='not-default-123')
        assert False, 'Expected ValidationError for default auth_secret_key outside development'
    except ValidationError as exc:
        assert 'auth_secret_key must be changed outside development environments' in str(exc)


def test_non_development_rejects_default_bootstrap_password() -> None:
    try:
        Settings(app_env='staging', auth_secret_key='staging-secret-123')
        assert False, 'Expected ValidationError for default reviewer_bootstrap_password outside development'
    except ValidationError as exc:
        assert 'reviewer_bootstrap_password must be changed outside development environments' in str(exc)


def test_development_allows_default_runtime_secrets() -> None:
    settings = Settings(app_env='development')
    assert settings.auth_secret_key == 'change-me-in-prod'
    assert settings.reviewer_bootstrap_password == 'change-me'


def test_auth_token_ttl_minutes_must_be_positive() -> None:
    try:
        Settings(app_env='development', auth_token_ttl_minutes=0)
        assert False, 'Expected ValidationError for non-positive auth_token_ttl_minutes'
    except ValidationError as exc:
        assert 'auth_token_ttl_minutes must be greater than 0' in str(exc)


def test_auth_token_ttl_minutes_rejects_large_values() -> None:
    try:
        Settings(app_env='development', auth_token_ttl_minutes=1441)
        assert False, 'Expected ValidationError for oversized auth_token_ttl_minutes'
    except ValidationError as exc:
        assert 'auth_token_ttl_minutes must be less than or equal to 1440' in str(exc)


def test_auth_token_ttl_minutes_accepts_reasonable_upper_bound() -> None:
    settings = Settings(
        app_env='production',
        auth_secret_key='prod-secret-123',
        reviewer_bootstrap_password='prod-password-123',
        auth_token_ttl_minutes=1440,
    )
    assert settings.auth_token_ttl_minutes == 1440
