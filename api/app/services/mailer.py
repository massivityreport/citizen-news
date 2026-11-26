"""E-mail sending behind a small interface. Backend chosen by MAIL_BACKEND ("console" or "smtp")."""

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from config.settings import Settings, get_settings

logger = logging.getLogger("app.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleMailer:
    """Development only: writes the whole message, login link included, in the API logs."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("MAIL_BACKEND=console, e-mail not sent. To: %s | Subject: %s\n%s", to, subject, body)


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.starttls = settings.smtp_starttls
        self.sender = settings.mail_from

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password or "")
            smtp.send_message(message)


def get_mailer() -> Mailer:
    """FastAPI dependency (overridable in tests)."""
    settings = get_settings()
    return SmtpMailer(settings) if settings.mail_backend == "smtp" else ConsoleMailer()


def login_message(link: str, ttl_minutes: int) -> tuple[str, str]:
    subject = "Votre lien de connexion à Citizen News"
    body = (
        "Bonjour,\n\n"
        f"Pour vous connecter à Citizen News, ouvrez ce lien (valable {ttl_minutes} minutes, usage unique) :\n\n"
        f"{link}\n\n"
        "Si vous n'avez rien demandé, ignorez simplement ce message.\n"
    )
    return subject, body
