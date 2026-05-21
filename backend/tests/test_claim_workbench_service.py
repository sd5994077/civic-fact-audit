import uuid
from datetime import datetime, timezone

from app.models.enums import ClaimStatus, Verdict
from app.services.claim_workbench_service import ClaimWorkbenchService


def _base_row() -> dict[str, object]:
    return {
        'claim_id': uuid.uuid4(),
        'claim_text': 'Claim text',
        'issue_tag': 'Economy',
        'status': ClaimStatus.reviewed,
        'statement_source_url': 'https://example.com/statement',
        'statement_published_at': datetime(2026, 5, 10, tzinfo=timezone.utc),
        'candidate_id': uuid.uuid4(),
        'candidate_name': 'Candidate A',
        'candidate_party': 'Independent',
        'candidate_office': 'Governor',
        'candidate_state': 'TX',
        'election_cycle': 2026,
        'race_stage': None,
        'fact_checkable': True,
        'is_published': False,
        'published_at': None,
        'published_by_reviewer_id': None,
        'primary_source_count': 0,
        'secondary_source_count': 0,
        'candidate_source_count': 0,
        'verification_source_count': 0,
        'verification_primary_count': 0,
        'verification_secondary_count': 0,
        'latest_verdict': None,
        'latest_confidence': None,
        'latest_rationale': None,
        'latest_citation_notes': None,
        'latest_reviewer_id': None,
        'latest_evaluated_at': None,
    }


def test_workbench_states_and_precedence(monkeypatch) -> None:
    needs_evidence = _base_row()

    needs_review = _base_row()
    needs_review['verification_primary_count'] = 1
    needs_review['verification_secondary_count'] = 1
    needs_review['verification_source_count'] = 2

    insufficient = _base_row()
    insufficient['verification_primary_count'] = 1
    insufficient['verification_secondary_count'] = 1
    insufficient['verification_source_count'] = 2
    insufficient['latest_verdict'] = Verdict.insufficient
    insufficient['latest_reviewer_id'] = 'reviewer@local'

    second_reviewer = _base_row()
    second_reviewer['latest_verdict'] = Verdict.supported
    second_reviewer['latest_rationale'] = 'Rationale'
    second_reviewer['latest_citation_notes'] = None
    second_reviewer['verification_primary_count'] = 1
    second_reviewer['verification_secondary_count'] = 1
    second_reviewer['verification_source_count'] = 2
    second_reviewer['latest_reviewer_id'] = 'reviewer@local'

    ready_to_publish = _base_row()
    ready_to_publish['latest_verdict'] = Verdict.supported
    ready_to_publish['latest_rationale'] = 'Rationale'
    ready_to_publish['latest_citation_notes'] = 'Citation packet'
    ready_to_publish['verification_primary_count'] = 1
    ready_to_publish['verification_secondary_count'] = 1
    ready_to_publish['verification_source_count'] = 2
    ready_to_publish['latest_reviewer_id'] = 'second-reviewer@local'

    published = _base_row()
    published['is_published'] = True
    published['published_at'] = datetime(2026, 5, 11, tzinfo=timezone.utc)
    published['latest_verdict'] = Verdict.supported
    published['latest_rationale'] = 'Rationale'
    published['latest_citation_notes'] = 'Citation packet'
    published['verification_primary_count'] = 1
    published['verification_secondary_count'] = 1
    published['verification_source_count'] = 2
    published['latest_reviewer_id'] = 'reviewer@local'

    rows = [needs_evidence, needs_review, insufficient, second_reviewer, ready_to_publish, published]

    monkeypatch.setattr(
        'app.services.claim_workbench_service.EvaluationService.list_review_queue',
        lambda *_args, **_kwargs: rows,
    )

    def _gate_failures(row: dict[str, object]) -> list[str]:
        claim_id = row['claim_id']
        if claim_id == ready_to_publish['claim_id'] or claim_id == published['claim_id']:
            return []
        if claim_id == second_reviewer['claim_id']:
            return ['latest_citation_notes_required']
        return ['verification_primary_source_required', 'verification_secondary_source_required']

    monkeypatch.setattr(
        'app.services.claim_workbench_service.EvaluationService._publish_gate_failures_from_review_row',
        _gate_failures,
    )

    items = ClaimWorkbenchService.list_workbench(object(), actor_reviewer_id='reviewer@local')  # type: ignore[arg-type]
    by_claim_id = {item['claim_id']: item for item in items}

    assert by_claim_id[needs_evidence['claim_id']]['reviewer_state'] == ClaimWorkbenchService.STATE_NEEDS_EVIDENCE
    assert by_claim_id[needs_review['claim_id']]['reviewer_state'] == ClaimWorkbenchService.STATE_NEEDS_REVIEW
    assert by_claim_id[insufficient['claim_id']]['reviewer_state'] == ClaimWorkbenchService.STATE_INSUFFICIENT_EVIDENCE
    assert by_claim_id[insufficient['claim_id']]['second_reviewer_action'] is None
    assert by_claim_id[second_reviewer['claim_id']]['reviewer_state'] == ClaimWorkbenchService.STATE_NEEDS_SECOND_REVIEWER
    assert by_claim_id[second_reviewer['claim_id']]['second_reviewer_action'] == ClaimWorkbenchService.SECOND_REVIEWER_ACTION_OVERWRITE_HANDOFF
    assert by_claim_id[ready_to_publish['claim_id']]['reviewer_state'] == ClaimWorkbenchService.STATE_READY_TO_PUBLISH
    assert by_claim_id[ready_to_publish['claim_id']]['second_reviewer_action'] is None
    assert by_claim_id[published['claim_id']]['reviewer_state'] == ClaimWorkbenchService.STATE_PUBLISHED


def test_workbench_filters_by_state_and_passes_non_fact_checkable_flag(monkeypatch) -> None:
    captured: dict[str, object] = {}
    row = _base_row()

    def _fake_list_review_queue(_db, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return [row]

    monkeypatch.setattr(
        'app.services.claim_workbench_service.EvaluationService.list_review_queue',
        _fake_list_review_queue,
    )
    monkeypatch.setattr(
        'app.services.claim_workbench_service.EvaluationService._publish_gate_failures_from_review_row',
        lambda _row: ['verification_primary_source_required'],
    )

    no_match = ClaimWorkbenchService.list_workbench(
        object(),  # type: ignore[arg-type]
        actor_reviewer_id='reviewer@local',
        include_non_fact_checkable=True,
        workbench_state=ClaimWorkbenchService.STATE_READY_TO_PUBLISH,
    )
    assert no_match == []
    assert captured['include_non_fact_checkable'] is True
    assert captured['require_minimum_evidence'] is False
