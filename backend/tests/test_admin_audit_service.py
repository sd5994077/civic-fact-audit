import uuid
from datetime import datetime, timezone

from app.core.errors import AppError
from app.models.entities import AdminAuditEvent
from app.services.admin_audit_service import AdminAuditService


class _FakeDb:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, AdminAuditEvent] = {}

    def add(self, obj):  # type: ignore[no-untyped-def]
        if obj.id is None:
            obj.id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        if getattr(obj, 'created_at', None) is None:
            obj.created_at = now
        obj.updated_at = now
        self.rows[obj.id] = obj

    def commit(self):  # type: ignore[no-untyped-def]
        return None

    def refresh(self, obj):  # type: ignore[no-untyped-def]
        obj.updated_at = datetime.now(timezone.utc)

    def get(self, _model, event_id):  # type: ignore[no-untyped-def]
        return self.rows.get(event_id)

    def execute(self, _query):  # type: ignore[no-untyped-def]
        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):  # type: ignore[no-untyped-def]
                return self

            def all(self):  # type: ignore[no-untyped-def]
                return self._rows

        return _Result(list(self.rows.values()))


def test_record_event_and_get_event() -> None:
    db = _FakeDb()
    event = AdminAuditService.record_event(
        db,
        actor_reviewer_id='admin@local',
        action='candidate_updated',
        entity_type='candidate',
        entity_id='abc-123',
        before_payload={'name': 'A'},
        after_payload={'name': 'B'},
        metadata={'source': 'api'},
    )

    assert event.id in db.rows
    row = AdminAuditService.get_event(db, event.id)  # type: ignore[arg-type]
    assert row['action'] == 'candidate_updated'
    assert row['before_payload'] == {'name': 'A'}
    assert row['after_payload'] == {'name': 'B'}


def test_get_event_not_found() -> None:
    db = _FakeDb()
    try:
        AdminAuditService.get_event(db, uuid.uuid4())  # type: ignore[arg-type]
        assert False, 'Expected admin_audit_event_not_found'
    except AppError as exc:
        assert exc.code == 'admin_audit_event_not_found'


def test_record_event_metadata_roundtrip_for_proposal_dual_control_fields() -> None:
    db = _FakeDb()
    event = AdminAuditService.record_event(
        db,
        actor_reviewer_id='applier@local',
        action='proposal_applied',
        entity_type='claim_proposal',
        entity_id='proposal-1',
        metadata={
            'proposal_type': 'verification_source_suggestion',
            'approval_reviewer_id': 'approver@local',
            'applying_reviewer_id': 'applier@local',
        },
    )
    row = AdminAuditService.get_event(db, event.id)  # type: ignore[arg-type]
    assert row['metadata']['proposal_type'] == 'verification_source_suggestion'
    assert row['metadata']['approval_reviewer_id'] == 'approver@local'
    assert row['metadata']['applying_reviewer_id'] == 'applier@local'


def test_record_event_metadata_roundtrip_for_dual_control_v2_events() -> None:
    db = _FakeDb()
    for action, entity_type, entity_id in [
        ('candidate_created', 'candidate', 'candidate-1'),
        ('candidate_updated', 'candidate', 'candidate-2'),
        ('claim_evaluation_overwritten', 'claim', 'claim-1'),
        ('bulk_sources_attached', 'bulk_source_attach', 'bulk-op-1'),
    ]:
        event = AdminAuditService.record_event(
            db,
            actor_reviewer_id='applier@local',
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata={
                'approval_reviewer_id': 'approver@local',
                'applying_reviewer_id': 'applier@local',
                'dual_control_enforced': True,
            },
        )
        row = AdminAuditService.get_event(db, event.id)  # type: ignore[arg-type]
        assert row['action'] == action
        assert row['metadata']['approval_reviewer_id'] == 'approver@local'
        assert row['metadata']['applying_reviewer_id'] == 'applier@local'
        assert row['metadata']['dual_control_enforced'] is True
