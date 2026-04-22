import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.entities import Candidate, Claim, ClaimEvaluation, IssueFrame, Source, Statement
from app.models.enums import RaceStage, SourceClass, Verdict
from app.services.evidence_bundle_service import EvidenceBundleService
from app.schemas.api import (
    CandidateRead,
    ClaimEvidenceBundleRead,
    CompareClaimItem,
    CompareIssue,
    CompareIssueFramePolicy,
    CompareRaceMeta,
    CompareResponse,
    SourceRead,
)


@dataclass(frozen=True)
class _CompareRow:
    candidate_id: uuid.UUID
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    issue_frame_key: str | None
    comparison_question: str | None
    allowed_candidate_source_classes: list[SourceClass] | None
    allowed_verification_source_classes: list[SourceClass] | None
    statement_source_url: str
    statement_published_at: datetime
    verdict: Verdict
    confidence: float
    rationale: str
    citation_notes: str | None
    evidence_bundle: ClaimEvidenceBundleRead | None


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


def _build_issue_frame_policy_by_key(rows: list[_CompareRow]) -> dict[str, CompareIssueFramePolicy]:
    policies: dict[str, CompareIssueFramePolicy] = {}
    for row in rows:
        if not row.issue_frame_key or row.issue_frame_key in policies:
            continue
        policies[row.issue_frame_key] = CompareIssueFramePolicy(
            frame_key=row.issue_frame_key,
            comparison_question=row.comparison_question,
            allowed_candidate_source_classes=list(row.allowed_candidate_source_classes or []),
            allowed_verification_source_classes=list(row.allowed_verification_source_classes or []),
        )
    return policies


def _resolve_issue_frame_policy(
    issue_rows: list[_CompareRow],
    frame_policies_by_key: dict[str, CompareIssueFramePolicy],
) -> CompareIssueFramePolicy | None:
    if not issue_rows:
        return None
    if any(row.issue_frame_key is None for row in issue_rows):
        return None
    frame_keys = {row.issue_frame_key for row in issue_rows if row.issue_frame_key}
    if len(frame_keys) != 1:
        return None
    frame_key = next(iter(frame_keys))
    return frame_policies_by_key.get(frame_key)


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
                    IssueFrame.frame_key.label('issue_frame_key'),
                    IssueFrame.title.label('issue_frame_title'),
                    IssueFrame.comparison_question,
                    IssueFrame.allowed_candidate_source_classes,
                    IssueFrame.allowed_verification_source_classes,
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
                issue_frame_key=row.issue_frame_key,
                comparison_question=row.comparison_question,
                allowed_candidate_source_classes=row.allowed_candidate_source_classes,
                allowed_verification_source_classes=row.allowed_verification_source_classes,
                statement_source_url=row.source_url,
                statement_published_at=row.published_at,
                verdict=row.verdict,
                confidence=row.confidence,
                rationale=row.rationale,
                citation_notes=row.citation_notes,
                evidence_bundle=None,
            )
            for row in rows
        ]

        top_issue_tags = _select_top_issue_tags(compare_rows, limit_issues=limit_issues)
        representatives = _pick_representatives(compare_rows)
        frame_policies_by_key = _build_issue_frame_policy_by_key(compare_rows)

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
        bundles_by_claim = EvidenceBundleService.get_bundles_for_claim_ids(db, rep_claim_ids)

        issues: list[CompareIssue] = []
        for tag in top_issue_tags:
            issue_rows: list[_CompareRow] = []
            items: list[CompareClaimItem] = []
            for cand in candidates:
                rep = representatives.get((cand.id, tag))
                if rep is None:
                    continue
                issue_rows.append(rep)
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
                        evidence_bundle=bundles_by_claim.get(rep.claim_id),
                    )
                )
            issues.append(
                CompareIssue(
                    issue_tag=tag,
                    frame_policy=_resolve_issue_frame_policy(issue_rows, frame_policies_by_key),
                    items=items,
                )
            )

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
