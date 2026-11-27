"""Closing: publish the most recent due edition, frozen, in ONE transaction.

`close_due_edition(session, now)` is called every minute by the worker (and by `close-edition`). It
- lists the due, unpublished edition dates (`pending_editions`) and publishes only the MOST RECENT one: the days a
  stopped worker missed produce no ghost editions (the calendar then moves on, since it keys on the latest
  published date),
- takes a transaction-scoped advisory lock, then looks again: two workers at the same time give one edition
  (the loser finds it published and does nothing; the unique constraint on editions.edition_date is the last
  safety net),
- calls `aggregate` (the only place that ranks) and inserts the edition and its topics (frozen copy) together:
  if anything fails, nothing is published. An edition without participants is published too (topics []).
"""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Edition, EditionTopic
from app.services.aggregation import aggregate
from app.services.edition_calendar import pending_editions

log = logging.getLogger("app.close")
LOCK_KEY = 0x434E4544  # "CNED": advisory lock of the closing


def close_due_edition(session: Session, now: datetime) -> Edition | None:
    """The edition published by this call, or None (nothing due, or someone else published it first)."""
    if not pending_editions(session, now):
        session.rollback()  # the common case, every minute: no lock, no transaction left open
        return None
    target = None
    try:
        session.execute(select(func.pg_advisory_xact_lock(LOCK_KEY)))
        pending = pending_editions(session, now)  # again, under the lock: another worker may have published
        if not pending:
            session.rollback()
            return None
        target = pending[-1]  # the most recent due one; the missed days before it stay unpublished
        result = aggregate(session, target, now)
        edition = Edition(edition_date=target, published_at=now, participants=result.participants)
        session.add(edition)
        session.flush()
        _insert_topics(session, edition, result)
        session.commit()
    except IntegrityError:
        session.rollback()
        if target is None or not session.scalar(select(Edition.id).where(Edition.edition_date == target)):
            raise  # not a lost race: a real integrity problem
        log.info("clôture : l'édition %s est déjà publiée", target)  # the lock did not cover it: unique constraint
        return None
    except BaseException:
        session.rollback()
        raise
    log.info("clôture : édition %s publiée (%d participants, %d sujets)", target, result.participants, len(result.topics))
    return edition


def _insert_topics(session: Session, edition: Edition, result) -> None:
    session.add_all(
        EditionTopic(
            edition_id=edition.id,
            rank=t.rank,
            topic_id=t.topic_id,
            title=t.title,
            summary=t.summary,
            sources=t.sources,
            source_count=t.source_count,
            article_count=t.article_count,
            approvals=t.score,
            proportion=t.proportion,
            image_url=t.image_url,
        )
        for t in result.topics
    )
    session.flush()
