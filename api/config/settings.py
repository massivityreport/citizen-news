"""Application settings, read from environment variables (and .env in development)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:password@host:5432/dbname
    database_url: str
    # Comma-separated list of allowed origins for CORS.
    cors_origins: Annotated[list[str], NoDecode] = []
    # Lifetime of a magic-link token, in minutes (used by the auth task).
    login_token_ttl_minutes: int = 15

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
