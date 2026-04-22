import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Candidate, Claim, ClaimEvaluation, IssueFrame, Source, Statement
from app.models.enums import RaceStage, Verdict
from app.schemas.api import CandidateRead, CompareClaimItem, CompareIssue, CompareRaceMeta, CompareResponse, SourceRead


@dataclass(frozen=True)
class _CompareRow:
    candidate_id: uuid.UUID
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    statement_source_url: str
    statement_published_at: datetime
    verdict: Verdict
    confidence: float
    rationale: str
    citation_notes: str | None


def _resolve_issue_tag(issue_frame_title: str | None, issue_tag: str | None) -> str | None:
    if issue_frame_title:
        return issue_frame_title.strip() or None
    if issue_tag:
        return issue_tag.strip() or None
    return None


def _select_top_issue_tags(rows: list[_CompareRow], limit_issues: int) -> list[str]:
    counts: dict[str, int] = {}
    for row in rows:
        if not row.issue_tag:
            continue
        counts[row.issue_tag] = counts.get(row.issue_tag, 0) + 1

    # Stable ordering: highest frequency, then alpha.
    return [tag for tag, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:limit_issues]]


def _pick_representatives(rows: list[_CompareRow]) -> dict[tuple[uuid.UUID, str], _CompareRow]:
    """
    Pick the most recent claim per (candidate, issue_tag).
    Assumes rows are ordered by statement_published_at desc.
    """
    reps: dict[tuple[uuid.UUID, str], _CompareRow] = {}
    for row in rows:
        if not row.issue_tag:
            continue
        key = (row.candidate_id, row.issue_tag)
        if key not in reps:
            reps[key] = row
    return reps


class ComparisonService:
    @staticmethod
    def _fact_checkable_predicate():
        return Claim.fact_checkable.is_(True)

    @staticmethod
    def _candidate_filters(
        *,
        state: str,
        office: str,
        election_cycle: int | None,
        race_stage: RaceStage | None,
    ) -> list[object]:
        filters: list[object] = [
            func.lower(Candidate.state) == state.strip().lower(),
            func.lower(Candidate.office) == office.strip().lower(),
        ]
        if election_cycle is not None:
            filters.append(Candidate.election_cycle == election_cycle)
        if race_stage is not None:
            filters.append(Candidate.race_stage == race_stage)
        return filters

    @staticmethod
    def compare_office_state(
        db: Session,
        state: str,
        office: str,
        election_cycle: int | None,
        race_stage: RaceStage | None,
        limit_issues: int,
        window_start: datetime,
        window_end: datetime,
    ) -> CompareResponse:
        if window_end < window_start:
            raise AppError('invalid_window', 'window_end must be greater than or equal to window_start.', status_code=422)

        candidates = (
            db.execute(
                select(Candidate)
                .where(
                    *ComparisonService._candidate_filters(
                        state=state,
                        office=office,
                        election_cycle=election_cycle,
                        race_stage=race_stage,
                    )
                )
                .order_by(Candidate.name.asc())
            )
            .scalars()
            .all()
        )
        if len(candidates) < 2:
            raise AppError(
                'insufficient_candidates',
                'Need at least two candidates for a comparison in the requested state/office.',
                status_code=404,
                details={
                    'state': state,
                    'office': office,
                    'election_cycle': election_cycle,
                    'race_stage': race_stage,
                    'found': len(candidates),
                },
            )

        candidate_ids = [c.id for c in candidates]

        claim_latest_eval = (
            select(ClaimEvaluation.claim_id, func.max(ClaimEvaluation.created_at).label('latest_created_at'))
            .group_by(ClaimEvaluation.claim_id)
            .subquery()
        )

        rows = (
            db.execute(
                select(
                    Statement.candidate_id,
                    Claim.id,
                    Claim.claim_text,
                    IssueFrame.title.label('issue_frame_title'),
                    Claim.issue_tag,
                    Statement.source_url,
                    Statement.published_at,
                    ClaimEvaluation.verdict,
                    ClaimEvaluation.confidence,
                    ClaimEvaluation.rationale,
                    ClaimEvaluation.citation_notes,
                )
                .join(Claim, Claim.statement_id == Statement.id)
                .join(claim_latest_eval, claim_latest_eval.c.claim_id == Claim.id)
                .outerjoin(IssueFrame, IssueFrame.id == Claim.issue_frame_id)
                .join(
                    ClaimEvaluation,
                    and_(
                        ClaimEvaluation.claim_id == claim_latest_eval.c.claim_id,
                        ClaimEvaluation.created_at == claim_latest_eval.c.latest_created_at,
                    ),
                )
                .where(
                    Statement.candidate_id.in_(candidate_ids),
                    Statement.published_at >= window_start,
                    Statement.published_at <= window_end,
                    ComparisonService._fact_checkable_predicate(),
                )
                .order_by(Statement.published_at.desc())
            )
            .all()
        )

        compare_rows = [
            _CompareRow(
                candidate_id=row.candidate_id,
                claim_id=row.id,
                claim_text=row.claim_text,
                issue_tag=_resolve_issue_tag(row.issue_frame_title, row.issue_tag),
                statement_source_url=row.source_url,
                statement_published_at=row.published_at,
                verdict=row.verdict,
                confidence=row.confidence,
                rationale=row.rationale,
                citation_notes=row.citation_notes,
            )
            for row in rows
        ]

        top_issue_tags = _select_top_issue_tags(compare_rows, limit_issues=limit_issues)
        representatives = _pick_representatives(compare_rows)

        rep_claim_ids: list[uuid.UUID] = []
        for tag in top_issue_tags:
            for cand in candidates:
                rep = representatives.get((cand.id, tag))
                if rep is not None:
                    rep_claim_ids.append(rep.claim_id)

        sources_by_claim: dict[uuid.UUID, list[SourceRead]] = {}
        if rep_claim_ids:
            src_rows = (
                db.execute(
                    select(Source)
                    .where(Source.claim_id.in_(rep_claim_ids))
                    .order_by(
                        Source.claim_id.asc(),
                        Source.source_origin.asc(),
                        Source.source_class.asc(),
                        Source.quality_score.desc(),
                    )
                )
                .scalars()
                .all()
            )
            for src in src_rows:
                sources_by_claim.setdefault(src.claim_id, []).append(SourceRead.model_validate(src, from_attributes=True))

        issues: list[CompareIssue] = []
        for tag in top_issue_tags:
            items: list[CompareClaimItem] = []
            for cand in candidates:
                rep = representatives.get((cand.id, tag))
                if rep is None:
                    continue
                items.append(
                    CompareClaimItem(
                        candidate_id=rep.candidate_id,
                        claim_id=rep.claim_id,
                        claim_text=rep.claim_text,
                        issue_tag=rep.issue_tag,
                        statement_source_url=rep.statement_source_url,
                        statement_published_at=rep.statement_published_at,
                        verdict=rep.verdict,
                        confidence=rep.confidence,
                        rationale=rep.rationale,
                        citation_notes=rep.citation_notes,
                        sources=sources_by_claim.get(rep.claim_id, []),
                    )
                )
            issues.append(CompareIssue(issue_tag=tag, items=items))

        meta = CompareRaceMeta(
            state=state,
            office=office,
            election_cycle=election_cycle,
            race_stage=race_stage,
            as_of=datetime.now(timezone.utc),
            disclaimer=(
                'This comparison is evidence-traceable, not an endorsement. '
                'Each verdict is only as strong as its linked sources; items labeled insufficient indicate missing evidence.'
            ),
        )

        return CompareResponse(
            race=meta,
            candidates=[CandidateRead.model_validate(c, from_attributes=True) for c in candidates],
            issues=issues,
        )
