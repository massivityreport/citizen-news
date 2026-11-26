"""Fictional data for demos and manual checks (`python -m app.cli seed-demo`). Development only.

Creates demo media, topics titled "[Démo] …" with one article per demo medium, fictional accounts
`demo-N@demo.invalid` and votes following a few profiles (broad support, mobilisation, under the radar,
surging, rejected, brand new), then runs the halving. Everything is recognisable (reserved `.invalid`
domain, "[Démo]" prefix) and removed by the next run, so the command can be repeated. Seeded: same
`seed`, same data.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import Account, Article, MediaSource, Topic, Vote
from app.services.halving import HalvingReport, halve

DEMO_DOMAIN = "demo.invalid"
TITLE_PREFIX = "[Démo] "
MEDIA = ("Démo Matin", "Démo Soir", "Démo Hebdo")


@dataclass(frozen=True)
class Profile:
    name: str
    topics: int
    sources: int
    votes: tuple[int, int]      # min and max number of voters
    more: float                 # share of "more" among opinions
    unknown: float = 0.1        # share of "unknown" among all votes
    recent: bool = False        # votes cast within the last hours
    hours_ago: float = 3.0      # age of the topic's latest article


PROFILES = (
    Profile("Priorité commune", 4, 3, (60, 90), 0.85),
    Profile("Forte mobilisation", 3, 3, (42, 48), 0.85, unknown=0.03),
    Profile("Sous les radars", 3, 2, (20, 28), 0.9),
    Profile("Émergent", 3, 3, (14, 22), 0.8, recent=True),
    Profile("Peu soutenu", 5, 3, (22, 40), 0.15),
    Profile("Tout juste arrivé", 6, 3, (0, 5), 0.5, hours_ago=1.0),
)
ACCOUNTS = 120


@dataclass
class SeedReport:
    topics: int
    accounts: int
    votes: int
    halving: HalvingReport


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
    accounts = [Account(email=f"demo-{i}@{DEMO_DOMAIN}") for i in range(ACCOUNTS)]
    session.add_all(media + accounts)
    session.flush()

    n_topics = n_votes = 0
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
            voters = rng.sample(accounts, rng.randint(*profile.votes))
            for account in voters:
                if rng.random() < profile.unknown:
                    choice = "unknown"
                else:
                    choice = "more" if rng.random() < profile.more else "not_priority"
                hours = rng.random() * 4 if profile.recent else 8 + rng.random() * 30
                session.add(Vote(account_id=account.id, topic_id=topic.id, choice=choice, created_at=now - timedelta(hours=hours)))
                n_votes += 1
    session.flush()
    report = halve(session, now=now)  # commits
    return SeedReport(n_topics, len(accounts), n_votes, report)
