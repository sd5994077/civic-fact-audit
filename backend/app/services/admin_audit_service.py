from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.moderation_policy import ModerationViolation
from app.models.entities import AdminAuditEvent


class AdminAuditService:
    @staticmethod
    def _to_json_text(payload: dict[str, Any] | None) -> str | None:
        if payload is None:
            return None
        return json.dumps(payload, separators=(',', ':'), sort_keys=True)

    @staticmethod
    def _parse_json_text(payload: str | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        text = payload.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {'raw': text}
        if isinstance(parsed, dict):
            return parsed
        return {'value': parsed}

    @staticmethod
    def record_event(
        db: Session,
        *,
        actor_reviewer_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before_payload: dict[str, Any] | None = None,
        after_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> AdminAuditEvent:
        event = AdminAuditEvent(
            actor_reviewer_id=actor_reviewer_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_payload=AdminAuditService._to_json_text(before_payload),
            after_payload=AdminAuditService._to_json_text(after_payload),
            metadata_payload=AdminAuditService._to_json_text(metadata),
        )
        db.add(event)
        if commit:
            db.commit()
            db.refresh(event)
        return event

    @staticmethod
    def _to_read_model(event: AdminAuditEvent) -> dict[str, Any]:
        return {
            'id': event.id,
            'actor_reviewer_id': event.actor_reviewer_id,
            'action': event.action,
            'entity_type': event.entity_type,
            'entity_id': event.entity_id,
            'before_payload': AdminAuditService._parse_json_text(event.before_payload),
            'after_payload': AdminAuditService._parse_json_text(event.after_payload),
            'metadata': AdminAuditService._parse_json_text(event.metadata_payload),
            'created_at': event.created_at,
            'updated_at': event.updated_at,
        }

    @staticmethod
    def get_event(db: Session, event_id: uuid.UUID) -> dict[str, Any]:
        event = db.get(AdminAuditEvent, event_id)
        if event is None:
            raise AppError('admin_audit_event_not_found', 'Admin audit event does not exist.', status_code=404)
        return AdminAuditService._to_read_model(event)

    @staticmethod
    def record_moderation_violation(
        db: Session,
        *,
        reviewer_id: str,
        text_preview: str,
        rejection_field: str,
        violation: ModerationViolation,
    ) -> None:
        AdminAuditService.record_event(
            db,
            actor_reviewer_id=reviewer_id,
            action='moderation_violation',
            entity_type='moderation_rule',
            entity_id=violation.rule_id,
            metadata={
                'rejection_field': rejection_field,
                'violation_type': violation.violation_type,
                'matched_pattern': violation.matched_pattern,
                'policy_version': violation.policy_version,
                'text_preview': text_preview[:200],
            },
        )

    @staticmethod
    def get_moderation_risk(
        db: Session,
        *,
        window_days: int = 30,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        rows = (
            db.execute(
                select(
                    AdminAuditEvent.actor_reviewer_id,
                    func.count(AdminAuditEvent.id).label('violation_count'),
                    func.max(AdminAuditEvent.created_at).label('last_violation_at'),
                )
                .where(
                    AdminAuditEvent.action == 'moderation_violation',
                    AdminAuditEvent.created_at >= cutoff,
                )
                .group_by(AdminAuditEvent.actor_reviewer_id)
                .order_by(func.count(AdminAuditEvent.id).desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        return [
            {
                'reviewer_id': row['actor_reviewer_id'],
                'violation_count': int(row['violation_count']),
                'last_violation_at': row['last_violation_at'],
            }
            for row in rows
        ]

    @staticmethod
    def list_events(
        db: Session,
        *,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        actor_reviewer_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: Select[tuple[AdminAuditEvent]] = select(AdminAuditEvent).order_by(AdminAuditEvent.created_at.desc())
        if action is not None:
            query = query.where(AdminAuditEvent.action == action.strip())
        if entity_type is not None:
            query = query.where(AdminAuditEvent.entity_type == entity_type.strip())
        if entity_id is not None:
            query = query.where(AdminAuditEvent.entity_id == entity_id.strip())
        if actor_reviewer_id is not None:
            query = query.where(AdminAuditEvent.actor_reviewer_id == actor_reviewer_id.strip())
        rows = db.execute(query.limit(limit)).scalars().all()
        return [AdminAuditService._to_read_model(row) for row in rows]
