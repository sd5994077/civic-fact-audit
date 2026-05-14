from functools import lru_cache

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    _DEFAULT_AUTH_SECRET = 'change-me-in-prod'
    _DEFAULT_BOOTSTRAP_PASSWORD = 'change-me'
    _DEFAULT_DB_PASSWORD = 'postgres'
    _DEFAULT_CORS_ORIGINS = ['http://localhost:5500', 'http://127.0.0.1:5500']
    _MAX_AUTH_TOKEN_TTL_MINUTES = 24 * 60

    app_name: str = 'civic-fact-audit'
    app_env: str = 'development'
    app_version: str = '0.1.0'

    postgres_host: str = 'localhost'
    postgres_port: int = 5433
    postgres_db: str = 'civic_fact_audit'
    postgres_user: str = 'postgres'
    postgres_password: str = _DEFAULT_DB_PASSWORD

    openai_api_key: str = ''
    auth_secret_key: str = _DEFAULT_AUTH_SECRET
    auth_token_ttl_minutes: int = 480
    reviewer_bootstrap_email: str = 'reviewer@local'
    reviewer_bootstrap_password: str = _DEFAULT_BOOTSTRAP_PASSWORD
    reviewer_bootstrap_name: str = 'Local Reviewer'
    reviewer_bootstrap_role: str = 'admin'
    cors_allowed_origins: list[str] = _DEFAULT_CORS_ORIGINS

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f'postgresql+psycopg://{self.postgres_user}:{self.postgres_password}'
            f'@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
        )

    @model_validator(mode='after')
    def validate_runtime_security_settings(self) -> 'Settings':
        env = (self.app_env or '').strip().lower()
        is_development = env == 'development'

        if not is_development:
            if self.auth_secret_key == self._DEFAULT_AUTH_SECRET:
                raise ValueError('auth_secret_key must be changed outside development environments')
            if self.reviewer_bootstrap_password == self._DEFAULT_BOOTSTRAP_PASSWORD:
                raise ValueError('reviewer_bootstrap_password must be changed outside development environments')
            if self.postgres_password == self._DEFAULT_DB_PASSWORD:
                raise ValueError('postgres_password must be changed outside development environments')
            if self.cors_allowed_origins == self._DEFAULT_CORS_ORIGINS:
                raise ValueError('cors_allowed_origins must be configured for non-development environments')

        if self.auth_token_ttl_minutes <= 0:
            raise ValueError('auth_token_ttl_minutes must be greater than 0')
        if self.auth_token_ttl_minutes > self._MAX_AUTH_TOKEN_TTL_MINUTES:
            raise ValueError(
                f'auth_token_ttl_minutes must be less than or equal to {self._MAX_AUTH_TOKEN_TTL_MINUTES}'
            )

        return self


@lru_cache

def get_settings() -> Settings:
    return Settings()


settings = get_settings()
