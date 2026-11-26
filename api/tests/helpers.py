"""Test data builders."""

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
