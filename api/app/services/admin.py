"""Back-office sessions: one shared password, no accounts.

The cookie holds an opaque random token; only its SHA-256 is stored (same scheme as citizen sessions,
but a separate table and cookie, so neither kind of session grants anything on the other side).
"""

import hmac
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import AdminSession
from app.services.auth import hash_token, new_token, now
from config.settings import get_settings


def password_matches(candidate: str) -> bool:
    """Constant-time comparison, on bytes (compare_digest on str raises for non-ASCII)."""
    expected = get_settings().admin_password.get_secret_value()
    return hmac.compare_digest(candidate.encode(), expected.encode())


def session_lifetime() -> timedelta:
    return timedelta(hours=get_settings().admin_session_hours)


def create_session(db: Session, at: datetime | None = None) -> tuple[str, int]:
    """Open an admin session. Returns (clear token for the cookie, lifetime in seconds)."""
    at = at or now()
    lifetime = session_lifetime()
    token = new_token()
    db.add(AdminSession(token_hash=hash_token(token), expires_at=at + lifetime))
    db.commit()
    return token, int(lifetime.total_seconds())


def is_valid_session(db: Session, token: str, at: datetime | None = None) -> bool:
    return (
        db.scalar(
            select(AdminSession.id).where(
                AdminSession.token_hash == hash_token(token), AdminSession.expires_at > (at or now())
            )
        )
        is not None
    )


def revoke_session(db: Session, token: str) -> None:
    db.execute(delete(AdminSession).where(AdminSession.token_hash == hash_token(token)))
    db.commit()


def purge_expired(db: Session, at: datetime | None = None) -> None:
    db.execute(delete(AdminSession).where(AdminSession.expires_at < (at or now())))
    db.commit()
