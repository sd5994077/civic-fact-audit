import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import CandidateScoreResponse, ErrorResponse, ScoreBreakdown
from app.services.scoring_service import FORMULA_VERSION, ScoringService

router = APIRouter(prefix='/candidates')


@router.get('/{candidate_id}/scores', response_model=CandidateScoreResponse, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}})
def get_scores(
    candidate_id: uuid.UUID,
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    include_insufficient_in_denominator: bool = Query(default=False),
    persist_snapshot: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> CandidateScoreResponse:
    computed_window_start = window_start or datetime(1970, 1, 1, tzinfo=timezone.utc)
    computed_window_end = window_end or datetime.now(timezone.utc)

    snapshot, computed = ScoringService.compute_candidate_scores(
        db=db,
        candidate_id=candidate_id,
        window_start=computed_window_start,
        window_end=computed_window_end,
        include_insufficient_in_denominator=include_insufficient_in_denominator,
        persist_snapshot=persist_snapshot,
    )

    return CandidateScoreResponse(
        candidate_id=candidate_id,
        window_start=computed_window_start,
        window_end=computed_window_end,
        fact_support_rate=snapshot.fact_support_rate if snapshot else computed.fsr,
        false_claim_rate=snapshot.false_claim_rate if snapshot else computed.fcr,
        evidence_sufficiency_rate=snapshot.evidence_sufficiency_rate if snapshot else computed.esr,
        composite_score=snapshot.composite_score if snapshot else computed.composite,
        breakdown=ScoreBreakdown(
            formula_version=snapshot.formula_version if snapshot else FORMULA_VERSION,
            include_insufficient_in_denominator=include_insufficient_in_denominator,
            evaluated_claims_denominator=computed.denominator,
            supported_claims_numerator=computed.supported,
            unsupported_claims_numerator=computed.unsupported,
            claims_with_minimum_evidence_numerator=computed.with_min_evidence,
        ),
    )
