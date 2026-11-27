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


def make_topic(session, title, sources, hours_ago=1.0, now=None, **kw):
    """A topic with one article from each of `sources` (so it is eligible when len(sources) >= 2).
    `now` defaults to the real clock: eligibility is computed against it."""
    from app.models import Topic

    now = now or datetime.now(UTC)
    topic = Topic(
        title=title, summary=f"Résumé de {title}",
        first_seen_at=now - timedelta(hours=hours_ago + 1), updated_at=now - timedelta(hours=hours_ago), **kw,
    )
    session.add(topic)
    session.flush()
    for source in sources:
        make_article(session, source, f"{topic.id}-{source.id}", f"{title} ({source.name})", hours_ago=hours_ago, now=now, topic_id=topic.id)
    return topic


def original_url(request) -> str:
    """The URL the code asked for. safe_fetch connects to the validated IP, so `request.url` holds that IP
    and the real host name is in the Host header."""
    return f"{request.url.scheme}://{request.headers['host']}{request.url.raw_path.decode()}"
