"""Application settings, read from environment variables (and .env in development)."""

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated, Literal


# Development-only admin password. The API refuses to start with it when COOKIE_SECURE=true.
DEFAULT_ADMIN_PASSWORD = "make-media-great-again"


class Settings(BaseSettings):
    # hide_input_in_errors: a validation error at startup must not echo secrets (passwords, DATABASE_URL).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

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
    # Une writes (PUT/DELETE/merge on /api/me/une*) per account, over their own short window.
    rate_limit_une_writes_per_account: int = Field(60, ge=1)
    rate_limit_une_window_seconds: int = Field(60, ge=1)
    # Edition calendar: the collective une closes every day at `edition_hour`:00 local time (see services/edition_calendar.py).
    edition_hour: int = Field(17, ge=0, le=23)
    edition_timezone: str = "Europe/Paris"
    # A topic is in the daily pool when one of its articles is newer than this (independent of the clustering window).
    pool_window_hours: int = Field(24, ge=1, le=24 * 30)
    # "Radar" tab: topics covered by at most this many distinct media.
    radar_max_sources: int = Field(3, ge=1)
    # Allows `python -m app.cli seed-demo` (fictional media and topics). Development only: refused with COOKIE_SECURE=true.
    demo_seed: bool = False
    # Back office: one shared password (no accounts). SecretStr keeps it out of reprs and logs.
    admin_password: SecretStr = Field(SecretStr(DEFAULT_ADMIN_PASSWORD), min_length=1)
    admin_session_hours: int = Field(8, ge=1, le=24 * 30)
    # Admin login attempts per IP, over their own window (brute-force protection).
    rate_limit_admin_login_per_ip: int = 10
    rate_limit_admin_login_window_seconds: int = 900
    # Take the client IP from X-Forwarded-For (last entry, added by the reverse proxy). Only behind a proxy.
    trust_proxy: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator("edition_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"EDITION_TIMEZONE inconnu : {value!r} (ex. Europe/Paris)")
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

    @property
    def admin_password_is_default(self) -> bool:
        return self.admin_password.get_secret_value() == DEFAULT_ADMIN_PASSWORD

    @model_validator(mode="after")
    def _no_default_admin_password_in_production(self):
        if self.admin_password_is_default and self.cookie_secure:
            raise ValueError(
                "ADMIN_PASSWORD is the development default and cannot be used with COOKIE_SECURE=true: "
                "anyone could open the back office. Set ADMIN_PASSWORD to a long secret of your own."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
