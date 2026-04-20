import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Claim, ClaimEvaluation
from app.models.enums import ClaimStatus, Verdict
from app.schemas.api import EvaluateClaimRequest
from app.services.source_service import SourceService


class EvaluationService:
    @staticmethod
    def evaluate_claim(db: Session, claim_id: uuid.UUID, payload: EvaluateClaimRequest) -> ClaimEvaluation:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)

        if payload.verdict in {Verdict.supported, Verdict.mixed, Verdict.unsupported}:
            if not SourceService.has_minimum_evidence(db, claim_id):
                raise AppError(
                    'minimum_evidence_missing',
                    'Claim must have at least one primary and one secondary source before this verdict.',
                    status_code=422,
                )

        evaluation = ClaimEvaluation(
            claim_id=claim.id,
            verdict=payload.verdict,
            confidence=payload.confidence,
            rationale=payload.rationale.strip(),
            citation_notes=payload.citation_notes,
            reviewer_id=payload.reviewer_id,
        )

        claim.status = ClaimStatus.reviewed
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)
        return evaluation
