"""Back office: the opinions sent from the public site (list, detail, read / unread, delete).

Emails appear here and nowhere else in the back office. A reply is e-mailed first and stored only if the
sending worked; `answered` means at least one reply is stored.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.entities import Feedback, FeedbackReply
from app.schemas import AdminFeedbackDetail, AdminFeedbackItem, AdminFeedbackPage, AdminFeedbackReplyOut
from app.services.mailer import Mailer, reply_message


class ReplySendError(Exception):
    """The e-mail could not be sent: nothing was stored."""

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
    rows = db.scalars(query.order_by(Feedback.created_at.desc(), Feedback.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    answered = set(db.scalars(select(FeedbackReply.feedback_id).where(FeedbackReply.feedback_id.in_([f.id for f in rows])))) if rows else set()
    items = [
        AdminFeedbackItem(
            id=f.id, created_at=f.created_at, kind=f.kind, email=f.email, page_name=f.page_name, page_url=f.page_url,
            excerpt=_excerpt(f.message), is_read=f.is_read, answered=f.id in answered,
        )
        for f in rows
    ]
    return AdminFeedbackPage(items=items, total=total, unread_count=unread_count(db), page=page, page_size=page_size)


def _detail(db: Session, f: Feedback) -> AdminFeedbackDetail:
    replies = db.scalars(
        select(FeedbackReply).where(FeedbackReply.feedback_id == f.id).order_by(FeedbackReply.created_at, FeedbackReply.id)
    ).all()
    return AdminFeedbackDetail(
        id=f.id, created_at=f.created_at, kind=f.kind, email=f.email, message=f.message, page_name=f.page_name,
        page_url=f.page_url, screen=f.screen, browser=f.browser, recent_actions=f.recent_actions, is_read=f.is_read,
        answered=bool(replies), replies=[AdminFeedbackReplyOut(id=r.id, created_at=r.created_at, message=r.message) for r in replies],
    )


def get_feedback(db: Session, feedback_id: int) -> AdminFeedbackDetail | None:
    f = db.get(Feedback, feedback_id)
    return None if f is None else _detail(db, f)


def set_read(db: Session, feedback_id: int, is_read: bool) -> AdminFeedbackDetail | None:
    f = db.get(Feedback, feedback_id)
    if f is None:
        return None
    f.is_read = is_read
    db.commit()
    return _detail(db, f)


def delete_feedback(db: Session, feedback_id: int) -> bool:
    """Deletes the opinion and its journey (a column of the same row). Its replies go with it (foreign key cascade)."""
    deleted = db.execute(delete(Feedback).where(Feedback.id == feedback_id)).rowcount
    db.commit()
    return bool(deleted)


def add_reply(db: Session, mailer: Mailer, feedback_id: int, message: str) -> AdminFeedbackDetail | None:
    """E-mails `message` to the author, then stores it. If sending fails, raises ReplySendError and stores nothing."""
    f = db.get(Feedback, feedback_id)
    if f is None:
        return None
    subject, body = reply_message(f.message, message)
    try:
        mailer.send(f.email, subject, body)
    except Exception as exc:
        db.rollback()
        raise ReplySendError from exc
    db.add(FeedbackReply(feedback_id=f.id, message=message))
    db.commit()
    return _detail(db, f)
