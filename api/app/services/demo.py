"""Fictional data for demos and manual checks (`python -m app.cli seed-demo`). Development only.

What it creates (everything recognisable: reserved `.invalid` domains, "[Démo]" title prefix):
- 5 demo media (inactive: the worker never tries to fetch them) and ~20 topics with articles from the last 24 h:
  widely covered ones (4-5 media), a few covered by 2-3 media (the "Sous les radars" tab), some with an https
  `image_url`;
- 12 fictional accounts (`demo-NN@example.invalid`, no mail is ever sent) whose unes for the edition in progress
  (`edition_state`) give a ranking with ties, one of them straddling the cut between rank 10 and 11, and topics
  without any approval;
- 3 published past editions (frozen copies, inserted directly: the pool of the past is not replayable), so the
  history, the permalinks and the back office have content.

Idempotent: a run first removes what a previous run created (demo media, topics, accounts and their unes, demo
editions), then recreates it; real data is never touched. `reset=True` also removes ALL editions and unes
(a clean calendar). Same `seed` and same `now`, same data.
"""

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    MAX_UNE_TOPICS,
    Account,
    Article,
    Edition,
    EditionTopic,
    MediaSource,
    Selection,
    Topic,
)
from app.services.edition_calendar import edition_state
from config.settings import get_settings

DEMO_DOMAIN = "demo.invalid"
EMAIL_DOMAIN = "example.invalid"
IMAGE_BASE = f"https://images.{DEMO_DOMAIN}"
TITLE_PREFIX = "[Démo] "
MEDIA = ("Démo Matin", "Démo Soir", "Démo Hebdo", "Démo Région", "Démo Express")
ACCOUNTS = 12
PAST_EDITIONS = 3

# (title, number of media, hours since the latest article, has an image, target approvals or None)
# The order matters for ties: equal approvals are ordered by media count, then by freshness (see aggregation).
# Four topics with 3 approvals (ranks 10-13) form a tie group that straddles the cut; 6-6 is broken on media count, the 3s on media count then freshness.
TOPICS: tuple[tuple[str, int, float, bool, int | None], ...] = (
    ("Budget 2027 : le Parlement adopte la loi de finances en première lecture", 5, 2.0, True, 12),
    ("Grève des transports : trafic très perturbé dans toute la région", 4, 3.5, True, 10),
    ("Canicule tardive : vigilance orange dans le sud du pays", 5, 1.5, False, 9),
    ("Le Classique : une victoire à l'arraché au Parc des Princes", 4, 5.0, True, 8),
    ("Élections municipales : les premiers sondages bousculent les favoris", 3, 4.0, False, 7),
    ("Pénurie de médecins : le plan du gouvernement reçu avec scepticisme", 4, 6.5, True, 6),
    ("Cybersécurité : une grande chaîne d'hôpitaux visée par une attaque", 3, 9.0, False, 6),
    ("Logement : les loyers continuent d'augmenter dans les grandes villes", 2, 7.0, False, 5),
    ("Climat : l'accord de la conférence internationale jugé insuffisant", 4, 12.0, True, 4),
    ("Découverte archéologique majeure sur un chantier de métro", 3, 10.0, False, 3),
    ("Intelligence artificielle : l'Europe précise les règles pour les modèles généralistes", 3, 8.0, True, 3),
    ("Agriculture : les éleveurs bloquent les routes avant le salon", 2, 14.0, False, 3),
    ("Énergie : le prix du gaz repart à la hausse avant l'hiver", 2, 18.0, False, 3),
    ("Éducation : la réforme du lycée relancée par le ministre", 2, 11.0, True, 2),
    ("Festival : un film inattendu remporte le grand prix du jury", 2, 20.0, False, 1),
    # Not in anybody's une.
    ("Une start-up locale lève dix millions d'euros pour ses batteries", 2, 2.5, True, None),
    ("Marathon de la ville : record de participation pour la 30e édition", 3, 15.0, False, None),
    ("Un phare breton rouvert au public après dix ans de travaux", 2, 22.0, True, None),
    ("Les abeilles de retour sur les toits : le bilan de la saison", 2, 16.0, False, None),
    ("Réforme du permis de conduire : ce qui change en janvier", 5, 4.5, False, None),
)

PAST_TITLES = (
    "Sommet européen : accord de dernière minute sur le budget commun",
    "Tempête sur la côte atlantique : des milliers de foyers sans électricité",
    "Football : le leader du championnat chute à domicile",
    "Santé : la campagne de vaccination d'automne démarre",
    "Inflation : les prix alimentaires en légère baisse",
    "Transports : le nouveau tarif unique adopté par la région",
    "Cinéma : un réalisateur primé pour l'ensemble de sa carrière",
    "Justice : le procès très attendu s'ouvre lundi",
    "Sciences : une sonde livre ses premières images",
    "Environnement : la forêt communale rouverte après l'incendie",
)


@dataclass
class SeedReport:
    topics: int
    articles: int
    accounts: int
    selections: int
    editions: int
    edition_date: date  # the edition in progress that the demo unes were recorded for


def purge_demo(session: Session) -> None:
    """Remove what seed_demo created. Real data stays; frozen editions are recognised by their topic titles."""
    demo_editions = select(EditionTopic.edition_id).where(EditionTopic.title.like(f"{TITLE_PREFIX}%"))
    session.execute(delete(Edition).where(Edition.id.in_(demo_editions)))  # edition_topics cascade
    session.execute(delete(Topic).where(Topic.title.like(f"{TITLE_PREFIX}%")))
    session.execute(delete(MediaSource).where(MediaSource.feed_url.like(f"https://{DEMO_DOMAIN}/%")))  # articles cascade
    session.execute(delete(Account).where(Account.email.like(f"%@{EMAIL_DOMAIN}")))  # selections, sessions cascade
    session.flush()


def seed_demo(session: Session, seed: int = 1, now: datetime | None = None, reset: bool = False) -> SeedReport:
    rng = random.Random(seed)
    now = now or datetime.now(UTC)
    if reset:
        session.execute(delete(Selection))
        session.execute(delete(Edition))
    purge_demo(session)

    media = [
        MediaSource(name=n, feed_url=f"https://{DEMO_DOMAIN}/{i}.xml", active=False) for i, n in enumerate(MEDIA)
    ]
    session.add_all(media)
    session.flush()

    topics: list[tuple[Topic, int | None]] = []
    n_articles = 0
    for k, (title, n_media, hours_ago, with_image, approvals) in enumerate(TOPICS):
        updated = now - timedelta(hours=hours_ago)
        full_title = f"{TITLE_PREFIX}{title}"
        topic = Topic(
            title=full_title,
            summary=f"Sujet fictif de démonstration : {title[0].lower()}{title[1:]}.",
            first_seen_at=updated - timedelta(hours=1 + rng.random() * 3),
            updated_at=updated,
        )
        session.add(topic)
        session.flush()
        for j, medium in enumerate(rng.sample(media, n_media)):
            published = updated - timedelta(minutes=j * 25 + rng.randint(0, 10))
            session.add(Article(
                source_id=medium.id,
                url=f"https://{DEMO_DOMAIN}/{medium.id}/{topic.id}",
                topic_id=topic.id,
                title=f"{full_title} ({medium.name})",
                summary="",
                published_at=published,
                image_url=f"{IMAGE_BASE}/{k + 1}.jpg" if with_image and j == 0 else None,
            ))
            n_articles += 1
        topics.append((topic, approvals))
    session.flush()

    n_editions = _seed_past_editions(session, now, rng)
    state = edition_state(session, now)  # after the past editions: it is the edition in progress
    n_accounts, n_selections = _seed_unes(session, topics, state.edition_date)
    session.commit()
    return SeedReport(len(topics), n_articles, n_accounts, n_selections, n_editions, state.edition_date)


def _seed_unes(session: Session, topics: list[tuple[Topic, int | None]], edition_date: date) -> tuple[int, int]:
    """Give every topic with a target its approvals, spread over the accounts (the least loaded first, so that
    nobody exceeds the 10 places of a une)."""
    accounts = [Account(email=f"demo-{i + 1:02d}@{EMAIL_DOMAIN}") for i in range(ACCOUNTS)]
    session.add_all(accounts)
    session.flush()
    load = [0] * ACCOUNTS
    count = 0
    for topic, approvals in topics:
        if not approvals:
            continue
        for i in sorted(range(ACCOUNTS), key=lambda i: (load[i], i))[:approvals]:
            assert load[i] < MAX_UNE_TOPICS
            session.add(Selection(account_id=accounts[i].id, edition_date=edition_date, topic_id=topic.id))
            load[i] += 1
            count += 1
    session.flush()
    return ACCOUNTS, count


def _seed_past_editions(session: Session, now: datetime, rng: random.Random) -> int:
    """Published editions of the PAST_EDITIONS days before today (local date), unless a real edition has that date."""
    today = now.astimezone(ZoneInfo(get_settings().edition_timezone)).date()
    taken = set(session.scalars(select(Edition.edition_date)))
    created = 0
    for n in range(1, PAST_EDITIONS + 1):
        day = today - timedelta(days=n)
        if day in taken:
            continue
        participants = 7 + 2 * n + rng.randint(0, 2)
        published_at = datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(get_settings().edition_timezone)).replace(
            hour=get_settings().edition_hour, minute=0
        ).astimezone(UTC)
        edition = Edition(edition_date=day, published_at=published_at, participants=participants)
        session.add(edition)
        session.flush()
        titles = rng.sample(PAST_TITLES, MAX_UNE_TOPICS if n == 1 else MAX_UNE_TOPICS - n)
        for rank, title in enumerate(titles, start=1):
            approvals = max(1, participants - 2 * rank + rng.randint(0, 1))
            n_media = rng.randint(2, 5)
            session.add(EditionTopic(
                edition_id=edition.id,
                rank=rank,
                topic_id=None,
                title=f"{TITLE_PREFIX}{title}",
                summary="Sujet fictif d'une édition passée.",
                sources=[
                    {
                        "name": name,
                        "url": f"https://{DEMO_DOMAIN}/archive/{day:%Y%m%d}/{rank}/{i}",
                        "title": f"{TITLE_PREFIX}{title} ({name})",
                        "published_at": (published_at - timedelta(hours=1 + i)).isoformat().replace("+00:00", "Z"),
                    }
                    for i, name in enumerate(MEDIA[:n_media])
                ],
                source_count=n_media,
                article_count=n_media,
                approvals=min(approvals, participants),
                proportion=min(approvals, participants) / participants,
                image_url=f"{IMAGE_BASE}/past-{n}-{rank}.jpg" if rank % 3 == 1 else None,
            ))
        created += 1
    session.flush()
    return created
