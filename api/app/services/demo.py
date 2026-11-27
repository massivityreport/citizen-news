"""Fictional data for demos and manual checks (`python -m app.cli seed-demo`). Development only.

Creates demo media and topics titled "[Démo] …" with one article per demo medium (a few profiles: widely
covered, little covered, brand new). Everything is recognisable (reserved `.invalid` domain, "[Démo]"
prefix) and removed by the next run, so the command can be repeated. Seeded: same `seed`, same data.
The full V2 seed (accounts with unes, an edition) comes with the last V2 task.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.entities import Account, Article, MediaSource, Topic

DEMO_DOMAIN = "demo.invalid"
TITLE_PREFIX = "[Démo] "
MEDIA = ("Démo Matin", "Démo Soir", "Démo Hebdo")


@dataclass(frozen=True)
class Profile:
    name: str
    topics: int
    sources: int
    hours_ago: float = 3.0  # age of the topic's latest article


PROFILES = (
    Profile("Très couvert", 6, 3),
    Profile("Peu couvert", 5, 2),
    Profile("Tout juste arrivé", 6, 3, hours_ago=1.0),
    Profile("Un seul média", 3, 1),
)


@dataclass
class SeedReport:
    topics: int


def purge_demo(session: Session) -> None:
    session.execute(delete(Topic).where(Topic.title.like(f"{TITLE_PREFIX}%")))
    session.execute(delete(MediaSource).where(MediaSource.feed_url.like(f"https://{DEMO_DOMAIN}/%")))
    session.execute(delete(Account).where(Account.email.like(f"%@{DEMO_DOMAIN}")))
    session.flush()


def seed_demo(session: Session, seed: int = 1, now: datetime | None = None) -> SeedReport:
    rng = random.Random(seed)
    now = now or datetime.now(UTC)
    purge_demo(session)
    media = [MediaSource(name=n, feed_url=f"https://{DEMO_DOMAIN}/{i}.xml") for i, n in enumerate(MEDIA)]
    session.add_all(media)
    session.flush()

    n_topics = 0
    for profile in PROFILES:
        for k in range(profile.topics):
            title = f"{TITLE_PREFIX}{profile.name} n°{k + 1}"
            updated = now - timedelta(hours=profile.hours_ago + rng.random() * 2)
            topic = Topic(
                title=title, summary=f"Sujet fictif de démonstration ({profile.name.lower()}).",
                first_seen_at=updated - timedelta(hours=2), updated_at=updated,
            )
            session.add(topic)
            session.flush()
            n_topics += 1
            for medium in media[: profile.sources]:
                session.add(Article(
                    source_id=medium.id, url=f"https://{DEMO_DOMAIN}/{medium.id}/{topic.id}", topic_id=topic.id,
                    title=f"{title} — {medium.name}", summary="", published_at=updated,
                ))
    session.commit()
    return SeedReport(n_topics)
