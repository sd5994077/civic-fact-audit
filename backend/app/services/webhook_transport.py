"""Webhook notification transport using urllib."""

from __future__ import annotations

import json
import logging
import urllib.request
from urllib.error import HTTPError

from app.core.config import settings

logger = logging.getLogger(__name__)


class WebhookTransport:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.notification_webhook_url)

    @staticmethod
    def send(*, event_type: str, recipient_email: str, claim_id: str | None, message: str) -> None:
        if not WebhookTransport.is_configured():
            logger.warning('Webhook URL not configured; skipping webhook for %s', event_type)
            return

        payload = {
            'event_type': event_type,
            'recipient_email': recipient_email,
            'claim_id': str(claim_id) if claim_id else None,
            'message': message,
        }
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(
            settings.notification_webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status >= 400:
                    raise RuntimeError(f'Webhook returned HTTP {response.status}')
        except HTTPError as exc:
            logger.error('Webhook failed for %s: HTTP %s', event_type, exc.code)
            raise
        except Exception as exc:
            logger.error('Webhook failed for %s: %s', event_type, exc)
            raise
