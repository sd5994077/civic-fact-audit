from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.enums import RaceStage, Verdict
from app.services.evaluation_service import EvaluationService


class ClaimWorkbenchService:
    STATE_NEEDS_EVIDENCE = 'Needs Evidence'
    STATE_NEEDS_REVIEW = 'Needs Review'
    STATE_NEEDS_SECOND_REVIEWER = 'Needs Second Reviewer'
    STATE_READY_TO_PUBLISH = 'Ready to Publish'
    STATE_PUBLISHED = 'Published'
    STATE_INSUFFICIENT_EVIDENCE = 'Insufficient Evidence'

    SECOND_REVIEWER_ACTION_PUBLISH_HANDOFF = 'publish_handoff'
    SECOND_REVIEWER_ACTION_OVERWRITE_HANDOFF = 'overwrite_handoff'

    _PUBLISHABLE_VERDICTS = {Verdict.supported, Verdict.mixed, Verdict.unsupported}

    @staticmethod
    def _derive_second_reviewer_action(
        *,
        is_published: bool,
        publish_gate_passed: bool,
        latest_verdict: Verdict | None,
        latest_reviewer_id: str | None,
        actor_reviewer_id: str | None,
    ) -> str | None:
        normalized_latest_reviewer_id = EvaluationService._normalize_reviewer_id(latest_reviewer_id)
        dual_control_ready_for_publish = (
            normalized_latest_reviewer_id is not None
            and actor_reviewer_id is not None
            and normalized_latest_reviewer_id != actor_reviewer_id
        )

        if not is_published and publish_gate_passed and not dual_control_ready_for_publish:
            return ClaimWorkbenchService.SECOND_REVIEWER_ACTION_PUBLISH_HANDOFF
        if not publish_gate_passed and latest_verdict is not None and latest_verdict != Verdict.insufficient:
            return ClaimWorkbenchService.SECOND_REVIEWER_ACTION_OVERWRITE_HANDOFF
        return None

    @staticmethod
    def _derive_state(
        *,
        is_published: bool,
        publish_gate_passed: bool,
        second_reviewer_action: str | None,
        latest_verdict: Verdict | None,
        has_minimum_verification_evidence: bool,
        has_latest_evaluation: bool,
    ) -> str:
        if is_published:
            return ClaimWorkbenchService.STATE_PUBLISHED
        if second_reviewer_action is not None:
            return ClaimWorkbenchService.STATE_NEEDS_SECOND_REVIEWER
        if publish_gate_passed:
            return ClaimWorkbenchService.STATE_READY_TO_PUBLISH
        if latest_verdict == Verdict.insufficient:
            return ClaimWorkbenchService.STATE_INSUFFICIENT_EVIDENCE
        if has_minimum_verification_evidence and not has_latest_evaluation:
            return ClaimWorkbenchService.STATE_NEEDS_REVIEW
        return ClaimWorkbenchService.STATE_NEEDS_EVIDENCE

    @staticmethod
    def _build_checklist(
        *,
        fact_checkable: bool,
        latest_verdict: Verdict | None,
        latest_rationale: str | None,
        latest_citation_notes: str | None,
        verification_primary_count: int,
        verification_secondary_count: int,
        moderation_clear: bool,
        dual_control_ready_for_publish: bool,
        dual_control_blocking: bool,
    ) -> list[dict[str, object]]:
        return [
            {'code': 'fact_checkable', 'label': 'Claim is fact-checkable', 'passed': fact_checkable, 'blocking': True},
            {
                'code': 'latest_verdict_publishable',
                'label': 'Latest verdict is publishable (supported/mixed/unsupported)',
                'passed': latest_verdict in ClaimWorkbenchService._PUBLISHABLE_VERDICTS,
                'blocking': True,
            },
            {
                'code': 'latest_rationale_present',
                'label': 'Latest rationale is present',
                'passed': bool((latest_rationale or '').strip()),
                'blocking': True,
            },
            {
                'code': 'latest_citation_notes_present',
                'label': 'Latest citation notes are present',
                'passed': bool((latest_citation_notes or '').strip()),
                'blocking': True,
            },
            {
                'code': 'verification_primary_present',
                'label': 'Verification primary source is attached',
                'passed': verification_primary_count > 0,
                'blocking': True,
            },
            {
                'code': 'verification_secondary_present',
                'label': 'Verification secondary source is attached',
                'passed': verification_secondary_count > 0,
                'blocking': True,
            },
            {
                'code': 'moderation_clear',
                'label': 'Latest evaluation is moderation-policy clean',
                'passed': moderation_clear,
                'blocking': True,
            },
            {
                'code': 'dual_control_ready_for_publish',
                'label': 'Publish handoff has a different applying reviewer',
                'passed': dual_control_ready_for_publish,
                'blocking': dual_control_blocking,
            },
        ]

    @staticmethod
    def list_workbench(
        db: Session,
        *,
        actor_reviewer_id: str,
        state: str | None = None,
        office: str | None = None,
        election_cycle: int | None = None,
        race_stage: RaceStage | None = None,
        include_non_fact_checkable: bool = False,
        workbench_state: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        rows = EvaluationService.list_review_queue(
            db,
            state=state,
            office=office,
            election_cycle=election_cycle,
            race_stage=race_stage,
            require_minimum_evidence=False,
            include_non_fact_checkable=include_non_fact_checkable,
            exclude_published=False,
            limit=limit,
        )
        normalized_actor_reviewer_id = EvaluationService._normalize_reviewer_id(actor_reviewer_id)

        items: list[dict[str, object]] = []
        for row in rows:
            publish_gate_failures = EvaluationService._publish_gate_failures_from_review_row(row)
            publish_gate_passed = len(publish_gate_failures) == 0
            latest_verdict = row.get('latest_verdict')
            verification_primary_count = int(row.get('verification_primary_count') or 0)
            verification_secondary_count = int(row.get('verification_secondary_count') or 0)
            has_minimum_verification_evidence = verification_primary_count > 0 and verification_secondary_count > 0
            latest_reviewer_id = row.get('latest_reviewer_id')
            normalized_latest_reviewer_id = EvaluationService._normalize_reviewer_id(latest_reviewer_id)
            dual_control_ready_for_publish = (
                normalized_latest_reviewer_id is not None
                and normalized_actor_reviewer_id is not None
                and normalized_latest_reviewer_id != normalized_actor_reviewer_id
            )
            second_reviewer_action = ClaimWorkbenchService._derive_second_reviewer_action(
                is_published=bool(row.get('is_published', False)),
                publish_gate_passed=publish_gate_passed,
                latest_verdict=latest_verdict,
                latest_reviewer_id=latest_reviewer_id,
                actor_reviewer_id=normalized_actor_reviewer_id,
            )
            workbench_state_value = ClaimWorkbenchService._derive_state(
                is_published=bool(row.get('is_published', False)),
                publish_gate_passed=publish_gate_passed,
                second_reviewer_action=second_reviewer_action,
                latest_verdict=latest_verdict,
                has_minimum_verification_evidence=has_minimum_verification_evidence,
                has_latest_evaluation=latest_verdict is not None,
            )
            if workbench_state is not None and workbench_state_value != workbench_state:
                continue
            moderation_clear = (
                EvaluationService._PUBLISH_GATE_MODERATION_POLICY not in publish_gate_failures
            )
            checklist = ClaimWorkbenchService._build_checklist(
                fact_checkable=bool(row.get('fact_checkable', True)),
                latest_verdict=latest_verdict,
                latest_rationale=row.get('latest_rationale'),
                latest_citation_notes=row.get('latest_citation_notes'),
                verification_primary_count=verification_primary_count,
                verification_secondary_count=verification_secondary_count,
                moderation_clear=moderation_clear,
                dual_control_ready_for_publish=dual_control_ready_for_publish,
                dual_control_blocking=publish_gate_passed and not bool(row.get('is_published', False)),
            )
            items.append(
                {
                    'claim_id': row['claim_id'],
                    'claim_text': row['claim_text'],
                    'issue_tag': row['issue_tag'],
                    'status': row['status'],
                    'statement_source_url': row['statement_source_url'],
                    'statement_published_at': row['statement_published_at'],
                    'candidate_id': row['candidate_id'],
                    'candidate_name': row['candidate_name'],
                    'candidate_party': row['candidate_party'],
                    'candidate_office': row['candidate_office'],
                    'candidate_state': row['candidate_state'],
                    'election_cycle': row['election_cycle'],
                    'race_stage': row['race_stage'],
                    'fact_checkable': bool(row.get('fact_checkable', True)),
                    'is_published': bool(row.get('is_published', False)),
                    'published_at': row.get('published_at'),
                    'published_by_reviewer_id': row.get('published_by_reviewer_id'),
                    'reviewer_state': workbench_state_value,
                    'second_reviewer_action': second_reviewer_action,
                    'primary_source_count': int(row.get('primary_source_count') or 0),
                    'secondary_source_count': int(row.get('secondary_source_count') or 0),
                    'candidate_source_count': int(row.get('candidate_source_count') or 0),
                    'verification_source_count': int(row.get('verification_source_count') or 0),
                    'verification_primary_count': verification_primary_count,
                    'verification_secondary_count': verification_secondary_count,
                    'latest_verdict': latest_verdict,
                    'latest_confidence': row.get('latest_confidence'),
                    'latest_rationale': row.get('latest_rationale'),
                    'latest_citation_notes': row.get('latest_citation_notes'),
                    'latest_reviewer_id': latest_reviewer_id,
                    'latest_evaluated_at': row.get('latest_evaluated_at'),
                    'publish_gate_passed': publish_gate_passed,
                    'publish_gate_failures': publish_gate_failures,
                    'checklist': checklist,
                }
            )
        return items
