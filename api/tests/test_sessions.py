from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.deps import SESSION_COOKIE, current_account
from app.models import Account, AuthSession
from app.services import auth


@pytest.fixture
def account(session):
    a = Account(email="a@example.org")
    session.add(a)
    session.commit()
    return a


def test_session_token_stored_hashed(session, account):
    token, lifetime = auth.create_session(session, account)
    row = session.query(AuthSession).one()
    assert row.token_hash == auth.hash_token(token) and token not in row.token_hash
    assert lifetime == 30 * 86400
    assert auth.account_for_session(session, token).id == account.id


def test_unknown_expired_and_revoked_sessions(session, account):
    assert auth.account_for_session(session, "nope") is None
    past = auth.now() - timedelta(days=31)
    token, _ = auth.create_session(session, account, at=past)
    assert auth.account_for_session(session, token) is None
    token, _ = auth.create_session(session, account)
    auth.revoke_session(session, token)
    assert auth.account_for_session(session, token) is None


def test_current_account_dependency(session, account):
    app = FastAPI()

    @app.get("/who")
    def who(a: Account = Depends(current_account)):
        return {"email": a.email}

    client = TestClient(app)
    assert client.get("/who").status_code == 401
    client.cookies.set(SESSION_COOKIE, "garbage")
    assert client.get("/who").status_code == 401
    token, _ = auth.create_session(session, account)
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/who").json() == {"email": "a@example.org"}


def test_purge_expired(session, account):
    auth.create_session(session, account, at=auth.now() - timedelta(days=40))
    keep, _ = auth.create_session(session, account)
    auth.purge_expired(session)
    assert session.query(AuthSession).count() == 1
    assert auth.account_for_session(session, keep)
