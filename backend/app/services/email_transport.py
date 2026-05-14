"""Email notification transport using smtplib."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailTransport:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)

    @staticmethod
    def send(*, to: str, subject: str, body: str) -> None:
        if not EmailTransport.is_configured():
            logger.warning('SMTP not configured; skipping email to %s', to)
            return

        msg = MIMEText(body, 'plain')
        msg['Subject'] = subject
        msg['From'] = settings.notification_from
        msg['To'] = to

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.notification_from, [to], msg.as_string())
        except Exception as exc:
            logger.error('Email send failed to %s: %s', to, exc)
            raise
