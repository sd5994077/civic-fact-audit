from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.moderation_policy import enforce_boundary_safe_text
from app.models.entities import Candidate, Claim, ClaimProposal, IssueFrame, Statement
from app.models.enums import ProposalStatus, ProposalType, RaceStage, SourceClass, SourceOrigin, Verdict
from app.schemas.api import AddSourceRequest, ClaimProposalCreateRequest, EvaluateClaimRequest
from app.services.admin_audit_service import AdminAuditService
from app.services.source_service import SourceService


class ProposalService:
    @staticmethod
    def _validate_source_payload(
        proposal_type: ProposalType, payload: dict[str, Any]
    ) -> AddSourceRequest:
        required = {'url', 'source_class', 'source_origin', 'quality_score'}
        missing = sorted(required.difference(payload.keys()))
        if missing:
            raise AppError(
                'invalid_proposal_payload',
                'Source proposal payload is missing required fields.',
                status_code=422,
                details={'missing_fields': missing},
            )
        try:
            source_payload = AddSourceRequest.model_validate(payload)
        except Exception as exc:
            raise AppError('invalid_proposal_payload', 'Invalid source payload field values.', status_code=422) from exc

        if proposal_type == ProposalType.candidate_source_capture and source_payload.source_origin != SourceOrigin.candidate:
            raise AppError(
                'invalid_proposal_payload',
                'candidate_source_capture proposals must use source_origin=candidate.',
                status_code=422,
            )
        if (
            proposal_type == ProposalType.verification_source_suggestion
            and source_payload.source_origin != SourceOrigin.verification
        ):
            raise AppError(
                'invalid_proposal_payload',
                'verification_source_suggestion proposals must use source_origin=verification.',
                status_code=422,
            )
        SourceService.validate_source_admission(source_payload)
        return source_payload

    @staticmethod
    def _validate_draft_verdict_payload(payload: dict[str, Any]) -> None:
        required = {'verdict', 'confidence', 'rationale', 'citation_notes'}
        missing = sorted(required.difference(payload.keys()))
        if missing:
            raise AppError(
                'invalid_proposal_payload',
                'draft_verdict payload is missing required fields.',
                status_code=422,
                details={'missing_fields': missing},
            )
        try:
            verdict = Verdict(payload['verdict'])
        except Exception as exc:
            raise AppError('invalid_proposal_payload', 'draft_verdict payload has invalid verdict.', status_code=422) from exc
        if not isinstance(payload['citation_notes'], str) or not payload['citation_notes'].strip():
            raise AppError(
                'invalid_proposal_payload',
                'draft_verdict payload requires non-empty citation_notes.',
                status_code=422,
            )
        try:
            EvaluateClaimRequest(
                verdict=verdict,
                confidence=payload['confidence'],
                rationale=payload['rationale'],
                citation_notes=payload['citation_notes'],
            )
        except Exception as exc:
            raise AppError('invalid_proposal_payload', 'draft_verdict payload has invalid field values.', status_code=422) from exc
        enforce_boundary_safe_text(text=str(payload['rationale']), rejection_field='proposal_payload.rationale')
        enforce_boundary_safe_text(text=str(payload['citation_notes']), rejection_field='proposal_payload.citation_notes')

    @staticmethod
    def _validate_payload(proposal_type: ProposalType, payload: dict[str, Any]) -> None:
        if proposal_type == ProposalType.issue_frame_mapping:
            issue_frame_id = payload.get('issue_frame_id')
            if not isinstance(issue_frame_id, str):
                raise AppError('invalid_proposal_payload', 'issue_frame_mapping payload requires issue_frame_id.', status_code=422)
            try:
                uuid.UUID(issue_frame_id)
            except ValueError as exc:
                raise AppError('invalid_proposal_payload', 'issue_frame_id must be a valid UUID string.', status_code=422) from exc
            return

        if proposal_type in {ProposalType.candidate_source_capture, ProposalType.verification_source_suggestion}:
            ProposalService._validate_source_payload(proposal_type, payload)
            return

        if proposal_type == ProposalType.draft_verdict:
            ProposalService._validate_draft_verdict_payload(payload)
            return

        raise AppError('invalid_proposal_type', 'Unsupported proposal type.', status_code=422)

    @staticmethod
    def _to_read_model(proposal: ClaimProposal) -> dict[str, Any]:
        return {
            'id': proposal.id,
            'claim_id': proposal.claim_id,
            'proposal_type': proposal.proposal_type,
            'status': proposal.status,
            'proposed_by': proposal.proposed_by,
            'reviewed_by': proposal.reviewed_by,
            'reviewed_at': proposal.reviewed_at,
            'proposal_payload': json.loads(proposal.proposal_payload),
            'review_notes': proposal.review_notes,
            'created_at': proposal.created_at,
            'updated_at': proposal.updated_at,
        }

    @staticmethod
    def create_proposal(
        db: Session,
        claim_id: uuid.UUID,
        payload: ClaimProposalCreateRequest,
        *,
        proposed_by: str,
    ) -> ClaimProposal:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)

        ProposalService._validate_payload(payload.proposal_type, payload.proposal_payload)
        normalized_proposed_by = proposed_by.strip()
        if not normalized_proposed_by:
            raise AppError('invalid_proposal_payload', 'proposed_by must not be blank.', status_code=422)
        proposal = ClaimProposal(
            claim_id=claim_id,
            proposal_type=payload.proposal_type,
            status=ProposalStatus.proposed,
            proposed_by=normalized_proposed_by,
            proposal_payload=json.dumps(payload.proposal_payload, separators=(',', ':'), sort_keys=True),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        return proposal

    @staticmethod
    def list_proposals(
        db: Session,
        *,
        status: ProposalStatus | None = None,
        proposal_type: ProposalType | None = None,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query: Select[tuple[ClaimProposal]] = (
            select(ClaimProposal)
            .join(Claim, Claim.id == ClaimProposal.claim_id)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .order_by(ClaimProposal.created_at.desc())
        )
        if status is not None:
            query = query.where(ClaimProposal.status == status)
        if proposal_type is not None:
            query = query.where(ClaimProposal.proposal_type == proposal_type)
        if state is not None:
            query = query.where(Candidate.state.is_not(None), Candidate.state.ilike(state.strip()))
        if office is not None:
            query = query.where(Candidate.office.is_not(None), Candidate.office.ilike(office.strip()))
        if election_cycle is not None:
            query = query.where(Candidate.election_cycle == election_cycle)
        if race_stage is not None:
            query = query.where(Candidate.race_stage == race_stage)

        proposals = db.execute(query.limit(limit)).scalars().all()
        return [ProposalService._to_read_model(item) for item in proposals]

    @staticmethod
    def _get_proposal(db: Session, proposal_id: uuid.UUID) -> ClaimProposal:
        proposal = db.get(ClaimProposal, proposal_id)
        if proposal is None:
            raise AppError('proposal_not_found', 'Proposal does not exist.', status_code=404)
        return proposal

    @staticmethod
    def approve_proposal(db: Session, proposal_id: uuid.UUID, *, reviewer_id: str, review_notes: str | None = None) -> ClaimProposal:
        proposal = ProposalService._get_proposal(db, proposal_id)
        if proposal.status != ProposalStatus.proposed:
            raise AppError('invalid_proposal_transition', 'Only proposed proposals can be approved.', status_code=409)
        proposal.status = ProposalStatus.approved
        proposal.reviewed_by = reviewer_id
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.review_notes = review_notes
        db.commit()
        db.refresh(proposal)
        return proposal

    @staticmethod
    def reject_proposal(db: Session, proposal_id: uuid.UUID, *, reviewer_id: str, review_notes: str | None = None) -> ClaimProposal:
        proposal = ProposalService._get_proposal(db, proposal_id)
        if proposal.status != ProposalStatus.proposed:
            raise AppError('invalid_proposal_transition', 'Only proposed proposals can be rejected.', status_code=409)
        proposal.status = ProposalStatus.rejected
        proposal.reviewed_by = reviewer_id
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.review_notes = review_notes
        db.commit()
        db.refresh(proposal)
        return proposal

    @staticmethod
    def apply_proposal(db: Session, proposal_id: uuid.UUID, *, reviewer_id: str, review_notes: str | None = None) -> dict[str, Any]:
        proposal = ProposalService._get_proposal(db, proposal_id)
        if proposal.status != ProposalStatus.approved:
            raise AppError('invalid_proposal_transition', 'Only approved proposals can be applied.', status_code=409)
        proposal_before = {
            'id': str(proposal.id),
            'claim_id': str(proposal.claim_id),
            'proposal_type': proposal.proposal_type.value,
            'status': proposal.status.value,
            'reviewed_by': proposal.reviewed_by,
            'reviewed_at': proposal.reviewed_at.isoformat() if proposal.reviewed_at is not None else None,
            'review_notes': proposal.review_notes,
        }
        try:
            payload = json.loads(proposal.proposal_payload)
        except json.JSONDecodeError as exc:
            raise AppError('invalid_proposal_payload', 'Proposal payload is not valid JSON.', status_code=422) from exc
        claim = db.get(Claim, proposal.claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)

        ProposalService._validate_payload(proposal.proposal_type, payload)

        try:
            applied_effect = 'no_change'
            if proposal.proposal_type == ProposalType.issue_frame_mapping:
                issue_frame_id = uuid.UUID(payload['issue_frame_id'])
                frame = db.get(IssueFrame, issue_frame_id)
                if frame is None:
                    raise AppError('issue_frame_not_found', 'Issue frame does not exist.', status_code=404)
                claim.issue_frame_id = frame.id
                applied_effect = 'issue_frame_mapped'
                db.flush()
            elif proposal.proposal_type in {ProposalType.candidate_source_capture, ProposalType.verification_source_suggestion}:
                source_payload = ProposalService._validate_source_payload(proposal.proposal_type, payload)
                SourceService.add_source(db, claim.id, source_payload, commit=False)
                applied_effect = 'source_attached'
            elif proposal.proposal_type == ProposalType.draft_verdict:
                applied_effect = 'draft_verdict_retained_for_reviewer_evaluate_flow'
            else:
                raise AppError('invalid_proposal_type', 'Unsupported proposal type.', status_code=422)

            proposal.status = ProposalStatus.applied
            proposal.reviewed_by = reviewer_id
            proposal.reviewed_at = datetime.now(timezone.utc)
            if review_notes is not None:
                proposal.review_notes = review_notes
            AdminAuditService.record_event(
                db,
                actor_reviewer_id=reviewer_id,
                action='proposal_applied',
                entity_type='claim_proposal',
                entity_id=str(proposal.id),
                before_payload=proposal_before,
                after_payload={
                    'id': str(proposal.id),
                    'claim_id': str(proposal.claim_id),
                    'proposal_type': proposal.proposal_type.value,
                    'status': proposal.status.value,
                    'reviewed_by': proposal.reviewed_by,
                    'reviewed_at': proposal.reviewed_at.isoformat() if proposal.reviewed_at is not None else None,
                    'review_notes': proposal.review_notes,
                },
                metadata={'applied_effect': applied_effect},
                commit=False,
            )
            db.commit()
            db.refresh(proposal)
            return {'proposal': proposal, 'applied_effect': applied_effect}
        except AppError:
            db.rollback()
            raise
