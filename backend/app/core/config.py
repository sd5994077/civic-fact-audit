from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = 'civic-fact-audit'
    app_env: str = 'development'
    app_version: str = '0.1.0'

    postgres_host: str = 'localhost'
    postgres_port: int = 5433
    postgres_db: str = 'civic_fact_audit'
    postgres_user: str = 'postgres'
    postgres_password: str = 'postgres'

    openai_api_key: str = ''

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f'postgresql+psycopg://{self.postgres_user}:{self.postgres_password}'
            f'@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
        )


@lru_cache

def get_settings() -> Settings:
    return Settings()


settings = get_settings()
