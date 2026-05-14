"""Notification orchestration: deduplication, reviewer selection, and dispatch."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.models.entities import NotificationEvent, ReviewerUser

logger = logging.getLogger(__name__)

NotificationEventType = Literal[
    'claim_ready_for_review',
    'claim_ready_for_publish',
    'proposal_needs_triage',
]


class NotificationService:
    _ADMIN_ONLY_EVENTS = {'claim_ready_for_publish', 'proposal_needs_triage'}

    @staticmethod
    def _select_reviewers(
        db: Session, *, event_type: str
    ) -> list[ReviewerUser]:
        stmt = select(ReviewerUser).where(ReviewerUser.is_active.is_(True))
        if event_type in NotificationService._ADMIN_ONLY_EVENTS:
            stmt = stmt.where(ReviewerUser.role == 'admin')
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def _already_notified(
        db: Session,
        *,
        event_type: str,
        claim_id: uuid.UUID | None,
        reviewer_id: uuid.UUID,
    ) -> bool:
        stmt = select(func.count(NotificationEvent.id)).where(
            NotificationEvent.event_type == event_type,
            NotificationEvent.claim_id == claim_id,
            NotificationEvent.reviewer_id == reviewer_id,
        )
        return bool(db.execute(stmt).scalar() or 0)

    @staticmethod
    def _render_message(*, event_type: str, claim_id: uuid.UUID | None) -> tuple[str, str]:
        if event_type == 'claim_ready_for_review':
            subject = 'Claim ready for evidence review'
            body = f'A claim is now ready for evidence review. Claim ID: {claim_id}\n'
        elif event_type == 'claim_ready_for_publish':
            subject = 'Claim ready for publication'
            body = f'A claim has passed evaluation and is ready to publish. Claim ID: {claim_id}\n'
        elif event_type == 'proposal_needs_triage':
            subject = 'Proposal needs triage'
            body = 'A new proposal is awaiting triage review.\n'
        else:
            subject = 'Notification'
            body = f'Event: {event_type}\n'
        if claim_id:
            body += 'View in admin console: /admin/\n'
        return subject, body

    @staticmethod
    def enqueue(
        db: Session,
        *,
        event_type: NotificationEventType,
        claim_id: uuid.UUID | None = None,
    ) -> tuple[int, int, int]:
        if not settings.notification_enabled:
            logger.info('Notifications disabled; skipping enqueue for %s', event_type)
            return 0, 0, 0

        reviewers = NotificationService._select_reviewers(db, event_type=event_type)
        created = 0
        for reviewer in reviewers:
            if NotificationService._already_notified(
                db, event_type=event_type, claim_id=claim_id, reviewer_id=reviewer.id
            ):
                continue
            transport = 'webhook' if settings.notification_webhook_url else 'email'
            event = NotificationEvent(
                event_type=event_type,
                claim_id=claim_id,
                reviewer_id=reviewer.id,
                recipient_email=reviewer.email,
                transport=transport,
                status='pending',
            )
            db.add(event)
            created += 1
        if created:
            db.commit()
            threading.Thread(
                target=NotificationService._dispatch_background,
                daemon=True,
            ).start()
        return created, 0, 0

    @staticmethod
    def _dispatch_background() -> None:
        from app.db.database import SessionLocal

        db = SessionLocal()
        try:
            NotificationService.process_pending(db)
        except Exception:
            logger.exception('Background notification dispatch failed')
        finally:
            db.close()

    @staticmethod
    def process_pending(db: Session) -> tuple[int, int]:
        from app.services.email_transport import EmailTransport
        from app.services.webhook_transport import WebhookTransport

        stmt = select(NotificationEvent).where(
            NotificationEvent.status == 'pending',
        ).order_by(NotificationEvent.created_at)
        pending = list(db.execute(stmt).scalars().all())

        sent = 0
        failed = 0
        for event in pending:
            subject, body = NotificationService._render_message(
                event_type=event.event_type, claim_id=event.claim_id
            )
            try:
                if event.transport == 'webhook' and WebhookTransport.is_configured():
                    WebhookTransport.send(
                        event_type=event.event_type,
                        recipient_email=event.recipient_email,
                        claim_id=str(event.claim_id) if event.claim_id else None,
                        message=body,
                    )
                else:
                    EmailTransport.send(
                        to=event.recipient_email, subject=subject, body=body
                    )
                event.status = 'sent'
                event.sent_at = datetime.now(timezone.utc)
                sent += 1
            except Exception as exc:
                event.status = 'failed'
                event.error_message = str(exc)
                failed += 1
                logger.error('Notification %s failed: %s', event.id, exc)

        if sent or failed:
            db.commit()
        return sent, failed

    @staticmethod
    def list_events(
        db: Session, *, limit: int = 100, offset: int = 0, status: str | None = None
    ) -> list[NotificationEvent]:
        stmt = select(NotificationEvent).order_by(NotificationEvent.created_at.desc())
        if status is not None:
            stmt = stmt.where(NotificationEvent.status == status)
        stmt = stmt.limit(limit).offset(offset)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def test_notification(db: Session, *, reviewer_id: uuid.UUID, event_type: str) -> NotificationEvent:
        reviewer = db.get(ReviewerUser, reviewer_id)
        if reviewer is None:
            raise AppError('not_found', 'Reviewer not found.', status_code=404)

        transport = 'webhook' if settings.notification_webhook_url else 'email'
        event = NotificationEvent(
            event_type=event_type,
            reviewer_id=reviewer.id,
            recipient_email=reviewer.email,
            transport=transport,
            status='pending',
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        threading.Thread(
            target=NotificationService._dispatch_background,
            daemon=True,
        ).start()
        return event
