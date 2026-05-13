from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import Candidate, Claim, Statement
from app.models.enums import ClaimStatus, RaceStage


class SearchService:
    @staticmethod
    def search_claims(
        db: Session,
        *,
        q: str,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
        status: ClaimStatus | None = None,
        fact_checkable: bool | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Full-text + substring search across claim text, issue tag, and candidate name.

        Returns rows ordered by full-text relevance rank descending then by
        claim creation date descending.  Returns an empty list when the query
        is blank or whitespace-only.
        """
        q = q.strip()
        if not q:
            return []

        ts_query = func.plainto_tsquery('english', q)
        ts_rank = func.ts_rank(func.to_tsvector('english', Claim.claim_text), ts_query)

        stmt = (
            select(
                Claim.id.label('claim_id'),
                Claim.claim_text,
                Claim.issue_tag,
                Claim.status,
                Claim.fact_checkable,
                Claim.is_published,
                Candidate.id.label('candidate_id'),
                Candidate.name.label('candidate_name'),
                Candidate.party.label('candidate_party'),
                Candidate.office.label('candidate_office'),
                Candidate.state.label('candidate_state'),
                Candidate.election_cycle,
                Candidate.race_stage,
                ts_rank.label('rank'),
            )
            .select_from(Claim)
            .join(Statement, Claim.statement_id == Statement.id)
            .join(Candidate, Statement.candidate_id == Candidate.id)
            .where(
                or_(
                    func.to_tsvector('english', Claim.claim_text).op('@@')(ts_query),
                    func.coalesce(Claim.issue_tag, '').ilike(f'%{q}%'),
                    Candidate.name.ilike(f'%{q}%'),
                )
            )
            .order_by(ts_rank.desc(), Claim.created_at.desc())
            .limit(limit)
        )

        if state is not None:
            stmt = stmt.where(Candidate.state == state)
        if office is not None:
            stmt = stmt.where(Candidate.office == office)
        if election_cycle is not None:
            stmt = stmt.where(Candidate.election_cycle == election_cycle)
        if race_stage is not None:
            stmt = stmt.where(Candidate.race_stage == race_stage)
        if status is not None:
            stmt = stmt.where(Claim.status == status)
        if fact_checkable is not None:
            stmt = stmt.where(Claim.fact_checkable == fact_checkable)

        rows = db.execute(stmt).mappings().all()
        return [dict(row) for row in rows]
