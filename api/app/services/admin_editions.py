"""Back office: the preview of the edition in progress and the published editions.

The preview calls `aggregate`, the very function the closing publishes with: same inputs, same ranking. It
writes nothing (only reads: no lock, no row, nothing frozen), so the closing that follows publishes as usual.
"""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Edition
from app.schemas import AdminEditionPage, AdminItem, AdminPreview, AdminTie, EditionSummary
from app.services.aggregation import RankedTopic, aggregate
from app.services.edition_calendar import edition_state
from app.services.editions import edition_summaries_page


def _item(t: RankedTopic) -> AdminItem:
    return AdminItem(
        rank=t.rank, topic_id=t.topic_id, title=t.title, approvals=t.score, proportion=round(t.proportion, 3),
        source_count=t.source_count, article_count=t.article_count, updated_at=t.updated_at,
        tied_with=t.tied_with, broken_by=t.broken_by,
    )


def preview(session: Session, now: datetime) -> AdminPreview:
    result = aggregate(session, edition_state(session, now).edition_date, now)
    return AdminPreview(
        computed_at=result.computed_at,
        edition_date=result.edition_date,
        participants=result.participants,
        topics=[_item(t) for t in result.topics],
        next=[_item(t) for t in result.next],
        ties=[AdminTie(approvals=g.approvals, topic_ids=g.topic_ids, broken_by=g.broken_by, crosses_cut=g.crosses_cut) for g in result.ties],
    )


def list_editions(session: Session, page: int, page_size: int) -> AdminEditionPage:
    total = session.scalar(select(func.count()).select_from(Edition)) or 0
    items = edition_summaries_page(session, page_size, (page - 1) * page_size)
    return AdminEditionPage(items=items, total=total, page=page, page_size=page_size)
