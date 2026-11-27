"""Back-office replies to an opinion: sent by e-mail first, stored only if the sending worked."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Feedback, FeedbackReply
from app.services.mailer import get_mailer
from tests.test_admin_auth import PASSWORD
from tests.test_admin_feedback import make

T0 = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


@pytest.fixture
def admin(client, mails):
    client.app.dependency_overrides[get_mailer] = lambda: mails
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


class FailingMailer:
    def send(self, to, subject, body):
        raise OSError("smtp down")


def count(session):
    session.expire_all()
    return session.scalar(select(func.count()).select_from(FeedbackReply))


def test_reply_route_is_refused_without_admin_session(client, session, mails):
    client.app.dependency_overrides[get_mailer] = lambda: mails
    fid = make(session, 1)
    assert client.post(f"/api/admin/feedback/{fid}/replies", json={"message": "Bonjour"}).status_code == 401
    assert mails.sent == [] and count(session) == 0


def test_reply_is_emailed_then_stored(admin, session, mails):
    fid = make(session, 1)
    r = admin.post(f"/api/admin/feedback/{fid}/replies", json={"message": "  Merci pour votre retour.  "})
    assert r.status_code == 201
    to, subject, body = mails.sent[0]
    assert to == "v1@example.org"
    assert "Citizen News" in subject and "Message 1" in subject
    assert "Merci pour votre retour." in body and "Message 1" in body
    detail = r.json()
    assert detail["answered"] is True
    assert [x["message"] for x in detail["replies"]] == ["Merci pour votre retour."]
    assert detail["replies"][0]["created_at"]
    assert count(session) == 1


def test_subject_quotes_the_start_of_a_long_opinion_cleanly(admin, session, mails):
    fid = make(session, 1, message="mot " * 200)
    admin.post(f"/api/admin/feedback/{fid}/replies", json={"message": "Réponse"})
    subject = mails.sent[0][1]
    assert len(subject) < 140 and subject.endswith("… »") and "mot …" not in subject


def test_several_replies_are_kept_with_their_date(admin, session, mails):
    fid = make(session, 1)
    for text in ("Première", "Seconde"):
        assert admin.post(f"/api/admin/feedback/{fid}/replies", json={"message": text}).status_code == 201
    detail = admin.get(f"/api/admin/feedback/{fid}").json()
    assert [x["message"] for x in detail["replies"]] == ["Première", "Seconde"]
    assert detail["replies"][0]["created_at"] <= detail["replies"][1]["created_at"]
    assert len(mails.sent) == 2


def test_answered_mark_in_the_list(admin, session):
    a, b = make(session, 1), make(session, 2)
    admin.post(f"/api/admin/feedback/{a}/replies", json={"message": "Réponse"})
    items = {i["id"]: i for i in admin.get("/api/admin/feedback").json()["items"]}
    assert items[a]["answered"] is True and items[b]["answered"] is False


def test_failed_sending_stores_nothing_and_reports_an_error(admin, session):
    admin.app.dependency_overrides[get_mailer] = lambda: FailingMailer()
    fid = make(session, 1)
    r = admin.post(f"/api/admin/feedback/{fid}/replies", json={"message": "Réponse"})
    assert r.status_code == 502 and "envoy" in r.json()["detail"].lower()
    assert count(session) == 0
    detail = admin.get(f"/api/admin/feedback/{fid}").json()
    assert detail["answered"] is False and detail["replies"] == []


@pytest.mark.parametrize("message", ["", "   \n ", "x" * 5001])
def test_empty_or_oversized_reply_is_refused(admin, session, mails, message):
    fid = make(session, 1)
    assert admin.post(f"/api/admin/feedback/{fid}/replies", json={"message": message}).status_code == 422
    assert mails.sent == [] and count(session) == 0


def test_unknown_opinion_is_404_and_sends_nothing(admin, mails):
    assert admin.post("/api/admin/feedback/999/replies", json={"message": "Bonjour"}).status_code == 404
    assert mails.sent == []


def test_deleting_an_opinion_deletes_its_replies(admin, session):
    keep, gone = make(session, 1), make(session, 2)
    for fid in (keep, gone):
        admin.post(f"/api/admin/feedback/{fid}/replies", json={"message": "Réponse"})
    assert count(session) == 2
    assert admin.delete(f"/api/admin/feedback/{gone}").status_code == 204
    assert count(session) == 1
    assert session.scalars(select(FeedbackReply.feedback_id)).all() == [keep]


def test_read_unread_and_counter_still_work_with_replies(admin, session):
    fid = make(session, 1)
    admin.post(f"/api/admin/feedback/{fid}/replies", json={"message": "Réponse"})
    assert admin.get("/api/admin/feedback/unread-count").json() == {"unread_count": 1}
    assert admin.post(f"/api/admin/feedback/{fid}/read").json()["replies"][0]["message"] == "Réponse"
    assert admin.get("/api/admin/feedback/unread-count").json() == {"unread_count": 0}
    assert admin.post(f"/api/admin/feedback/{fid}/unread").json()["is_read"] is False
