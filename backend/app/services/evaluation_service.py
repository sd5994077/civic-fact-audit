import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.moderation_policy import find_moderation_violation
from app.models.entities import Candidate, Claim, ClaimEvaluation, Source, Statement
from app.models.enums import ClaimStatus, RaceStage, SourceClass, SourceOrigin, Verdict
from app.schemas.api import EvaluateClaimRequest
from app.services.admin_audit_service import AdminAuditService
from app.services.source_service import SourceService


def _build_review_row_warnings(*, primary_count: int, secondary_count: int) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    if primary_count == 0:
        warnings.append(
            {
                'code': 'missing_verification_primary',
                'severity': 'critical',
                'is_confidence_blocking': True,
                'message': 'No verification primary source is linked for this claim.',
            }
        )
    if secondary_count == 0:
        warnings.append(
            {
                'code': 'missing_verification_secondary',
                'severity': 'critical',
                'is_confidence_blocking': True,
                'message': 'No verification secondary source is linked for this claim.',
            }
        )
    return warnings


class EvaluationService:
    _PUBLISH_GATE_FACT_CHECKABLE = 'claim_not_fact_checkable'
    _PUBLISH_GATE_VERDICT = 'latest_verdict_must_be_supported_mixed_or_unsupported'
    _PUBLISH_GATE_RATIONALE = 'latest_rationale_required'
    _PUBLISH_GATE_CITATION_NOTES = 'latest_citation_notes_required'
    _PUBLISH_GATE_VERIFICATION_PRIMARY = 'verification_primary_source_required'
    _PUBLISH_GATE_VERIFICATION_SECONDARY = 'verification_secondary_source_required'
    _PUBLISH_GATE_MODERATION_POLICY = 'latest_evaluation_moderation_policy_violation'

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
        eligible = SourceService._eligible_for_verification_calculations_predicate()
        primary_count = func.sum(case((and_(eligible, Source.source_class == SourceClass.primary), 1), else_=0))
        secondary_count = func.sum(case((and_(eligible, Source.source_class == SourceClass.secondary), 1), else_=0))
        candidate_count = func.sum(case((and_(eligible, Source.source_origin == SourceOrigin.candidate), 1), else_=0))
        verification_count = func.sum(case((and_(eligible, Source.source_origin == SourceOrigin.verification), 1), else_=0))
        verification_primary_count = func.sum(
            case(
                (
                    and_(eligible, Source.source_origin == SourceOrigin.verification, Source.source_class == SourceClass.primary),
                    1,
                ),
                else_=0,
            )
        )
        verification_secondary_count = func.sum(
            case(
                (
                    and_(eligible, Source.source_origin == SourceOrigin.verification, Source.source_class == SourceClass.secondary),
                    1,
                ),
                else_=0,
            )
        )

        latest_eval_ranked = (
            select(
                ClaimEvaluation.claim_id.label('claim_id'),
                ClaimEvaluation.verdict.label('latest_verdict'),
                ClaimEvaluation.confidence.label('latest_confidence'),
                ClaimEvaluation.rationale.label('latest_rationale'),
                ClaimEvaluation.citation_notes.label('latest_citation_notes'),
                ClaimEvaluation.reviewer_id.label('latest_reviewer_id'),
                ClaimEvaluation.created_at.label('latest_evaluated_at'),
                func.row_number()
                .over(
                    partition_by=ClaimEvaluation.claim_id,
                    order_by=(ClaimEvaluation.created_at.desc(), ClaimEvaluation.id.desc()),
                )
                .label('row_num'),
            )
            .subquery()
        )

        query = (
            select(
                Claim.id.label('claim_id'),
                Claim.claim_text,
                Claim.issue_tag,
                Claim.status,
                Statement.source_url.label('statement_source_url'),
                Statement.published_at.label('statement_published_at'),
                Candidate.id.label('candidate_id'),
                Candidate.name.label('candidate_name'),
                Candidate.party,
                Candidate.office,
                Candidate.state,
                Candidate.election_cycle,
                Candidate.race_stage,
                Claim.fact_checkable.label('fact_checkable'),
                Claim.is_published.label('is_published'),
                Claim.published_at.label('claim_published_at'),
                Claim.published_by_reviewer_id.label('published_by_reviewer_id'),
                primary_count.label('primary_count'),
                secondary_count.label('secondary_count'),
                candidate_count.label('candidate_count'),
                verification_count.label('verification_count'),
                verification_primary_count.label('verification_primary_count'),
                verification_secondary_count.label('verification_secondary_count'),
                latest_eval_ranked.c.latest_verdict,
                latest_eval_ranked.c.latest_confidence,
                latest_eval_ranked.c.latest_rationale,
                latest_eval_ranked.c.latest_citation_notes,
                latest_eval_ranked.c.latest_reviewer_id,
                latest_eval_ranked.c.latest_evaluated_at,
            )
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .outerjoin(Source, Source.claim_id == Claim.id)
            .outerjoin(
                latest_eval_ranked,
                and_(
                    latest_eval_ranked.c.claim_id == Claim.id,
                    latest_eval_ranked.c.row_num == 1,
                ),
            )
            .where(EvaluationService._fact_checkable_predicate())
            .group_by(
                Claim.id,
                Claim.claim_text,
                Claim.issue_tag,
                Claim.status,
                Claim.fact_checkable,
                Claim.is_published,
                Claim.published_at,
                Claim.published_by_reviewer_id,
                Statement.source_url,
                Statement.published_at,
                Candidate.id,
                Candidate.name,
                Candidate.party,
                Candidate.office,
                Candidate.state,
                Candidate.election_cycle,
                Candidate.race_stage,
                latest_eval_ranked.c.latest_verdict,
                latest_eval_ranked.c.latest_confidence,
                latest_eval_ranked.c.latest_rationale,
                latest_eval_ranked.c.latest_citation_notes,
                latest_eval_ranked.c.latest_reviewer_id,
                latest_eval_ranked.c.latest_evaluated_at,
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
            query = query.having(verification_primary_count > 0, verification_secondary_count > 0)

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
                'statement_published_at': row['statement_published_at'],
                'candidate_id': row['candidate_id'],
                'candidate_name': row['candidate_name'],
                'candidate_party': row['party'],
                'candidate_office': row['office'],
                'candidate_state': row['state'],
                'election_cycle': row['election_cycle'],
                'race_stage': row['race_stage'],
                'fact_checkable': row['fact_checkable'],
                'is_published': row['is_published'],
                'published_at': row['claim_published_at'],
                'published_by_reviewer_id': row['published_by_reviewer_id'],
                'primary_source_count': int(row['primary_count']),
                'secondary_source_count': int(row['secondary_count']),
                'candidate_source_count': int(row['candidate_count']),
                'verification_source_count': int(row['verification_count']),
                'verification_primary_count': int(row['verification_primary_count']),
                'verification_secondary_count': int(row['verification_secondary_count']),
                'latest_verdict': row['latest_verdict'],
                'latest_confidence': row['latest_confidence'],
                'latest_rationale': row['latest_rationale'],
                'latest_citation_notes': row['latest_citation_notes'],
                'latest_reviewer_id': row['latest_reviewer_id'],
                'latest_evaluated_at': row['latest_evaluated_at'],
                'warnings': _build_review_row_warnings(
                    primary_count=int(row['verification_primary_count']),
                    secondary_count=int(row['verification_secondary_count']),
                ),
            }
            for row in rows
        ]

    @staticmethod
    def evaluate_claim(db: Session, claim_id: uuid.UUID, payload: EvaluateClaimRequest, reviewer_id: str) -> ClaimEvaluation:
        claim = EvaluationService._get_claim_for_evaluation_mutation(db, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)
        latest_evaluation = EvaluationService._latest_evaluation(db, claim_id, lock=True)
        rationale_text = payload.rationale.strip()
        rationale_violation = find_moderation_violation(rationale_text)
        if rationale_violation is not None:
            raise AppError(
                'moderation_policy_violation',
                'Rationale violates moderation policy boundaries.',
                status_code=422,
                details=rationale_violation.to_details(rejection_field='rationale'),
            )
        citation_text = (payload.citation_notes or '').strip()
        if citation_text:
            citation_violation = find_moderation_violation(citation_text)
            if citation_violation is not None:
                raise AppError(
                    'moderation_policy_violation',
                    'Citation notes violate moderation policy boundaries.',
                    status_code=422,
                    details=citation_violation.to_details(rejection_field='citation_notes'),
                )

        if payload.verdict in {Verdict.supported, Verdict.mixed, Verdict.unsupported}:
            if not SourceService.has_minimum_evidence(db, claim_id):
                raise AppError(
                    'minimum_evidence_missing',
                    'Claim must have at least one primary and one secondary source before this verdict.',
                    status_code=422,
                )

        normalized_applying_reviewer_id = EvaluationService._normalize_reviewer_id(reviewer_id)
        normalized_approval_reviewer_id = EvaluationService._normalize_reviewer_id(payload.approval_reviewer_id)
        if latest_evaluation is not None:
            if (
                normalized_approval_reviewer_id is None
                or normalized_applying_reviewer_id is None
                or normalized_approval_reviewer_id == normalized_applying_reviewer_id
            ):
                raise AppError(
                    'evaluation_overwrite_dual_control_required',
                    'Evaluation overwrites require different reviewers for approval and final mutation.',
                    status_code=409,
                    details={
                        'claim_id': str(claim_id),
                        'approval_reviewer_id': normalized_approval_reviewer_id,
                        'applying_reviewer_id': normalized_applying_reviewer_id,
                        'action': 'evaluate_overwrite',
                    },
                )

        evaluation = ClaimEvaluation(
            claim_id=claim.id,
            verdict=payload.verdict,
            confidence=payload.confidence,
            rationale=rationale_text,
            citation_notes=payload.citation_notes,
            reviewer_id=reviewer_id,
        )

        claim.status = ClaimStatus.reviewed
        db.add(evaluation)
        if latest_evaluation is not None and normalized_applying_reviewer_id is not None:
            before_payload = {
                'id': str(latest_evaluation.id),
                'claim_id': str(latest_evaluation.claim_id),
                'verdict': latest_evaluation.verdict.value,
                'confidence': latest_evaluation.confidence,
                'rationale': latest_evaluation.rationale,
                'citation_notes': latest_evaluation.citation_notes,
                'reviewer_id': latest_evaluation.reviewer_id,
                'created_at': latest_evaluation.created_at.isoformat(),
            }
            after_payload = {
                'claim_id': str(claim.id),
                'verdict': payload.verdict.value,
                'confidence': payload.confidence,
                'rationale': rationale_text,
                'citation_notes': payload.citation_notes,
                'reviewer_id': reviewer_id,
            }
            AdminAuditService.record_event(
                db,
                actor_reviewer_id=normalized_applying_reviewer_id,
                action='claim_evaluation_overwritten',
                entity_type='claim',
                entity_id=str(claim.id),
                before_payload=before_payload,
                after_payload=after_payload,
                metadata={
                    'approval_reviewer_id': normalized_approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'dual_control_enforced': True,
                },
                commit=False,
            )
        db.commit()
        db.refresh(evaluation)
        return evaluation

    @staticmethod
    def _latest_evaluation(db: Session, claim_id: uuid.UUID, *, lock: bool = False) -> ClaimEvaluation | None:
        return EvaluationService._latest_evaluation_for_publish(db, claim_id, lock=lock)

    @staticmethod
    def _latest_evaluation_for_publish(db: Session, claim_id: uuid.UUID, *, lock: bool) -> ClaimEvaluation | None:
        query = (
            select(ClaimEvaluation)
            .where(ClaimEvaluation.claim_id == claim_id)
            .order_by(ClaimEvaluation.created_at.desc(), ClaimEvaluation.id.desc())
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        return db.execute(query).scalars().first()

    @staticmethod
    def _get_claim_for_publish_mutation(db: Session, claim_id: uuid.UUID) -> Claim | None:
        if hasattr(db, 'execute'):
            return db.execute(select(Claim).where(Claim.id == claim_id).with_for_update()).scalars().first()
        return db.get(Claim, claim_id)

    @staticmethod
    def _get_claim_for_evaluation_mutation(db: Session, claim_id: uuid.UUID) -> Claim | None:
        if hasattr(db, 'execute'):
            return db.execute(select(Claim).where(Claim.id == claim_id).with_for_update()).scalars().first()
        return db.get(Claim, claim_id)

    @staticmethod
    def _publish_gate_failures(db: Session, claim: Claim, latest_eval: ClaimEvaluation | None) -> list[str]:
        failures: list[str] = []
        if not claim.fact_checkable:
            failures.append(EvaluationService._PUBLISH_GATE_FACT_CHECKABLE)
        if latest_eval is None or latest_eval.verdict not in {Verdict.supported, Verdict.mixed, Verdict.unsupported}:
            failures.append(EvaluationService._PUBLISH_GATE_VERDICT)
        if latest_eval is None or not latest_eval.rationale or not latest_eval.rationale.strip():
            failures.append(EvaluationService._PUBLISH_GATE_RATIONALE)
        if latest_eval is None or not latest_eval.citation_notes or not latest_eval.citation_notes.strip():
            failures.append(EvaluationService._PUBLISH_GATE_CITATION_NOTES)
        moderation_blocked = False
        if latest_eval is not None and latest_eval.rationale:
            moderation_blocked = find_moderation_violation(latest_eval.rationale.strip()) is not None
        if not moderation_blocked and latest_eval is not None and latest_eval.citation_notes:
            moderation_blocked = find_moderation_violation(latest_eval.citation_notes.strip()) is not None
        if moderation_blocked:
            failures.append(EvaluationService._PUBLISH_GATE_MODERATION_POLICY)
        if not SourceService.has_source_class(db, claim.id, SourceClass.primary, source_origin=SourceOrigin.verification):
            failures.append(EvaluationService._PUBLISH_GATE_VERIFICATION_PRIMARY)
        if not SourceService.has_source_class(db, claim.id, SourceClass.secondary, source_origin=SourceOrigin.verification):
            failures.append(EvaluationService._PUBLISH_GATE_VERIFICATION_SECONDARY)
        return list(dict.fromkeys(failures))

    @staticmethod
    def _publish_moderation_violations(latest_eval: ClaimEvaluation | None) -> list[dict[str, str]]:
        violations: list[dict[str, str]] = []
        if latest_eval is None:
            return violations
        if latest_eval.rationale and latest_eval.rationale.strip():
            rationale_violation = find_moderation_violation(latest_eval.rationale.strip())
            if rationale_violation is not None:
                violations.append(rationale_violation.to_details(rejection_field='rationale'))
        if latest_eval.citation_notes and latest_eval.citation_notes.strip():
            citation_violation = find_moderation_violation(latest_eval.citation_notes.strip())
            if citation_violation is not None:
                violations.append(citation_violation.to_details(rejection_field='citation_notes'))
        return violations

    @staticmethod
    def _claim_publish_state_payload(claim: Claim) -> dict[str, object]:
        status = getattr(claim, 'status', None)
        status_value = status.value if hasattr(status, 'value') else (str(status) if status is not None else None)
        published_at_raw = getattr(claim, 'published_at', None)
        published_at = published_at_raw.isoformat() if published_at_raw is not None else None
        return {
            'id': str(claim.id),
            'status': status_value,
            'is_published': bool(getattr(claim, 'is_published', False)),
            'published_at': published_at,
            'published_by_reviewer_id': getattr(claim, 'published_by_reviewer_id', None),
        }

    @staticmethod
    def _normalize_reviewer_id(reviewer_id: str | None) -> str | None:
        if reviewer_id is None:
            return None
        normalized = reviewer_id.strip().lower()
        if not normalized:
            return None
        return normalized

    @staticmethod
    def _resolve_publish_approval_reviewer_id(
        db: Session,
        claim_id: uuid.UUID,
        *,
        latest_eval: ClaimEvaluation | None = None,
        fallback_reviewer_id: str | None = None,
    ) -> str | None:
        evaluation = latest_eval if latest_eval is not None else EvaluationService._latest_evaluation(db, claim_id)
        reviewer_id = getattr(evaluation, 'reviewer_id', None) if evaluation is not None else fallback_reviewer_id
        return EvaluationService._normalize_reviewer_id(reviewer_id)

    @staticmethod
    def _enforce_publish_dual_control(
        db: Session,
        *,
        claim_id: uuid.UUID,
        applying_reviewer_id: str,
        action: str,
        latest_eval: ClaimEvaluation | None = None,
        fallback_approval_reviewer_id: str | None = None,
    ) -> tuple[str, str]:
        normalized_applying_reviewer_id = EvaluationService._normalize_reviewer_id(applying_reviewer_id)
        approval_reviewer_id = EvaluationService._resolve_publish_approval_reviewer_id(
            db,
            claim_id,
            latest_eval=latest_eval,
            fallback_reviewer_id=fallback_approval_reviewer_id,
        )
        if (
            normalized_applying_reviewer_id is None
            or approval_reviewer_id is None
            or approval_reviewer_id == normalized_applying_reviewer_id
        ):
            raise AppError(
                'publish_dual_control_required',
                'Publish and unpublish actions require different reviewers for approval and final mutation.',
                status_code=409,
                details={
                    'claim_id': str(claim_id),
                    'approval_reviewer_id': approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'action': action,
                },
            )
        return approval_reviewer_id, normalized_applying_reviewer_id

    @staticmethod
    def list_publish_queue(
        db: Session,
        *,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
        include_already_published: bool = False,
        only_gate_passed: bool = False,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        rows = EvaluationService.list_review_queue(
            db,
            state=state,
            office=office,
            election_cycle=election_cycle,
            race_stage=race_stage,
            require_minimum_evidence=False,
            limit=limit,
        )
        out: list[dict[str, object]] = []
        for row in rows:
            failures = EvaluationService._publish_gate_failures_from_review_row(row)
            gate_passed = len(failures) == 0
            if not include_already_published and bool(row.get('is_published')):
                continue
            if only_gate_passed and not gate_passed:
                continue
            out.append(
                {
                    'claim_id': row['claim_id'],
                    'claim_text': row['claim_text'],
                    'issue_tag': row['issue_tag'],
                    'candidate_name': row['candidate_name'],
                    'candidate_party': row['candidate_party'],
                    'statement_source_url': row['statement_source_url'],
                    'statement_published_at': row['statement_published_at'],
                    'latest_verdict': row['latest_verdict'],
                    'latest_confidence': row['latest_confidence'],
                    'latest_rationale': row['latest_rationale'],
                    'latest_citation_notes': row['latest_citation_notes'],
                    'latest_reviewer_id': row['latest_reviewer_id'],
                    'primary_source_count': row['primary_source_count'],
                    'secondary_source_count': row['secondary_source_count'],
                    'verification_primary_count': row['verification_primary_count'],
                    'verification_secondary_count': row['verification_secondary_count'],
                    'publish_gate_passed': gate_passed,
                    'publish_gate_failures': failures,
                    'is_published': bool(row.get('is_published', False)),
                    'published_at': row.get('claim_published_at'),
                    'published_by_reviewer_id': row.get('published_by_reviewer_id'),
                }
            )
        return out

    @staticmethod
    def _publish_gate_failures_from_review_row(row: dict[str, object]) -> list[str]:
        failures: list[str] = []
        if not bool(row.get('fact_checkable', True)):
            failures.append(EvaluationService._PUBLISH_GATE_FACT_CHECKABLE)
        latest_verdict = row.get('latest_verdict')
        if latest_verdict not in {Verdict.supported, Verdict.mixed, Verdict.unsupported}:
            failures.append(EvaluationService._PUBLISH_GATE_VERDICT)
        latest_rationale = str(row.get('latest_rationale') or '').strip()
        if not latest_rationale:
            failures.append(EvaluationService._PUBLISH_GATE_RATIONALE)
        latest_citation_notes = str(row.get('latest_citation_notes') or '').strip()
        if not latest_citation_notes:
            failures.append(EvaluationService._PUBLISH_GATE_CITATION_NOTES)
        moderation_blocked = False
        if latest_rationale:
            moderation_blocked = find_moderation_violation(latest_rationale) is not None
        if not moderation_blocked and latest_citation_notes:
            moderation_blocked = find_moderation_violation(latest_citation_notes) is not None
        if moderation_blocked:
            failures.append(EvaluationService._PUBLISH_GATE_MODERATION_POLICY)
        if int(row.get('verification_primary_count') or 0) <= 0:
            failures.append(EvaluationService._PUBLISH_GATE_VERIFICATION_PRIMARY)
        if int(row.get('verification_secondary_count') or 0) <= 0:
            failures.append(EvaluationService._PUBLISH_GATE_VERIFICATION_SECONDARY)
        return list(dict.fromkeys(failures))

    @staticmethod
    def publish_claim(db: Session, claim_id: uuid.UUID, *, approver_id: str) -> Claim:
        claim = EvaluationService._get_claim_for_publish_mutation(db, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)
        latest_eval = EvaluationService._latest_evaluation_for_publish(db, claim_id, lock=True)
        failures = EvaluationService._publish_gate_failures(db, claim, latest_eval)
        if failures:
            error_code = 'publish_gate_failed'
            error_message = 'Claim did not pass publish gate checks.'
            if EvaluationService._PUBLISH_GATE_MODERATION_POLICY in failures:
                error_code = 'publish_gate_moderation_failure'
                error_message = 'Claim publish blocked by moderation policy boundaries.'
            details: dict[str, object] = {'failed_checks': failures}
            moderation_violations = EvaluationService._publish_moderation_violations(latest_eval)
            if moderation_violations:
                details['moderation_violations'] = moderation_violations
            raise AppError(
                error_code,
                error_message,
                status_code=422,
                details=details,
            )
        approval_reviewer_id, applying_reviewer_id = EvaluationService._enforce_publish_dual_control(
            db,
            claim_id=claim_id,
            applying_reviewer_id=approver_id,
            action='publish',
            latest_eval=latest_eval,
        )
        before_payload = EvaluationService._claim_publish_state_payload(claim)
        claim.is_published = True
        claim.status = ClaimStatus.published
        claim.published_at = datetime.now(timezone.utc)
        claim.published_by_reviewer_id = applying_reviewer_id
        AdminAuditService.record_event(
            db,
            actor_reviewer_id=applying_reviewer_id,
            action='claim_published',
            entity_type='claim',
            entity_id=str(claim.id),
            before_payload=before_payload,
            after_payload=EvaluationService._claim_publish_state_payload(claim),
            metadata={
                'approval_reviewer_id': approval_reviewer_id,
                'applying_reviewer_id': applying_reviewer_id,
                'dual_control_enforced': True,
            },
            commit=False,
        )
        db.commit()
        db.refresh(claim)
        return claim

    @staticmethod
    def unpublish_claim(db: Session, claim_id: uuid.UUID, *, approver_id: str) -> Claim:
        claim = EvaluationService._get_claim_for_publish_mutation(db, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)
        latest_eval = EvaluationService._latest_evaluation_for_publish(db, claim_id, lock=True)
        approval_reviewer_id, applying_reviewer_id = EvaluationService._enforce_publish_dual_control(
            db,
            claim_id=claim_id,
            applying_reviewer_id=approver_id,
            action='unpublish',
            latest_eval=latest_eval,
            fallback_approval_reviewer_id=claim.published_by_reviewer_id,
        )
        before_payload = EvaluationService._claim_publish_state_payload(claim)
        claim.is_published = False
        claim.published_at = None
        claim.published_by_reviewer_id = None
        claim.status = ClaimStatus.reviewed
        AdminAuditService.record_event(
            db,
            actor_reviewer_id=applying_reviewer_id,
            action='claim_unpublished',
            entity_type='claim',
            entity_id=str(claim.id),
            before_payload=before_payload,
            after_payload=EvaluationService._claim_publish_state_payload(claim),
            metadata={
                'approval_reviewer_id': approval_reviewer_id,
                'applying_reviewer_id': applying_reviewer_id,
                'dual_control_enforced': True,
            },
            commit=False,
        )
        db.commit()
        db.refresh(claim)
        return claim
