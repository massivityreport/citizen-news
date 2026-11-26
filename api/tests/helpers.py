"""Test data builders."""

import re
from datetime import UTC, datetime, timedelta

from app.models.entities import Article, MediaSource

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

RETRAITES = [
    ("Retraites : le gouvernement rouvre les discussions avec les syndicats",
     "Les syndicats sont reçus lundi à Matignon pour discuter de la réforme des retraites."),
    ("Réforme des retraites : syndicats et gouvernement reprennent le dialogue",
     "Les discussions sur la réforme des retraites reprennent lundi entre le gouvernement et les syndicats."),
    ("Retraites : les syndicats retrouvent le gouvernement lundi",
     "Une nouvelle séance de discussions sur les retraites s'ouvre à Matignon."),
]
FOOT = (
    "Le PSG s'impose face à Marseille dans un Classique renversant",
    "Le Paris Saint-Germain a battu l'Olympique de Marseille 2-0 au Parc des Princes.",
)
METEO = (
    "Canicule : douze départements du sud placés en vigilance orange",
    "Météo-France annonce des températures dépassant 38 degrés dans le Sud-Est.",
)


def make_sources(session, *names: str) -> list[MediaSource]:
    sources = [MediaSource(name=n, feed_url=f"https://{i}.example/rss") for i, n in enumerate(names)]
    session.add_all(sources)
    session.flush()
    return sources


def make_article(session, source, n, title, summary="", hours_ago=1.0, now=NOW, **kw) -> Article:
    a = Article(
        source_id=source.id,
        url=f"https://{source.id}.example/a/{n}",
        title=title,
        summary=summary,
        published_at=now - timedelta(hours=hours_ago),
        **kw,
    )
    session.add(a)
    session.flush()
    return a


class RecordingMailer:
    """Stands in for the Mailer: records messages instead of sending them."""

    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))

    def last_token(self) -> str:
        return re.search(r"/connexion\?token=([\w-]+)", self.sent[-1][2]).group(1)


def ask(api, email="a@example.org"):
    return api.post("/api/auth/magic-link", json={"email": email})


def add_votes(session, topic, more=0, not_priority=0, unknown=0, prefix="v"):
    """Give `topic` that many votes, each from a fresh account (one vote per account and topic)."""
    from app.models import Account, Vote

    n = session.query(Account).count()
    plan = ["more"] * more + ["not_priority"] * not_priority + ["unknown"] * unknown
    accounts = [Account(email=f"{prefix}{n + i}@example.org") for i in range(len(plan))]
    session.add_all(accounts)
    session.flush()
    session.add_all(Vote(account_id=a.id, topic_id=topic.id, choice=c) for a, c in zip(accounts, plan))
    session.flush()
