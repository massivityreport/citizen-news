import pytest
from sqlalchemy import func, select

from app import cli
from app.models import Account, Topic, Vote
from config.settings import get_settings


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setenv("DEMO_SEED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def test_seed_demo_is_refused_by_default(session, monkeypatch):
    monkeypatch.delenv("DEMO_SEED", raising=False)
    get_settings.cache_clear()
    assert cli.main(["seed-demo"]) == 2
    assert session.scalar(select(func.count()).select_from(Topic)) == 0


def test_seed_demo_is_refused_in_production(session, monkeypatch, demo_on):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("ADMIN_PASSWORD", "un-vrai-secret-long")  # otherwise the settings themselves are refused
    get_settings.cache_clear()
    assert cli.main(["seed-demo"]) == 2
    assert session.scalar(select(func.count()).select_from(Topic)) == 0


def test_seed_demo_fills_the_front_and_the_halving(session, client, demo_on):
    assert cli.main(["seed-demo"]) == 0
    session.expire_all()
    states = dict(session.execute(select(Topic.state, func.count()).group_by(Topic.state)).all())
    assert states.get("reserve") and states.get("new") and (states.get("active") or states.get("emerged"))
    codes = {i["reason"]["code"] for i in client.get("/api/topics/front?limit=50").json()["items"]}
    assert codes == {"common_priority", "strong_mobilisation", "under_the_radar", "emerging"}
    assert all(t.title.startswith("[Démo]") for t in session.scalars(select(Topic)))
    assert all(a.email.endswith("@demo.invalid") for a in session.scalars(select(Account)))


def test_seed_demo_can_be_repeated_without_duplicates(session, demo_on):
    assert cli.main(["seed-demo"]) == 0
    counts = [session.scalar(select(func.count()).select_from(m)) for m in (Topic, Account, Vote)]
    assert cli.main(["seed-demo"]) == 0
    session.expire_all()
    assert counts == [session.scalar(select(func.count()).select_from(m)) for m in (Topic, Account, Vote)]
