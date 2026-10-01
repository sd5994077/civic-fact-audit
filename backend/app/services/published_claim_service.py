import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import Candidate, Claim, ClaimEvaluation, Source, Statement
from app.models.enums import RaceStage, SourceOrigin
from app.schemas.api import DashboardClaimRead, SourceRead
from app.services.comparison_service import _build_item_warnings, _sanitize_public_rationale


class PublishedClaimService:
    @staticmethod
    def list_claims(
        db: Session, *, state: str, office: str, election_cycle: int | None,
        race_stage: RaceStage | None, limit: int, offset: int,
    ) -> list[DashboardClaimRead]:
        latest = select(
            ClaimEvaluation.claim_id, ClaimEvaluation.verdict, ClaimEvaluation.confidence,
            ClaimEvaluation.rationale, ClaimEvaluation.citation_notes,
            func.row_number().over(partition_by=ClaimEvaluation.claim_id,
                                   order_by=(ClaimEvaluation.created_at.desc(), ClaimEvaluation.id.desc())).label('position'),
        ).subquery()
        query = select(
            Claim.id.label('claim_id'), Claim.claim_text, Claim.issue_tag, Claim.published_at,
            latest.c.verdict, latest.c.confidence, latest.c.rationale, latest.c.citation_notes,
            Candidate.id.label('candidate_id'), Candidate.name.label('candidate_name'),
            Candidate.party.label('candidate_party'), Candidate.office.label('candidate_office'),
            Candidate.state.label('candidate_state'), Candidate.election_cycle, Candidate.race_stage,
            Statement.source_url.label('statement_source_url'),
            Statement.published_at.label('statement_published_at'),
        ).select_from(Claim).join(Statement, Claim.statement_id == Statement.id).join(
            Candidate, Statement.candidate_id == Candidate.id,
        ).outerjoin(latest, and_(latest.c.claim_id == Claim.id, latest.c.position == 1)).where(
            Claim.is_published.is_(True), Claim.fact_checkable.is_(True),
            Claim.published_at.is_not(None), Candidate.state == state, Candidate.office == office,
        ).order_by(Claim.published_at.desc(), Claim.id).limit(limit).offset(offset)
        if election_cycle is not None:
            query = query.where(Candidate.election_cycle == election_cycle)
        if race_stage is not None:
            query = query.where(Candidate.race_stage == race_stage)
        rows = db.execute(query).mappings().all()
        sources_by_claim: dict[uuid.UUID, list[SourceRead]] = {}
        if rows:
            sources = db.execute(select(Source).where(
                Source.claim_id.in_([row['claim_id'] for row in rows]),
                or_(Source.source_origin != SourceOrigin.verification, Source.policy_flagged.is_(False)),
            ).order_by(Source.created_at, Source.id)).scalars().all()
            for source in sources:
                sources_by_claim.setdefault(source.claim_id, []).append(SourceRead.model_validate(source, from_attributes=True))
        claims: list[DashboardClaimRead] = []
        for row in rows:
            sources = sources_by_claim.get(row['claim_id'], [])
            rationale, rationale_warnings = _sanitize_public_rationale(row['rationale'] or '')
            warnings = _build_item_warnings(sources=sources, evidence_bundle=None) + rationale_warnings
            claims.append(DashboardClaimRead.model_validate({
                **dict(row), 'rationale': rationale, 'sources': sources, 'warnings': warnings,
            }))
        return claims
