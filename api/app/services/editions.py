"""Read side of the published editions: always the frozen copy, never recomputed from live topics."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Edition, EditionTopic
from app.schemas import EditionOut, EditionSummary, EditionTopicOut, SourceOut


def edition_out(session: Session, edition: Edition) -> EditionOut:
    rows = session.scalars(select(EditionTopic).where(EditionTopic.edition_id == edition.id).order_by(EditionTopic.rank))
    return EditionOut(
        date=edition.edition_date,
        published_at=edition.published_at,
        participants=edition.participants,
        topics=[
            EditionTopicOut(
                rank=t.rank,
                topic_id=t.topic_id,
                title=t.title,
                summary=t.summary,
                sources=[SourceOut(**s) for s in t.sources],
                source_count=t.source_count,
                article_count=t.article_count,
                approvals=t.approvals,
                proportion=round(t.proportion, 3),
                image_url=t.image_url,
            )
            for t in rows
        ],
    )


def latest_edition(session: Session) -> EditionOut | None:
    edition = session.scalar(select(Edition).order_by(Edition.edition_date.desc()).limit(1))
    return edition_out(session, edition) if edition else None


def edition_by_date(session: Session, day: date) -> EditionOut | None:
    edition = session.scalar(select(Edition).where(Edition.edition_date == day))
    return edition_out(session, edition) if edition else None


def edition_summaries(session: Session, limit: int) -> list[EditionSummary]:
    return edition_summaries_page(session, limit, 0)


def edition_summaries_page(session: Session, limit: int, offset: int) -> list[EditionSummary]:
    count = select(func.count(EditionTopic.id)).where(EditionTopic.edition_id == Edition.id).correlate(Edition).scalar_subquery()
    rows = session.execute(
        select(Edition.edition_date, Edition.published_at, Edition.participants, count)
        .order_by(Edition.edition_date.desc())
        .limit(limit)
        .offset(offset)
    )
    return [EditionSummary(date=d, published_at=p, participants=n, topic_count=c) for d, p, n, c in rows]
