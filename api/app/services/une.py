"""A citizen's personal une for the edition in progress.

Every write runs in ONE transaction that first locks the account row (SELECT ... FOR UPDATE): two writes of
the same account are serialised, so the 10-place limit cannot be exceeded by concurrent requests, and the
open/closed check and the count are made on the state the write really sees. Uniqueness
(account, edition_date, topic) is also enforced by the database.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.entities import MAX_UNE_TOPICS, Account, Selection, Topic
from app.services.edition_calendar import EditionState, edition_state
from app.services.pool import eligible_pool


class UneError(Exception):
    """A business refusal; `detail` is the French message sent to the client."""

    status = 400
    detail = ""

    def __init__(self, detail: str | None = None):
        super().__init__(detail or self.detail)
        self.detail = detail or self.detail


class UneClosed(UneError):
    status = 409
    detail = "La clôture est passée, la une du jour n'est plus modifiable"


class UneFull(UneError):
    status = 409
    detail = "Votre une est complète"


class TopicNotFound(UneError):
    status = 404
    detail = "Sujet introuvable"


class TopicNotInPool(UneError):
    status = 422
    detail = "Ce sujet n'est plus au bassin du jour"


class InvalidTopics(UneError):
    status = 422
    detail = "Sujet inconnu"


@dataclass(frozen=True)
class Une:
    state: EditionState
    topic_ids: list[int]


@dataclass(frozen=True)
class MergeResult:
    added: int
    ignored: int
    une: Une


def dedupe(topic_ids: list[int]) -> list[int]:
    return list(dict.fromkeys(topic_ids))


def current_une(session: Session, account_id: int, now: datetime) -> Une:
    state = edition_state(session, now)
    return Une(state, _topic_ids(session, account_id, state))


def _topic_ids(session: Session, account_id: int, state: EditionState) -> list[int]:
    return list(
        session.scalars(
            select(Selection.topic_id)
            .where(Selection.account_id == account_id, Selection.edition_date == state.edition_date)
            .order_by(Selection.id)  # order of addition
        )
    )


def _begin_write(session: Session, account_id: int, now: datetime) -> tuple[EditionState, list[int]]:
    """Lock the account, then read the edition state and the current une. Raises UneClosed."""
    session.scalar(select(Account.id).where(Account.id == account_id).with_for_update())
    state = edition_state(session, now)
    if not state.open:
        session.rollback()
        raise UneClosed()
    return state, _topic_ids(session, account_id, state)


def _insert(session: Session, account_id: int, state: EditionState, topic_ids: list[int]) -> None:
    if topic_ids:
        session.execute(
            pg_insert(Selection)
            .values([{"account_id": account_id, "edition_date": state.edition_date, "topic_id": t} for t in topic_ids])
            .on_conflict_do_nothing(constraint="uq_selections_account_id_edition_date_topic_id")
        )


def _existing(session: Session, topic_ids: list[int]) -> set[int]:
    return set(session.scalars(select(Topic.id).where(Topic.id.in_(topic_ids)))) if topic_ids else set()


def _fail(session: Session, error: UneError):
    session.rollback()
    raise error


def add_topic(session: Session, account_id: int, topic_id: int, now: datetime) -> Une:
    """Idempotent. 404 unknown topic, 422 topic out of the pool, 409 full une."""
    state, current = _begin_write(session, account_id, now)
    if topic_id not in current:
        if topic_id not in _existing(session, [topic_id]):
            _fail(session, TopicNotFound())
        if not eligible_pool(session, now, [topic_id]):
            _fail(session, TopicNotInPool())
        if len(current) >= MAX_UNE_TOPICS:
            _fail(session, UneFull())
        _insert(session, account_id, state, [topic_id])
        current = current + [topic_id]
    session.commit()
    return Une(state, current)


def remove_topic(session: Session, account_id: int, topic_id: int, now: datetime) -> Une:
    """Idempotent."""
    state, current = _begin_write(session, account_id, now)
    session.execute(
        delete(Selection).where(
            Selection.account_id == account_id, Selection.edition_date == state.edition_date, Selection.topic_id == topic_id
        )
    )
    session.commit()
    return Une(state, [t for t in current if t != topic_id])


def replace(session: Session, account_id: int, topic_ids: list[int], now: datetime) -> Une:
    """Make the une exactly `topic_ids` (deduplicated, <= 10, existing topics; the pool is not required here).
    Topics already in the une keep their place; new ones follow in the given order."""
    topic_ids = dedupe(topic_ids)
    if len(topic_ids) > MAX_UNE_TOPICS:
        raise InvalidTopics(f"Une une compte {MAX_UNE_TOPICS} sujets au plus")
    state, current = _begin_write(session, account_id, now)
    if len(_existing(session, topic_ids)) != len(topic_ids):
        _fail(session, InvalidTopics())
    keep = [t for t in current if t in topic_ids]
    session.execute(
        delete(Selection).where(
            Selection.account_id == account_id,
            Selection.edition_date == state.edition_date,
            Selection.topic_id.not_in(topic_ids),
        )
    )
    new = [t for t in topic_ids if t not in current]
    _insert(session, account_id, state, new)
    session.commit()
    return Une(state, keep + new)


def merge(session: Session, account_id: int, topic_ids: list[int], now: datetime) -> MergeResult:
    """Add the topics that are in the pool, without touching what is already there, up to 10 places.
    `ignored` = topics unknown, out of the pool, or that no longer fit; topics already in the une count for nothing."""
    topic_ids = dedupe(topic_ids)
    state, current = _begin_write(session, account_id, now)
    in_pool = {e.topic_id for e in eligible_pool(session, now, topic_ids)} if topic_ids else set()
    candidates = [t for t in topic_ids if t not in current]
    ignored = sum(1 for t in candidates if t not in in_pool)
    fitting = [t for t in candidates if t in in_pool]
    room = MAX_UNE_TOPICS - len(current)
    ignored += max(len(fitting) - room, 0)
    new = fitting[: max(room, 0)]
    _insert(session, account_id, state, new)
    session.commit()
    return MergeResult(len(new), ignored, Une(state, current + new))
