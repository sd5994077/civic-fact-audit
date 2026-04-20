import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Candidate, Claim, ClaimEvaluation, ScoreSnapshot, Source, Statement
from app.models.enums import SourceClass, Verdict

FORMULA_VERSION = 'scoring_v1_2026_04_20'


@dataclass
class ScoreComputation:
    denominator: int
    supported: int
    unsupported: int
    with_min_evidence: int
    fsr: float
    fcr: float
    esr: float
    composite: float | None


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _composite_score(fsr: float, esr: float, fcr: float) -> float:
    return round((0.5 * fsr) + (0.3 * esr) - (0.2 * fcr), 6)


def calculate_score_metrics(denominator: int, supported: int, unsupported: int, with_min_evidence: int) -> ScoreComputation:
    fsr = _rate(supported, denominator)
    fcr = _rate(unsupported, denominator)
    esr = _rate(with_min_evidence, denominator)
    composite = _composite_score(fsr, esr, fcr) if denominator > 0 else None

    return ScoreComputation(
        denominator=denominator,
        supported=supported,
        unsupported=unsupported,
        with_min_evidence=with_min_evidence,
        fsr=fsr,
        fcr=fcr,
        esr=esr,
        composite=composite,
    )


class ScoringService:
    @staticmethod
    def compute_candidate_scores(
        db: Session,
        candidate_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
        include_insufficient_in_denominator: bool,
        persist_snapshot: bool = True,
    ) -> tuple[ScoreSnapshot | None, ScoreComputation]:
        if window_end < window_start:
            raise AppError('invalid_window', 'window_end must be greater than or equal to window_start.', status_code=422)
        if db.get(Candidate, candidate_id) is None:
            raise AppError('candidate_not_found', 'Candidate does not exist.', status_code=404)

        claim_latest_eval = (
            select(ClaimEvaluation.claim_id, func.max(ClaimEvaluation.created_at).label('latest_created_at'))
            .group_by(ClaimEvaluation.claim_id)
            .subquery()
        )

        base_query = (
            select(Claim.id, ClaimEvaluation.verdict)
            .join(Statement, Statement.id == Claim.statement_id)
            .join(
                claim_latest_eval,
                claim_latest_eval.c.claim_id == Claim.id,
            )
            .join(
                ClaimEvaluation,
                and_(
                    ClaimEvaluation.claim_id == claim_latest_eval.c.claim_id,
                    ClaimEvaluation.created_at == claim_latest_eval.c.latest_created_at,
                ),
            )
            .where(
                Statement.candidate_id == candidate_id,
                Statement.published_at >= window_start,
                Statement.published_at <= window_end,
            )
        )

        evaluated_rows = db.execute(base_query).all()
        if not include_insufficient_in_denominator:
            evaluated_rows = [row for row in evaluated_rows if row.verdict != Verdict.insufficient]

        denominator = len(evaluated_rows)
        supported = sum(1 for row in evaluated_rows if row.verdict == Verdict.supported)
        unsupported = sum(1 for row in evaluated_rows if row.verdict == Verdict.unsupported)

        claim_ids = [row.id for row in evaluated_rows]
        with_min_evidence = 0
        if claim_ids:
            evidence_rows = (
                db.execute(
                    select(Source.claim_id, Source.source_class)
                    .where(Source.claim_id.in_(claim_ids))
                )
                .all()
            )
            grouped: dict[uuid.UUID, set[SourceClass]] = {}
            for row in evidence_rows:
                claim_key = row.claim_id
                grouped.setdefault(claim_key, set()).add(row.source_class)

            with_min_evidence = sum(
                1
                for claim_id in claim_ids
                if SourceClass.primary in grouped.get(claim_id, set()) and SourceClass.secondary in grouped.get(claim_id, set())
            )

        computation = calculate_score_metrics(
            denominator=denominator,
            supported=supported,
            unsupported=unsupported,
            with_min_evidence=with_min_evidence,
        )

        snapshot: ScoreSnapshot | None = None
        if persist_snapshot:
            snapshot = ScoreSnapshot(
                candidate_id=candidate_id,
                window_start=window_start,
                window_end=window_end,
                fact_support_rate=computation.fsr,
                false_claim_rate=computation.fcr,
                evidence_sufficiency_rate=computation.esr,
                composite_score=computation.composite,
                formula_version=FORMULA_VERSION,
                include_insufficient_in_denominator=include_insufficient_in_denominator,
                denominator_total=denominator,
            )
            db.add(snapshot)
            db.commit()
            db.refresh(snapshot)

        return snapshot, computation
