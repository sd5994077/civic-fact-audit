import uuid
import json

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.source_admission_policy import (
    SourcePolicyRuleMatch,
    find_partisan_rule_match,
    get_source_admission_policy,
    is_social_url,
)
from app.models.entities import Candidate, Claim, Source, Statement
from app.models.enums import RaceStage, SourceClass, SourceOrigin
from app.models.enums import ClaimStatus as ClaimStatusEnum
from app.schemas.api import AddSourceRequest, BulkSourceAttachItem
from app.services.admin_audit_service import AdminAuditService
from app.services.auth_service import AuthService
from app.services.evidence_bundle_service import EvidenceBundleService


class SourceService:
    @staticmethod
    def _normalize_reviewer_id(reviewer_id: str | None) -> str | None:
        return AuthService.normalize_reviewer_id(reviewer_id)

    @staticmethod
    def _build_bulk_operation_id(
        *,
        approval_reviewer_id: str | None,
        applying_reviewer_id: str | None,
        items: list[BulkSourceAttachItem],
    ) -> str:
        canonical_items = sorted(
            (
                {
                    'claim_id': str(item.claim_id),
                    'url': str(item.url),
                    'source_class': item.source_class.value,
                    'source_origin': item.source_origin.value,
                    'publisher': item.publisher,
                    'quality_score': item.quality_score,
                    'is_direct_candidate_quote': item.is_direct_candidate_quote,
                }
                for item in items
            ),
            key=lambda entry: (
                entry['claim_id'],
                entry['url'],
                entry['source_class'],
                entry['source_origin'],
                entry['publisher'] or '',
                str(entry['quality_score']),
                str(entry['is_direct_candidate_quote']),
            ),
        )
        payload = {
            'approval_reviewer_id': SourceService._normalize_reviewer_id(approval_reviewer_id),
            'applying_reviewer_id': SourceService._normalize_reviewer_id(applying_reviewer_id),
            'items': canonical_items,
        }
        canonical = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, canonical))

    @staticmethod
    def _fact_checkable_predicate():
        return Claim.fact_checkable.is_(True)

    @staticmethod
    def _eligible_for_verification_calculations_predicate():
        return or_(Source.source_origin != SourceOrigin.verification, Source.policy_flagged.is_(False))

    @staticmethod
    def _eligible_verification_source_predicate():
        return and_(Source.source_origin == SourceOrigin.verification, Source.policy_flagged.is_(False))

    @staticmethod
    def get_partisan_match(*, publisher: str | None, url: str) -> SourcePolicyRuleMatch | None:
        return find_partisan_rule_match(publisher=publisher, url=url)

    @staticmethod
    def validate_source_admission(payload: AddSourceRequest) -> None:
        matched_rule = SourceService.get_partisan_match(publisher=payload.publisher, url=str(payload.url))
        if matched_rule is None:
            return
        policy = get_source_admission_policy()
        matched_rule_payload = {
            'field': matched_rule.field,
            'match_type': matched_rule.match_type,
            'pattern': matched_rule.pattern,
            'value': matched_rule.value,
        }
        if payload.source_origin == SourceOrigin.verification:
            raise AppError(
                'source_admission_policy_violation',
                'Partisan/advocacy sources cannot be added as verification evidence.',
                status_code=422,
                details={
                    'policy_version': policy.version,
                    'rejection_field': 'source_origin',
                    'matched_rule': matched_rule_payload,
                    'source_origin': payload.source_origin.value,
                },
            )
        if not payload.is_direct_candidate_quote:
            raise AppError(
                'source_admission_policy_violation',
                'Candidate-origin partisan sources require is_direct_candidate_quote=true.',
                status_code=422,
                details={
                    'policy_version': policy.version,
                    'rejection_field': 'is_direct_candidate_quote',
                    'matched_rule': matched_rule_payload,
                    'is_direct_candidate_quote': payload.is_direct_candidate_quote,
                },
            )
        if not is_social_url(str(payload.url)):
            raise AppError(
                'source_admission_policy_violation',
                'Direct-candidate-quote exception only applies to official social media URLs.',
                status_code=422,
                details={
                    'policy_version': policy.version,
                    'rejection_field': 'url',
                    'matched_rule': matched_rule_payload,
                    'allowed_social_domains': list(policy.social_domains),
                },
            )

    @staticmethod
    def _bulk_status_from_error_code(error_code: str) -> str:
        if error_code == 'duplicate_source':
            return 'duplicate'
        if error_code == 'claim_not_found':
            return 'claim_not_found'
        if error_code == 'source_admission_policy_violation':
            return 'policy_violation'
        return 'error'

    @staticmethod
    def _build_evidence_queue_query(
        *,
        state: str | None,
        office: str | None,
        election_cycle: int | None,
        race_stage: RaceStage | None,
        include_only_missing: bool,
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
                candidate_count.label('candidate_count'),
                verification_count.label('verification_count'),
                verification_primary_count.label('verification_primary_count'),
                verification_secondary_count.label('verification_secondary_count'),
            )
            .join(Statement, Statement.id == Claim.statement_id)
            .join(Candidate, Candidate.id == Statement.candidate_id)
            .outerjoin(Source, Source.claim_id == Claim.id)
            .where(SourceService._fact_checkable_predicate())
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

        if include_only_missing:
            query = query.having(or_(verification_primary_count == 0, verification_secondary_count == 0))

        return query

    @staticmethod
    def add_source(db: Session, claim_id: uuid.UUID, payload: AddSourceRequest, *, commit: bool = True) -> list[Source]:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppError('claim_not_found', 'Claim does not exist.', status_code=404)
        SourceService.validate_source_admission(payload)

        source = Source(
            claim_id=claim.id,
            url=str(payload.url),
            source_class=payload.source_class,
            source_origin=payload.source_origin,
            publisher=payload.publisher,
            quality_score=payload.quality_score,
        )
        db.add(source)
        try:
            db.flush()
            # Keep derived evidence bundles current for compare/public reads
            # inside the same transaction as the source write.
            EvidenceBundleService.sync_claim_bundle(db, claim.id, commit=False)
            if commit:
                db.commit()
            else:
                db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise AppError(
                'duplicate_source',
                'This source URL is already attached to the claim.',
                status_code=409,
            ) from exc
        except AppError:
            db.rollback()
            raise

        sources = db.scalars(select(Source).where(Source.claim_id == claim.id).order_by(Source.created_at.asc())).all()
        return list(sources)

    @staticmethod
    def has_minimum_evidence(db: Session, claim_id: uuid.UUID) -> bool:
        rows = db.execute(
            select(Source.source_class).where(Source.claim_id == claim_id, SourceService._eligible_verification_source_predicate())
        ).all()
        source_classes = {row[0] for row in rows}
        return SourceClass.primary in source_classes and SourceClass.secondary in source_classes

    @staticmethod
    def has_source_class(
        db: Session,
        claim_id: uuid.UUID,
        source_class: SourceClass,
        *,
        source_origin: SourceOrigin | None = None,
    ) -> bool:
        query = select(Source.id).where(Source.claim_id == claim_id, Source.source_class == source_class)
        if source_origin is not None:
            query = query.where(Source.source_origin == source_origin)
            if source_origin == SourceOrigin.verification:
                query = query.where(Source.policy_flagged.is_(False))
        return db.execute(query.limit(1)).scalars().first() is not None

    @staticmethod
    def list_evidence_queue(
        db: Session,
        *,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
        include_only_missing: bool = True,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        rows = (
            db.execute(
                SourceService._build_evidence_queue_query(
                    state=state,
                    office=office,
                    election_cycle=election_cycle,
                    race_stage=race_stage,
                    include_only_missing=include_only_missing,
                ).limit(limit)
            )
            .mappings()
            .all()
        )

        items: list[dict[str, object]] = []
        for row in rows:
            missing: list[SourceClass] = []
            if int(row['verification_primary_count']) == 0:
                missing.append(SourceClass.primary)
            if int(row['verification_secondary_count']) == 0:
                missing.append(SourceClass.secondary)
            items.append(
                {
                    'claim_id': row['claim_id'],
                    'claim_text': row['claim_text'],
                    'issue_tag': row['issue_tag'],
                    'status': ClaimStatusEnum(row['status']),
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
                    'candidate_source_count': int(row['candidate_count']),
                    'verification_source_count': int(row['verification_count']),
                    'missing_source_classes': missing,
                }
            )
        return items

    @staticmethod
    def attach_sources_bulk(
        db: Session,
        *,
        approval_reviewer_id: str | None,
        applying_reviewer_id: str,
        items: list[BulkSourceAttachItem],
    ) -> dict[str, object]:
        normalized_approval_reviewer_id = AuthService.resolve_active_reviewer_id(
            db,
            approval_reviewer_id,
            allowed_roles={'reviewer', 'admin'},
        )
        normalized_applying_reviewer_id = AuthService.resolve_active_reviewer_id(
            db,
            applying_reviewer_id,
            allowed_roles={'reviewer', 'admin'},
        )
        bulk_operation_id = SourceService._build_bulk_operation_id(
            approval_reviewer_id=normalized_approval_reviewer_id,
            applying_reviewer_id=normalized_applying_reviewer_id,
            items=items,
        )
        has_verification_items = any(item.source_origin == SourceOrigin.verification for item in items)
        has_candidate_items = any(item.source_origin == SourceOrigin.candidate for item in items)
        dual_control_valid = (
            normalized_approval_reviewer_id is not None
            and normalized_applying_reviewer_id is not None
            and normalized_approval_reviewer_id != normalized_applying_reviewer_id
        )
        if has_verification_items and (
            not dual_control_valid
            and not has_candidate_items
        ):
            raise AppError(
                'bulk_attach_dual_control_required',
                'Verification-source bulk attach operations require different reviewers for approval and final mutation.',
                status_code=409,
                details={
                    'bulk_operation_id': bulk_operation_id,
                    'approval_reviewer_id': normalized_approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'action': 'bulk_attach_verification_sources',
                },
            )

        attached = 0
        failed = 0
        results: list[dict[str, object]] = []
        status_counts: dict[str, int] = {
            'attached': 0,
            'duplicate': 0,
            'policy_violation': 0,
            'claim_not_found': 0,
            'error': 0,
        }

        for item in items:
            if item.source_origin == SourceOrigin.verification and not dual_control_valid:
                failed += 1
                status_counts['error'] += 1
                results.append(
                    {
                        'claim_id': item.claim_id,
                        'url': str(item.url),
                        'source_class': item.source_class,
                        'source_origin': item.source_origin,
                        'status': 'error',
                        'error': {
                            'code': 'bulk_attach_dual_control_required',
                            'message': 'Verification-source bulk attach operations require different reviewers for approval and final mutation.',
                            'details': {
                                'bulk_operation_id': bulk_operation_id,
                                'approval_reviewer_id': normalized_approval_reviewer_id,
                                'applying_reviewer_id': normalized_applying_reviewer_id,
                                'action': 'bulk_attach_verification_sources',
                            },
                        },
                    }
                )
                continue
            payload = AddSourceRequest(
                url=item.url,
                source_class=item.source_class,
                source_origin=item.source_origin,
                publisher=item.publisher,
                quality_score=item.quality_score,
                is_direct_candidate_quote=item.is_direct_candidate_quote,
            )
            try:
                SourceService.add_source(db, item.claim_id, payload)
                attached += 1
                status_counts['attached'] += 1
                results.append(
                    {
                        'claim_id': item.claim_id,
                        'url': str(item.url),
                        'source_class': item.source_class,
                        'source_origin': item.source_origin,
                        'status': 'attached',
                        'error': None,
                    }
                )
            except AppError as exc:
                failed += 1
                status = SourceService._bulk_status_from_error_code(exc.code)
                if status not in status_counts:
                    status = 'error'
                status_counts[status] += 1
                results.append(
                    {
                        'claim_id': item.claim_id,
                        'url': str(item.url),
                        'source_class': item.source_class,
                        'source_origin': item.source_origin,
                        'status': status,
                        'error': {'code': exc.code, 'message': exc.message, 'details': exc.details},
                    }
                )

        if normalized_applying_reviewer_id is not None:
            AdminAuditService.record_event(
                db,
                actor_reviewer_id=normalized_applying_reviewer_id,
                action='bulk_sources_attached',
                entity_type='bulk_source_attach',
                entity_id=bulk_operation_id,
                metadata={
                    'bulk_operation_id': bulk_operation_id,
                    'total': len(items),
                    'attached': attached,
                    'failed': failed,
                    'status_counts': status_counts,
                    'approval_reviewer_id': normalized_approval_reviewer_id,
                    'applying_reviewer_id': normalized_applying_reviewer_id,
                    'dual_control_enforced': has_verification_items,
                },
                commit=False,
            )
            db.commit()

        return {
            'bulk_operation_id': bulk_operation_id,
            'total': len(items),
            'attached': attached,
            'failed': failed,
            'results': results,
        }
