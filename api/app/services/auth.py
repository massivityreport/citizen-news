"""Magic-link login and sessions.

Tokens (login links and session cookies) are random, opaque, and stored hashed (SHA-256): a database
leak does not give working tokens. Randomness is high enough that an unsalted fast hash is adequate.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.entities import Account, AuthSession, LoginToken
from config.settings import get_settings

# Used or expired login tokens are kept this long, then purged (they hold an e-mail address).
PURGE_AFTER = timedelta(days=1)


def now() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def create_login_token(
    session: Session, email: str, at: datetime | None = None, draft_topic_ids: list[int] | None = None
) -> str:
    """Store a fresh single-use token for `email` and return the clear token (to be e-mailed).
    `draft_topic_ids`: the une typed before logging in, kept with the token (never in the link)."""
    at = at or now()
    token = new_token()
    session.add(
        LoginToken(
            email=email,
            token_hash=hash_token(token),
            expires_at=at + timedelta(minutes=get_settings().login_token_ttl_minutes),
            draft={"topic_ids": draft_topic_ids} if draft_topic_ids else None,
        )
    )
    session.commit()
    return token


def login_link(token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/connexion?token={token}"


def consume_login_token(session: Session, token: str, at: datetime | None = None) -> tuple[str, list[int]] | None:
    """Atomically mark the token used and erase its draft. Returns (e-mail, draft topic ids), or None if the
    token is unknown, expired or already used. The row lock makes a concurrent second use fail."""
    at = at or now()
    row = session.scalars(
        select(LoginToken)
        .where(LoginToken.token_hash == hash_token(token), LoginToken.used_at.is_(None), LoginToken.expires_at > at)
        .with_for_update()
    ).first()
    if row is None:
        session.rollback()
        return None
    email = row.email
    topic_ids = list((row.draft or {}).get("topic_ids", []))
    row.used_at = at
    row.draft = None  # the draft lives only until the token is consumed
    session.commit()
    return email, topic_ids


def get_or_create_account(session: Session, email: str) -> Account:
    session.execute(pg_insert(Account).values(email=email).on_conflict_do_nothing(index_elements=["email"]))
    account = session.scalars(select(Account).where(Account.email == email)).one()
    session.commit()
    return account


def create_session(session: Session, account: Account, at: datetime | None = None) -> tuple[str, int]:
    """Open a session for the account. Returns (clear token for the cookie, lifetime in seconds)."""
    at = at or now()
    lifetime = timedelta(days=get_settings().session_ttl_days)
    token = new_token()
    session.add(AuthSession(account_id=account.id, token_hash=hash_token(token), expires_at=at + lifetime))
    session.commit()
    return token, int(lifetime.total_seconds())


def account_for_session(session: Session, token: str, at: datetime | None = None) -> Account | None:
    return session.scalars(
        select(Account)
        .join(AuthSession, AuthSession.account_id == Account.id)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.expires_at > (at or now()))
    ).first()


def revoke_session(session: Session, token: str) -> None:
    session.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    session.commit()


def purge_expired(session: Session, at: datetime | None = None) -> None:
    at = at or now()
    session.execute(delete(AuthSession).where(AuthSession.expires_at < at))
    # An expired token is useless: forget its draft now, the row itself goes after PURGE_AFTER.
    session.execute(update(LoginToken).where(LoginToken.expires_at < at, LoginToken.draft.is_not(None)).values(draft=None))
    session.execute(delete(LoginToken).where(LoginToken.expires_at < at - PURGE_AFTER))
    session.execute(delete(LoginToken).where(LoginToken.used_at < at - PURGE_AFTER))
    session.commit()
