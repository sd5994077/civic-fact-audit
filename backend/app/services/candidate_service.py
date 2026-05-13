from dataclasses import dataclass
from datetime import datetime
import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Candidate, Statement
from app.models.enums import RaceStage
from app.schemas.api import CandidateCreate, CandidateUpdate
from app.services.admin_audit_service import AdminAuditService
from app.services.auth_service import AuthService


@dataclass(frozen=True)
class CandidateRosterUpsert:
    name: str
    party: str | None
    office: str
    state: str
    election_cycle: int
    race_stage: RaceStage
    roster_status: str | None = None
    roster_source_url: str | None = None
    roster_checked_at: datetime | None = None
    roster_notes: str | None = None
    is_active: bool = True


class CandidateService:
    _RACE_CONTEXT_FIELDS = {'office', 'state', 'election_cycle', 'race_stage'}

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_required_name(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise AppError('candidate_invalid', 'Candidate name must not be blank.', status_code=422)
        return normalized

    @staticmethod
    def _normalize_optional_url(value: object | None) -> str | None:
        if value is None:
            return None
        return CandidateService._normalize_optional_text(str(value))

    @staticmethod
    def _normalize_reviewer_id(reviewer_id: str | None) -> str | None:
        return AuthService.normalize_reviewer_id(reviewer_id)

    @staticmethod
    def _enforce_candidate_dual_control(
        db: Session,
        *,
        candidate_id: uuid.UUID | None,
        approval_reviewer_id: str | None,
        applying_reviewer_id: str | None,
        action: str,
    ) -> tuple[str, str]:
        normalized_approval_reviewer_id = AuthService.resolve_active_reviewer_id(
            db,
            approval_reviewer_id,
            allowed_roles={'reviewer', 'admin'},
        )
        normalized_applying_reviewer_id = AuthService.resolve_active_reviewer_id(
            db,
            applying_reviewer_id,
            allowed_roles={'reviewer', 'admin'},
        )
        if (
            normalized_approval_reviewer_id is None
            or normalized_applying_reviewer_id is None
            or normalized_approval_reviewer_id == normalized_applying_reviewer_id
        ):
            raise AppError(
                'candidate_dual_control_required',
                'Candidate mutations require different reviewers for approval and final mutation.',
                status_code=409,
                details={
                    'candidate_id': str(candidate_id) if candidate_id is not None else None,
                    'approval_reviewer_id': normalized_approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'action': action,
                },
            )
        return normalized_approval_reviewer_id, normalized_applying_reviewer_id

    @staticmethod
    def _candidate_audit_payload(candidate: Candidate) -> dict[str, object]:
        race_stage = getattr(candidate, 'race_stage', None)
        race_stage_value = race_stage.value if hasattr(race_stage, 'value') else (str(race_stage) if race_stage else None)
        roster_checked_at = getattr(candidate, 'roster_checked_at', None)
        return {
            'id': str(candidate.id),
            'name': getattr(candidate, 'name', None),
            'party': getattr(candidate, 'party', None),
            'office': getattr(candidate, 'office', None),
            'state': getattr(candidate, 'state', None),
            'election_cycle': getattr(candidate, 'election_cycle', None),
            'race_stage': race_stage_value,
            'is_active': getattr(candidate, 'is_active', True),
            'roster_status': getattr(candidate, 'roster_status', None),
            'roster_source_url': getattr(candidate, 'roster_source_url', None),
            'roster_checked_at': roster_checked_at.isoformat() if roster_checked_at is not None else None,
            'roster_notes': getattr(candidate, 'roster_notes', None),
        }

    @staticmethod
    def _build_candidate_query(
        *,
        state: str | None,
        office: str | None,
        election_cycle: int | None,
        race_stage: RaceStage | None,
    ) -> Select[tuple[Candidate]]:
        query = select(Candidate)
        filters: list[object] = []
        if state is not None:
            filters.append(func.lower(Candidate.state) == state.strip().lower())
        if office is not None:
            filters.append(func.lower(Candidate.office) == office.strip().lower())
        if election_cycle is not None:
            filters.append(Candidate.election_cycle == election_cycle)
        if race_stage is not None:
            filters.append(Candidate.race_stage == race_stage)
        if filters:
            query = query.where(*filters)
        return query.order_by(Candidate.name.asc())

    @staticmethod
    def create_candidate(
        db: Session,
        payload: CandidateCreate,
        *,
        actor_reviewer_id: str | None = None,
        approval_reviewer_id: str | None = None,
    ) -> Candidate:
        applying_reviewer_id = actor_reviewer_id
        candidate = Candidate(
            name=CandidateService._normalize_required_name(payload.name),
            party=CandidateService._normalize_optional_text(payload.party),
            office=CandidateService._normalize_optional_text(payload.office),
            state=CandidateService._normalize_optional_text(payload.state),
            election_cycle=payload.election_cycle,
            race_stage=payload.race_stage,
            is_active=payload.is_active,
            roster_status=CandidateService._normalize_optional_text(payload.roster_status),
            roster_source_url=CandidateService._normalize_optional_url(payload.roster_source_url),
            roster_checked_at=payload.roster_checked_at,
            roster_notes=CandidateService._normalize_optional_text(payload.roster_notes),
        )
        normalized_approval_reviewer_id: str | None = None
        normalized_applying_reviewer_id: str | None = None
        if applying_reviewer_id is not None:
            normalized_approval_reviewer_id, normalized_applying_reviewer_id = CandidateService._enforce_candidate_dual_control(
                db,
                candidate_id=None,
                approval_reviewer_id=approval_reviewer_id,
                applying_reviewer_id=applying_reviewer_id,
                action='candidate_create',
            )
        db.add(candidate)
        if actor_reviewer_id is not None and normalized_applying_reviewer_id is not None:
            # Ensure DB defaults (including candidate id) are populated before audit write.
            db.flush()
            AdminAuditService.record_event(
                db,
                actor_reviewer_id=normalized_applying_reviewer_id,
                action='candidate_created',
                entity_type='candidate',
                entity_id=str(candidate.id),
                before_payload=None,
                after_payload=CandidateService._candidate_audit_payload(candidate),
                metadata={
                    'source': 'api',
                    'approval_reviewer_id': normalized_approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'dual_control_enforced': True,
                },
                commit=False,
            )
        db.commit()
        db.refresh(candidate)
        return candidate

    @staticmethod
    def get_candidate(db: Session, candidate_id: uuid.UUID) -> Candidate:
        candidate = db.get(Candidate, candidate_id)
        if candidate is None:
            raise AppError('candidate_not_found', 'Candidate does not exist.', status_code=404)
        return candidate

    @staticmethod
    def _has_statements(db: Session, candidate_id: uuid.UUID) -> bool:
        statement_count = db.execute(
            select(func.count(Statement.id)).where(Statement.candidate_id == candidate_id)
        ).scalar_one()
        return int(statement_count) > 0

    @staticmethod
    def update_candidate(
        db: Session,
        candidate_id: uuid.UUID,
        payload: CandidateUpdate,
        *,
        actor_reviewer_id: str | None = None,
        approval_reviewer_id: str | None = None,
    ) -> Candidate:
        candidate = CandidateService.get_candidate(db, candidate_id)
        before_payload = CandidateService._candidate_audit_payload(candidate)
        changed_fields: set[str] = set()
        updates: dict[str, object] = {}

        if 'name' in payload.model_fields_set:
            if payload.name is None:
                raise AppError('candidate_update_invalid', 'name cannot be null.', status_code=422)
            normalized_name = CandidateService._normalize_required_name(payload.name)
            if normalized_name != candidate.name:
                updates['name'] = normalized_name
                changed_fields.add('name')
        if 'party' in payload.model_fields_set:
            normalized_party = CandidateService._normalize_optional_text(payload.party)
            if normalized_party != candidate.party:
                updates['party'] = normalized_party
                changed_fields.add('party')
        if 'office' in payload.model_fields_set:
            normalized_office = CandidateService._normalize_optional_text(payload.office)
            if normalized_office != candidate.office:
                updates['office'] = normalized_office
                changed_fields.add('office')
        if 'state' in payload.model_fields_set:
            normalized_state = CandidateService._normalize_optional_text(payload.state)
            if normalized_state != candidate.state:
                updates['state'] = normalized_state
                changed_fields.add('state')
        if 'election_cycle' in payload.model_fields_set and payload.election_cycle != candidate.election_cycle:
            updates['election_cycle'] = payload.election_cycle
            changed_fields.add('election_cycle')
        if 'race_stage' in payload.model_fields_set and payload.race_stage != candidate.race_stage:
            updates['race_stage'] = payload.race_stage
            changed_fields.add('race_stage')
        if 'is_active' in payload.model_fields_set:
            if payload.is_active is None:
                raise AppError('candidate_update_invalid', 'is_active cannot be null.', status_code=422)
            if payload.is_active != candidate.is_active:
                updates['is_active'] = payload.is_active
                changed_fields.add('is_active')
        if 'roster_status' in payload.model_fields_set:
            normalized_roster_status = CandidateService._normalize_optional_text(payload.roster_status)
            if normalized_roster_status != candidate.roster_status:
                updates['roster_status'] = normalized_roster_status
                changed_fields.add('roster_status')
        if 'roster_source_url' in payload.model_fields_set:
            normalized_roster_source_url = CandidateService._normalize_optional_url(payload.roster_source_url)
            if normalized_roster_source_url != candidate.roster_source_url:
                updates['roster_source_url'] = normalized_roster_source_url
                changed_fields.add('roster_source_url')
        if 'roster_checked_at' in payload.model_fields_set and payload.roster_checked_at != candidate.roster_checked_at:
            updates['roster_checked_at'] = payload.roster_checked_at
            changed_fields.add('roster_checked_at')
        if 'roster_notes' in payload.model_fields_set:
            normalized_roster_notes = CandidateService._normalize_optional_text(payload.roster_notes)
            if normalized_roster_notes != candidate.roster_notes:
                updates['roster_notes'] = normalized_roster_notes
                changed_fields.add('roster_notes')

        race_context_changed = len(changed_fields.intersection(CandidateService._RACE_CONTEXT_FIELDS)) > 0
        if race_context_changed and CandidateService._has_statements(db, candidate.id):
            raise AppError(
                'candidate_update_conflict',
                'Cannot change candidate race context fields after statements exist.',
                status_code=422,
                details={
                    'changed_fields': sorted(changed_fields.intersection(CandidateService._RACE_CONTEXT_FIELDS)),
                    'rule': 'race_context_locked_after_statements',
                },
            )

        normalized_approval_reviewer_id: str | None = None
        normalized_applying_reviewer_id: str | None = None
        if actor_reviewer_id is not None:
            normalized_approval_reviewer_id, normalized_applying_reviewer_id = CandidateService._enforce_candidate_dual_control(
                db,
                candidate_id=candidate.id,
                approval_reviewer_id=approval_reviewer_id,
                applying_reviewer_id=actor_reviewer_id,
                action='candidate_update',
            )

        for field_name, value in updates.items():
            setattr(candidate, field_name, value)

        if normalized_applying_reviewer_id is not None and updates:
            AdminAuditService.record_event(
                db,
                actor_reviewer_id=normalized_applying_reviewer_id,
                action='candidate_updated',
                entity_type='candidate',
                entity_id=str(candidate.id),
                before_payload=before_payload,
                after_payload=CandidateService._candidate_audit_payload(candidate),
                metadata={
                    'source': 'api',
                    'changed_fields': sorted(changed_fields),
                    'approval_reviewer_id': normalized_approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'dual_control_enforced': True,
                },
                commit=False,
            )

        db.commit()
        db.refresh(candidate)
        return candidate

    @staticmethod
    def _get_existing_candidate_by_race_context(db: Session, entry: CandidateRosterUpsert) -> Candidate | None:
        return (
            db.execute(
                select(Candidate).where(
                    Candidate.name == CandidateService._normalize_required_name(entry.name),
                    Candidate.office == CandidateService._normalize_optional_text(entry.office),
                    Candidate.state == CandidateService._normalize_optional_text(entry.state),
                    Candidate.election_cycle == entry.election_cycle,
                    Candidate.race_stage == entry.race_stage,
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    def upsert_roster_candidates(db: Session, roster: list[CandidateRosterUpsert]) -> tuple[int, int]:
        created = 0
        updated = 0
        for entry in roster:
            existing = CandidateService._get_existing_candidate_by_race_context(db, entry)
            normalized_name = CandidateService._normalize_required_name(entry.name)
            normalized_party = CandidateService._normalize_optional_text(entry.party)
            normalized_office = CandidateService._normalize_optional_text(entry.office)
            normalized_state = CandidateService._normalize_optional_text(entry.state)
            normalized_status = CandidateService._normalize_optional_text(entry.roster_status)
            normalized_source_url = CandidateService._normalize_optional_url(entry.roster_source_url)
            normalized_notes = CandidateService._normalize_optional_text(entry.roster_notes)

            if existing is None:
                db.add(
                    Candidate(
                        name=normalized_name,
                        party=normalized_party,
                        office=normalized_office,
                        state=normalized_state,
                        election_cycle=entry.election_cycle,
                        race_stage=entry.race_stage,
                        is_active=entry.is_active,
                        roster_status=normalized_status,
                        roster_source_url=normalized_source_url,
                        roster_checked_at=entry.roster_checked_at,
                        roster_notes=normalized_notes,
                    )
                )
                created += 1
                continue

            changed = False
            if existing.party != normalized_party:
                existing.party = normalized_party
                changed = True
            if existing.is_active != entry.is_active:
                existing.is_active = entry.is_active
                changed = True
            if existing.roster_status != normalized_status:
                existing.roster_status = normalized_status
                changed = True
            if existing.roster_source_url != normalized_source_url:
                existing.roster_source_url = normalized_source_url
                changed = True
            if existing.roster_checked_at != entry.roster_checked_at:
                existing.roster_checked_at = entry.roster_checked_at
                changed = True
            if existing.roster_notes != normalized_notes:
                existing.roster_notes = normalized_notes
                changed = True
            if changed:
                updated += 1

        db.commit()
        return created, updated

    @staticmethod
    def list_candidates(
        db: Session,
        *,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
    ) -> list[Candidate]:
        query = CandidateService._build_candidate_query(
            state=state,
            office=office,
            election_cycle=election_cycle,
            race_stage=race_stage,
        )
        return db.execute(query).scalars().all()
