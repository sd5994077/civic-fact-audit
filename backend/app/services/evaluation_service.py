import uuid

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Candidate, Claim, ClaimEvaluation, Source, Statement
from app.models.enums import ClaimStatus, RaceStage, SourceClass, Verdict
from app.schemas.api import EvaluateClaimRequest
from app.services.source_service import SourceService


class EvaluationService:
    @staticmethod
    def _fact_checkable_predicate():
        return Claim.fact_checkable.is_(True)

    @staticmethod
    def _build_review_queue_query(
        *,
        state: str | None,
        office: str | None,
        election_cycle: int | None,
        race_stage: RaceStage | None,
        require_minimum_evidence: bool,
    ):
        primary_count = func.sum(case((Source.source_class == SourceClass.primary, 1), else_=0))
        secondary_count = func.sum(case((Source.source_class == SourceClass.secondary, 1), else_=0))

        latest_eval = (
            select(ClaimEvaluation.claim_id, func.max(ClaimEvaluation.created_at).label('latest_created_at'))
            .group_by(ClaimEvaluation.claim_id)
            .subquery()
        )

        query = (
            select(
                Claim.id.label('claim_id'),
                Claim.claim_text,
                Claim.issue_tag,
                Claim.status,
                Statement.source_url.label('statement_source_url'),
                Statement.published_at,
                Candidate.id.label('candidate_id'),
                Candidate.name.label('candidate_name'),
                Candidate.party,
                Candidate.office,
                Candidate.state,
                Candidate.election_cycle,
                Candidate.race_stage,
                primary_count.label('primary_count'),
                secondary_count.label('secondary_count'),
                ClaimEvaluation.verdict.label('latest_verdict'),
                ClaimEvaluation.confidence.label('latest_confidence'),
                ClaimEvaluation.rationale.label('latest_rationale'),
                ClaimEvaluation.citation_notes.label('latest_citation_notes'),
                ClaimEvaluation.reviewer_id.label('latest_reviewer_id'),
                ClaimEvaluation.created_at.label('latest_evaluated_at'),
            )
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .outerjoin(Source, Source.claim_id == Claim.id)
            .outerjoin(latest_eval, latest_eval.c.claim_id == Claim.id)
            .outerjoin(
                ClaimEvaluation,
                and_(
                    ClaimEvaluation.claim_id == latest_eval.c.claim_id,
                    ClaimEvaluation.created_at == latest_eval.c.latest_created_at,
                ),
            )
            .where(EvaluationService._fact_checkable_predicate())
            .group_by(
                Claim.id,
                Claim.claim_text,
                Claim.issue_tag,
                Claim.status,
                Statement.source_url,
                Statement.published_at,
                Candidate.id,
                Candidate.name,
                Candidate.party,
                Candidate.office,
                Candidate.state,
                Candidate.election_cycle,
                Candidate.race_stage,
                ClaimEvaluation.verdict,
                ClaimEvaluation.confidence,
                ClaimEvaluation.rationale,
                ClaimEvaluation.citation_notes,
                ClaimEvaluation.reviewer_id,
                ClaimEvaluation.created_at,
            )
            .order_by(Statement.published_at.desc(), Candidate.name.asc())
        )

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

        if require_minimum_evidence:
            query = query.having(primary_count > 0, secondary_count > 0)

        return query

    @staticmethod
    def list_review_queue(
        db: Session,
        *,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
        require_minimum_evidence: bool = True,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        rows = (
            db.execute(
                EvaluationService._build_review_queue_query(
                    state=state,
                    office=office,
                    election_cycle=election_cycle,
                    race_stage=race_stage,
                    require_minimum_evidence=require_minimum_evidence,
                ).limit(limit)
            )
            .mappings()
            .all()
        )

        return [
            {
                'claim_id': row['claim_id'],
                'claim_text': row['claim_text'],
                'issue_tag': row['issue_tag'],
                'status': ClaimStatus(row['status']),
                'statement_source_url': row['statement_source_url'],
                'statement_published_at': row['published_at'],
                'candidate_id': row['candidate_id'],
                'candidate_name': row['candidate_name'],
                'candidate_party': row['party'],
                'candidate_office': row['office'],
                'candidate_state': row['state'],
                'election_cycle': row['election_cycle'],
                'race_stage': row['race_stage'],
                'primary_source_count': int(row['primary_count']),
                'secondary_source_count': int(row['secondary_count']),
                'latest_verdict': row['latest_verdict'],
                'latest_confidence': row['latest_confidence'],
                'latest_rationale': row['latest_rationale'],
                'latest_citation_notes': row['latest_citation_notes'],
                'latest_reviewer_id': row['latest_reviewer_id'],
                'latest_evaluated_at': row['latest_evaluated_at'],
            }
            for row in rows
        ]

    @staticmethod
    def evaluate_claim(db: Session, claim_id: uuid.UUID, payload: EvaluateClaimRequest, reviewer_id: str) -> ClaimEvaluation:
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
            reviewer_id=reviewer_id,
        )

        claim.status = ClaimStatus.reviewed
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)
        return evaluation
