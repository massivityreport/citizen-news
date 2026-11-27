"""Back office: the opinions sent from the public site (list, detail, read / unread, delete).

Emails appear here and nowhere else in the back office. There are no replies yet: `answered` is always false.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.entities import Feedback
from app.schemas import AdminFeedbackDetail, AdminFeedbackItem, AdminFeedbackPage

EXCERPT_LENGTH = 140


def _excerpt(message: str) -> str:
    line = " ".join(message.split())
    return line if len(line) <= EXCERPT_LENGTH else line[: EXCERPT_LENGTH - 1].rstrip() + "…"


def unread_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Feedback).where(Feedback.is_read.is_(False))) or 0


def list_feedback(db: Session, unread_only: bool, page: int, page_size: int) -> AdminFeedbackPage:
    query = select(Feedback)
    if unread_only:
        query = query.where(Feedback.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Feedback.created_at.desc(), Feedback.id.desc()).limit(page_size).offset((page - 1) * page_size))
    items = [
        AdminFeedbackItem(
            id=f.id, created_at=f.created_at, kind=f.kind, email=f.email, page_name=f.page_name, page_url=f.page_url,
            excerpt=_excerpt(f.message), is_read=f.is_read,
        )
        for f in rows
    ]
    return AdminFeedbackPage(items=items, total=total, unread_count=unread_count(db), page=page, page_size=page_size)


def _detail(f: Feedback) -> AdminFeedbackDetail:
    return AdminFeedbackDetail(
        id=f.id, created_at=f.created_at, kind=f.kind, email=f.email, message=f.message, page_name=f.page_name,
        page_url=f.page_url, screen=f.screen, browser=f.browser, recent_actions=f.recent_actions, is_read=f.is_read,
    )


def get_feedback(db: Session, feedback_id: int) -> AdminFeedbackDetail | None:
    f = db.get(Feedback, feedback_id)
    return None if f is None else _detail(f)


def set_read(db: Session, feedback_id: int, is_read: bool) -> AdminFeedbackDetail | None:
    f = db.get(Feedback, feedback_id)
    if f is None:
        return None
    f.is_read = is_read
    db.commit()
    return _detail(f)


def delete_feedback(db: Session, feedback_id: int) -> bool:
    """Deletes the opinion and its journey (a column of the same row). Replies will cascade once their table exists."""
    deleted = db.execute(delete(Feedback).where(Feedback.id == feedback_id)).rowcount
    db.commit()
    return bool(deleted)
