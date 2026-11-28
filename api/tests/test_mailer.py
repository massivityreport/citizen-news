import logging

import pytest

from app.services import mailer
from config.settings import Settings


OWN_PASSWORD = "un-vrai-secret-long"


def _settings(**kw):
    return Settings(database_url="postgresql+psycopg://x/x", **kw)


class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.calls = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append(("send", message))


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)


def test_smtp_sends_with_starttls_and_login():
    m = mailer.SmtpMailer(_settings(mail_backend="smtp", smtp_host="mail.test", smtp_port=2525,
                                    smtp_user="u", smtp_password="p", mail_from="N <n@x.org>"))
    m.send("a@example.org", "Sujet", "Corps du message")
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("mail.test", 2525)
    assert smtp.calls[:2] == ["starttls", ("login", "u", "p")]
    message = smtp.calls[2][1]
    assert (message["To"], message["From"], message["Subject"]) == ("a@example.org", "N <n@x.org>", "Sujet")
    assert "Corps du message" in message.get_content()


def test_smtp_without_starttls_nor_login():
    m = mailer.SmtpMailer(_settings(mail_backend="smtp", smtp_host="mailpit", smtp_port=1025, smtp_starttls=False))
    m.send("a@example.org", "S", "B")
    assert [c if isinstance(c, str) else c[0] for c in FakeSMTP.instances[0].calls] == ["send"]


def test_smtp_backend_requires_host():
    with pytest.raises(ValueError):
        _settings(mail_backend="smtp")


def test_console_mailer_logs_the_message(caplog):
    with caplog.at_level(logging.WARNING, logger="app.mail"):
        mailer.ConsoleMailer().send("a@example.org", "S", "http://front/connexion?token=abc")
    assert "token=abc" in caplog.text and not FakeSMTP.instances


def test_get_mailer_follows_backend(monkeypatch):
    monkeypatch.setattr(mailer, "get_settings", lambda: _settings())
    assert isinstance(mailer.get_mailer(), mailer.ConsoleMailer)
    monkeypatch.setattr(mailer, "get_settings", lambda: _settings(mail_backend="smtp", smtp_host="h"))
    assert isinstance(mailer.get_mailer(), mailer.SmtpMailer)


def test_login_message_contains_link():
    subject, body = mailer.login_message("http://front/connexion?token=t", 15)
    assert "http://front/connexion?token=t" in body and "15 minutes" in body and subject


def test_console_backend_refused_with_secure_cookies():
    with pytest.raises(ValueError, match="MAIL_BACKEND=console"):
        _settings(mail_backend="console", cookie_secure=True, admin_password=OWN_PASSWORD)
    _settings(mail_backend="smtp", smtp_host="h", cookie_secure=True, admin_password=OWN_PASSWORD)  # fine


def test_each_production_refusal_fires_on_its_own():
    # Default admin password only (mailer is fine): refused for ADMIN_PASSWORD, not for the mailer.
    with pytest.raises(ValueError, match="ADMIN_PASSWORD") as e:
        _settings(mail_backend="smtp", smtp_host="h", cookie_secure=True)
    assert "MAIL_BACKEND" not in str(e.value)
    # Console mailer only (password is fine): refused for the mailer, not for ADMIN_PASSWORD.
    with pytest.raises(ValueError, match="MAIL_BACKEND=console") as e:
        _settings(mail_backend="console", cookie_secure=True, admin_password=OWN_PASSWORD)
    assert "ADMIN_PASSWORD" not in str(e.value)


def test_console_backend_warns_at_startup(caplog, database_url):
    from app.main import create_app

    with caplog.at_level(logging.WARNING, logger="app.mail"):
        create_app()
    assert "MAIL_BACKEND=console" in caplog.text and "Development only" in caplog.text


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r", " ", "\x0b", "\x1c"])
def test_reply_subject_cannot_inject_a_header(separator):
    """An opinion beginning with a line break then `Bcc:` must stay inside the subject, on one line."""
    subject, _ = mailer.reply_message(f"Bonjour{separator}Bcc: espion@exemple.org", "Merci")
    assert "\n" not in subject and "\r" not in subject
    m = mailer.SmtpMailer(_settings(mail_backend="smtp", smtp_host="mailpit", smtp_port=1025, smtp_starttls=False))
    m.send("auteur@exemple.org", subject, "Merci")
    [(_, message)] = [c for c in FakeSMTP.instances[-1].calls if c[0] == "send"]
    assert message["Bcc"] is None
    assert set(message.keys()) == {"From", "To", "Subject", "Content-Type", "Content-Transfer-Encoding", "MIME-Version"}
    sent = message.as_bytes()
    assert b"\nBcc:" not in sent and b"\rBcc:" not in sent
