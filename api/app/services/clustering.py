"""Group articles into topics: TF-IDF vectors + cosine similarity against topic centroids.

Algorithm (deterministic for a given database state and `now`):
- Candidates: articles without topic published in the last `window_hours`, in (date, id) order.
- Existing topics whose last article is within the window can still accept articles; older ones are frozen.
- Each article joins the closest topic whose cosine similarity to the topic centroid reaches
  `similarity_threshold`; otherwise it starts a new topic.
- Rerunning with no new article changes nothing (assigned articles are never moved).

Dates: an article's date is published_at, or fetched_at when the feed gave none. A topic's
first_seen_at / updated_at are the earliest / latest date of its articles.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import Article, Topic
from app.services.stopwords import FRENCH_STOP_WORDS
from app.services.text import truncate
from config.clustering import ClusteringParams, load_clustering_params

log = logging.getLogger(__name__)

TITLE_WEIGHT = 3  # the title is repeated this many times before the summary
SUMMARY_MAX_CHARS = 280
_LOCK_KEY = 7_302_001  # pg advisory lock: one clustering run at a time


@dataclass
class ClusterReport:
    attached: int = 0
    new_topics: int = 0
    updated_topics: int = 0


def article_date(a: Article) -> datetime:
    return a.published_at or a.fetched_at


def article_text(a: Article) -> str:
    return " ".join([a.title] * TITLE_WEIGHT + [a.summary or ""])


def _vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        strip_accents="unicode",
        lowercase=True,
        stop_words=sorted(FRENCH_STOP_WORDS),
        token_pattern=r"(?u)\b\w\w+\b",
        sublinear_tf=True,
    )


def _centroid(rows: list[int], matrix: sparse.csr_matrix) -> sparse.csr_matrix:
    return normalize(sparse.csr_matrix(matrix[rows].sum(axis=0)))


def cluster(
    session: Session,
    params: ClusteringParams | None = None,
    now: datetime | None = None,
) -> ClusterReport:
    params = params or load_clustering_params()
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=params.window_hours)
    report = ClusterReport()

    session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})

    day = func.coalesce(Article.published_at, Article.fetched_at)
    pending = list(
        session.scalars(
            select(Article).where(Article.topic_id.is_(None), day >= cutoff).order_by(day, Article.id)
        )
    )
    if not pending:
        return report
    open_topics = list(
        session.scalars(select(Topic).where(Topic.updated_at >= cutoff).order_by(Topic.id))
    )
    members: dict[int, list[Article]] = {t.id: [] for t in open_topics}
    if open_topics:
        for a in session.scalars(
            select(Article).where(Article.topic_id.in_(list(members))).order_by(day, Article.id)
        ):
            members[a.topic_id].append(a)

    # Groups are (topic or None, articles); topics without articles cannot be compared and are skipped.
    groups: list[tuple[Topic | None, list[Article]]] = [(t, members[t.id]) for t in open_topics if members[t.id]]
    corpus = [a for _, arts in groups for a in arts] + pending
    matrix = normalize(_vectorizer().fit_transform([article_text(a) for a in corpus])).tocsr()
    row_of = {a.id: i for i, a in enumerate(corpus)}

    rows = [[row_of[a.id] for a in arts] for _, arts in groups]
    centroids = [_centroid(r, matrix) for r in rows]
    touched: set[int] = set()

    for article in pending:
        i = row_of[article.id]
        k, sim = None, 0.0
        if centroids:
            sims = (sparse.vstack(centroids) @ matrix[i].T).toarray().ravel()
            top = int(np.argmax(sims))  # first maximum: the lowest group index wins ties
            k, sim = top, float(sims[top])
        if k is not None and sim >= params.similarity_threshold:
            groups[k][1].append(article)
            rows[k].append(i)
            centroids[k] = _centroid(rows[k], matrix)
        else:
            groups.append((None, [article]))
            rows.append([i])
            centroids.append(_centroid([i], matrix))
            k = len(groups) - 1
        touched.add(k)
        report.attached += 1

    for k in sorted(touched):
        topic, arts = groups[k]
        dates = [article_date(a) for a in arts]
        rep = _representative(arts, rows[k], matrix, centroids[k])
        if topic is None:
            topic = Topic(title=rep.title, summary="")
            session.add(topic)
            report.new_topics += 1
        else:
            report.updated_topics += 1
        topic.title = rep.title
        topic.summary = _summary(arts, rows[k], matrix, centroids[k])
        topic.first_seen_at = min(dates)
        topic.updated_at = max(dates)
        session.flush()
        for a in arts:
            a.topic_id = topic.id
    session.commit()
    log.info("clustering: %s", report)
    return report


def _ranked(arts: list[Article], rows: list[int], matrix, centroid) -> list[Article]:
    """Articles from most to least representative: closest to the centroid (rounded to 2 decimals so
    near-ties go to the shorter title), then shorter title, then oldest id."""
    sims = (matrix[rows] @ centroid.T).toarray().ravel()
    order = sorted(range(len(arts)), key=lambda j: (-round(float(sims[j]), 2), len(arts[j].title), arts[j].id))
    return [arts[j] for j in order]


def _representative(arts, rows, matrix, centroid) -> Article:
    return _ranked(arts, rows, matrix, centroid)[0]


def _summary(arts, rows, matrix, centroid) -> str:
    for a in _ranked(arts, rows, matrix, centroid):
        if a.summary:
            return truncate(a.summary, SUMMARY_MAX_CHARS)
    return ""
