"""Tests for NotificationService and transports."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import AppError
from app.services.notification_service import NotificationService


class TestSelectReviewers:
    def test_claim_ready_for_publish_selects_only_admins(self) -> None:
        db = MagicMock()
        admin = MagicMock()
        admin.role = 'admin'
        reviewer = MagicMock()
        reviewer.role = 'reviewer'
        db.execute.return_value.scalars.return_value.all.return_value = [admin]

        result = NotificationService._select_reviewers(db, event_type='claim_ready_for_publish')
        assert result == [admin]

    def test_claim_ready_for_review_selects_all_active(self) -> None:
        db = MagicMock()
        users = [MagicMock(), MagicMock()]
        db.execute.return_value.scalars.return_value.all.return_value = users

        result = NotificationService._select_reviewers(db, event_type='claim_ready_for_review')
        assert result == users

    def test_proposal_needs_triage_selects_only_admins(self) -> None:
        db = MagicMock()
        admin = MagicMock()
        admin.role = 'admin'
        db.execute.return_value.scalars.return_value.all.return_value = [admin]

        result = NotificationService._select_reviewers(db, event_type='proposal_needs_triage')
        assert result == [admin]


class TestAlreadyNotified:
    def test_returns_true_when_record_exists(self) -> None:
        db = MagicMock()
        db.execute.return_value.scalar.return_value = 1
        assert NotificationService._already_notified(
            db, event_type='claim_ready_for_publish', claim_id=uuid.uuid4(), reviewer_id=uuid.uuid4()
        )

    def test_returns_false_when_no_record(self) -> None:
        db = MagicMock()
        db.execute.return_value.scalar.return_value = 0
        assert not NotificationService._already_notified(
            db, event_type='claim_ready_for_publish', claim_id=uuid.uuid4(), reviewer_id=uuid.uuid4()
        )


class TestRenderMessage:
    def test_claim_ready_for_review(self) -> None:
        subject, body = NotificationService._render_message(
            event_type='claim_ready_for_review', claim_id=uuid.uuid4()
        )
        assert 'evidence review' in subject.lower()
        assert 'ready for evidence review' in body

    def test_claim_ready_for_publish(self) -> None:
        subject, body = NotificationService._render_message(
            event_type='claim_ready_for_publish', claim_id=uuid.uuid4()
        )
        assert 'publication' in subject.lower()
        assert 'ready to publish' in body

    def test_proposal_needs_triage(self) -> None:
        subject, body = NotificationService._render_message(
            event_type='proposal_needs_triage', claim_id=None
        )
        assert 'triage' in subject.lower()
        assert 'awaiting triage' in body


class TestEnqueue:
    def test_returns_zero_when_disabled(self) -> None:
        db = MagicMock()
        with patch('app.services.notification_service.settings.notification_enabled', False):
            created, sent, failed = NotificationService.enqueue(
                db, event_type='claim_ready_for_publish', claim_id=uuid.uuid4()
            )
        assert created == 0
        assert sent == 0
        assert failed == 0

    def test_creates_records_and_sends(self) -> None:
        db = MagicMock()
        reviewer = MagicMock()
        reviewer.id = uuid.uuid4()
        reviewer.email = 'admin@local'
        reviewer.role = 'admin'
        db.execute.return_value.scalars.return_value.all.return_value = [reviewer]
        db.execute.return_value.scalar.return_value = 0

        with patch('app.services.notification_service.settings.notification_enabled', True):
            with patch('app.services.notification_service.settings.notification_webhook_url', ''):
                with patch.object(NotificationService, '_dispatch_background'):
                    created, sent, failed = NotificationService.enqueue(
                        db, event_type='claim_ready_for_publish', claim_id=uuid.uuid4()
                    )

        assert created == 1
        assert sent == 0
        assert failed == 0
        db.add.assert_called_once()
        db.commit.assert_called()

    def test_skips_already_notified(self) -> None:
        db = MagicMock()
        reviewer = MagicMock()
        reviewer.id = uuid.uuid4()
        reviewer.email = 'admin@local'
        reviewer.role = 'admin'
        db.execute.return_value.scalars.return_value.all.return_value = [reviewer]
        db.execute.return_value.scalar.return_value = 1

        with patch('app.services.notification_service.settings.notification_enabled', True):
            created, sent, failed = NotificationService.enqueue(
                db, event_type='claim_ready_for_publish', claim_id=uuid.uuid4()
            )

        assert created == 0
        assert sent == 0
        assert failed == 0


class TestProcessPending:
    def test_sends_pending_and_updates_status(self) -> None:
        db = MagicMock()
        event = MagicMock()
        event.event_type = 'claim_ready_for_publish'
        event.claim_id = uuid.uuid4()
        event.recipient_email = 'admin@local'
        event.transport = 'email'
        event.status = 'pending'
        event.error_message = None
        db.execute.return_value.scalars.return_value.all.return_value = [event]

        with patch('app.services.email_transport.EmailTransport.send') as mock_email:
            with patch('app.services.webhook_transport.WebhookTransport.is_configured', return_value=False):
                sent, failed = NotificationService.process_pending(db)

        assert sent == 1
        assert failed == 0
        assert event.status == 'sent'
        assert event.sent_at is not None
        mock_email.assert_called_once()
        db.commit.assert_called_once()

    def test_marks_failed_on_transport_error(self) -> None:
        db = MagicMock()
        event = MagicMock()
        event.event_type = 'claim_ready_for_publish'
        event.claim_id = uuid.uuid4()
        event.recipient_email = 'admin@local'
        event.transport = 'email'
        event.status = 'pending'
        event.error_message = None
        db.execute.return_value.scalars.return_value.all.return_value = [event]

        with patch('app.services.email_transport.EmailTransport.send', side_effect=RuntimeError('smtp down')):
            with patch('app.services.webhook_transport.WebhookTransport.is_configured', return_value=False):
                sent, failed = NotificationService.process_pending(db)

        assert sent == 0
        assert failed == 1
        assert event.status == 'failed'
        assert event.error_message == 'smtp down'
        db.commit.assert_called_once()


class TestTestNotification:
    def test_creates_test_event(self) -> None:
        db = MagicMock()
        reviewer = MagicMock()
        reviewer.id = uuid.uuid4()
        reviewer.email = 'admin@local'
        db.get.return_value = reviewer

        with patch('app.services.notification_service.settings.notification_webhook_url', ''):
            event = NotificationService.test_notification(db, reviewer_id=reviewer.id, event_type='claim_ready_for_publish')

        assert event.event_type == 'claim_ready_for_publish'
        assert event.recipient_email == 'admin@local'
        assert event.status == 'pending'
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_raises_when_reviewer_not_found(self) -> None:
        db = MagicMock()
        db.get.return_value = None
        with pytest.raises(AppError) as exc_info:
            NotificationService.test_notification(db, reviewer_id=uuid.uuid4(), event_type='claim_ready_for_publish')
        assert exc_info.value.status_code == 404
