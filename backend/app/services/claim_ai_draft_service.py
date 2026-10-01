from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Claim, ClaimAiDraft, ClaimEvaluation
from app.models.enums import Verdict

_DEFAULT_HISTORY_LIMIT = 20


class ClaimAiDraftService:
    """
    Persists every AI review-draft generation and exposes history/diff views so
    reviewers can see prior drafts and compare the latest one against what was
    actually submitted. Drafts remain reviewer aids only — nothing here writes
    to claim_evaluations or affects publish gates.
    """

    @staticmethod
    def _to_json_text(value: Any) -> str | None:
        if not value:
            return None
        return json.dumps(value, separators=(',', ':'), default=str)

    @staticmethod
    def _parse_json_text(value: str | None) -> list[Any]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def record_draft(db: Session, *, claim_id: uuid.UUID, payload: dict[str, Any]) -> ClaimAiDraft:
        suggested_verdict = payload['suggested_verdict']
        if not isinstance(suggested_verdict, Verdict):
            suggested_verdict = Verdict(suggested_verdict)
        draft = ClaimAiDraft(
            claim_id=claim_id,
            model=str(payload['model']),
            suggested_verdict=suggested_verdict,
            suggested_confidence=float(payload['suggested_confidence']),
            model_confidence=float(payload['model_confidence']),
            evidence_sufficiency=float(payload['evidence_sufficiency']),
            green_lane_ready=bool(payload['green_lane_ready']),
            rationale=str(payload['rationale']),
            citation_notes=str(payload['citation_notes']),
            subclaims_payload=ClaimAiDraftService._to_json_text(payload.get('subclaims')),
            source_assessments_payload=ClaimAiDraftService._to_json_text(payload.get('source_assessments')),
            warnings_payload=ClaimAiDraftService._to_json_text(payload.get('warnings')),
            missing_evidence_payload=ClaimAiDraftService._to_json_text(payload.get('missing_evidence')),
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return draft

    @staticmethod
    def _draft_to_dict(draft: ClaimAiDraft) -> dict[str, Any]:
        return {
            'id': draft.id,
            'claim_id': draft.claim_id,
            'model': draft.model,
            'suggested_verdict': draft.suggested_verdict,
            'suggested_confidence': draft.suggested_confidence,
            'model_confidence': draft.model_confidence,
            'evidence_sufficiency': draft.evidence_sufficiency,
            'green_lane_ready': draft.green_lane_ready,
            'rationale': draft.rationale,
            'citation_notes': draft.citation_notes,
            'subclaims': ClaimAiDraftService._parse_json_text(draft.subclaims_payload),
            'source_assessments': ClaimAiDraftService._parse_json_text(draft.source_assessments_payload),
            'warnings': ClaimAiDraftService._parse_json_text(draft.warnings_payload),
            'missing_evidence': ClaimAiDraftService._parse_json_text(draft.missing_evidence_payload),
            'created_at': draft.created_at,
        }

    @staticmethod
    def list_draft_history(db: Session, *, claim_id: uuid.UUID, limit: int = _DEFAULT_HISTORY_LIMIT) -> list[dict[str, Any]]:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)
        rows = (
            db.execute(
                select(ClaimAiDraft)
                .where(ClaimAiDraft.claim_id == claim_id)
                .order_by(ClaimAiDraft.created_at.desc())
                .limit(max(1, min(limit, 100)))
            )
            .scalars()
            .all()
        )
        return [ClaimAiDraftService._draft_to_dict(row) for row in rows]

    @staticmethod
    def get_draft_diff(db: Session, *, claim_id: uuid.UUID) -> dict[str, Any]:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)

        latest_draft_row = (
            db.execute(
                select(ClaimAiDraft)
                .where(ClaimAiDraft.claim_id == claim_id)
                .order_by(ClaimAiDraft.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        latest_eval_row = (
            db.execute(
                select(ClaimEvaluation)
                .where(ClaimEvaluation.claim_id == claim_id)
                .order_by(ClaimEvaluation.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        draft = ClaimAiDraftService._draft_to_dict(latest_draft_row) if latest_draft_row is not None else None
        evaluation = (
            {
                'id': latest_eval_row.id,
                'verdict': latest_eval_row.verdict,
                'confidence': latest_eval_row.confidence,
                'rationale': latest_eval_row.rationale,
                'citation_notes': latest_eval_row.citation_notes,
                'reviewer_id': latest_eval_row.reviewer_id,
                'created_at': latest_eval_row.created_at,
            }
            if latest_eval_row is not None
            else None
        )

        verdict_match: bool | None = None
        confidence_delta: float | None = None
        rationale_changed: bool | None = None
        citation_notes_changed: bool | None = None
        if draft is not None and evaluation is not None:
            verdict_match = draft['suggested_verdict'] == evaluation['verdict']
            confidence_delta = round(float(evaluation['confidence']) - float(draft['suggested_confidence']), 4)
            rationale_changed = draft['rationale'].strip() != (evaluation['rationale'] or '').strip()
            citation_notes_changed = draft['citation_notes'].strip() != (evaluation['citation_notes'] or '').strip()

        return {
            'claim_id': claim_id,
            'draft': draft,
            'evaluation': evaluation,
            'verdict_match': verdict_match,
            'confidence_delta': confidence_delta,
            'rationale_changed': rationale_changed,
            'citation_notes_changed': citation_notes_changed,
        }
