"""Application settings, read from environment variables (and .env in development)."""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated, Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:password@host:5432/dbname
    database_url: str
    # Comma-separated list of allowed origins for CORS.
    cors_origins: Annotated[list[str], NoDecode] = []
    # Lifetime of a magic-link token, in minutes.
    login_token_ttl_minutes: int = 15
    # Public base URL of the front end: login links are `{app_base_url}/connexion?token=...`.
    app_base_url: str = "http://localhost:5173"

    # Session cookie. `cookie_secure` must be true behind HTTPS (anything but local development).
    cookie_secure: bool = False
    session_ttl_days: int = 30

    # "console" writes the login link in the API logs (development only); "smtp" sends a real e-mail.
    mail_backend: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    mail_from: str = "Citizen News <no-reply@localhost>"

    # Rate limits, per window (see app/services/ratelimit.py). Counters live in memory only.
    rate_limit_window_seconds: int = 3600
    rate_limit_magic_link_per_email: int = 5
    rate_limit_magic_link_per_ip: int = 20
    rate_limit_verify_per_ip: int = 30
    rate_limit_claim_per_account: int = 30
    # Direct votes: per account, over their own (short) window.
    rate_limit_vote_per_account: int = 120
    rate_limit_vote_window_seconds: int = 60
    # Allows `python -m app.cli seed-demo` (fictional topics, accounts and votes). Development only: refused with COOKIE_SECURE=true.
    demo_seed: bool = False
    # Take the client IP from X-Forwarded-For (last entry, added by the reverse proxy). Only behind a proxy.
    trust_proxy: bool = False

    # Maximum number of votes accepted by one POST /api/votes/claim.
    claim_max_votes: int = Field(200, ge=1, le=1000)  # 1000 = hard bound on the parsed payload

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


    @model_validator(mode="after")
    def _smtp_needs_host(self):
        if self.mail_backend == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required when MAIL_BACKEND=smtp")
        return self

    @model_validator(mode="after")
    def _no_console_mail_in_production(self):
        # COOKIE_SECURE=true means HTTPS, i.e. production: the console mailer would log working login links.
        if self.mail_backend == "console" and self.cookie_secure:
            raise ValueError(
                "MAIL_BACKEND=console is for development only and cannot be used with COOKIE_SECURE=true: "
                "login links would be written to the logs. Set MAIL_BACKEND=smtp (and SMTP_HOST)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
