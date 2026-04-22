import uuid
from datetime import datetime, timezone

from app.models.enums import RaceStage, SourceClass, Verdict
from app.services.comparison_service import (
    ComparisonService,
    _CompareRow,
    _build_issue_frame_policy_by_key,
    _resolve_issue_frame_policy,
    _resolve_issue_tag,
)


def test_candidate_filters_include_cycle_and_stage_when_provided() -> None:
    filters = ComparisonService._candidate_filters(
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=RaceStage.primary,
    )

    assert len(filters) == 4


def test_candidate_filters_only_require_state_and_office_by_default() -> None:
    filters = ComparisonService._candidate_filters(
        state='TX',
        office='US Senate',
        election_cycle=None,
        race_stage=None,
    )

    assert len(filters) == 2


def test_resolve_issue_tag_prefers_frame_title_when_available() -> None:
    assert _resolve_issue_tag('Election Integrity', '2020 Election') == 'Election Integrity'


def test_resolve_issue_tag_falls_back_to_issue_tag() -> None:
    assert _resolve_issue_tag(None, '2020 Election') == '2020 Election'


def test_resolve_issue_tag_trims_and_handles_empty_values() -> None:
    assert _resolve_issue_tag('  ', '  ') is None


def test_build_issue_frame_policy_by_key_indexes_by_frame_key() -> None:
    frame_key = 'tx-2026-us-senate-election-integrity'
    rows = [
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim A',
            issue_tag='Election Integrity',
            issue_frame_key=frame_key,
            comparison_question='What verifiable evidence exists for each candidate view?',
            allowed_candidate_source_classes=[SourceClass.primary],
            allowed_verification_source_classes=[SourceClass.primary, SourceClass.secondary],
            statement_source_url='https://example.com/a',
            statement_published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
            verdict=Verdict.supported,
            confidence=0.9,
            rationale='Rationale A',
            citation_notes='Notes A',
            evidence_bundle=None,
        ),
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim B',
            issue_tag='Different Issue',
            issue_frame_key='tx-2026-us-senate-border-security',
            comparison_question='How accurate are each candidate border claims?',
            allowed_candidate_source_classes=[SourceClass.primary],
            allowed_verification_source_classes=[SourceClass.primary, SourceClass.secondary],
            statement_source_url='https://example.com/b',
            statement_published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            verdict=Verdict.mixed,
            confidence=0.5,
            rationale='Rationale B',
            citation_notes='Notes B',
            evidence_bundle=None,
        ),
    ]

    policies = _build_issue_frame_policy_by_key(rows)

    assert policies[frame_key].frame_key == frame_key
    assert policies[frame_key].allowed_candidate_source_classes == [SourceClass.primary]
    assert policies[frame_key].allowed_verification_source_classes == [SourceClass.primary, SourceClass.secondary]


def test_resolve_issue_frame_policy_requires_single_consistent_frame_key() -> None:
    issue_rows = [
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim A',
            issue_tag='Election Integrity',
            issue_frame_key='tx-2026-us-senate-election-integrity',
            comparison_question='What verifiable evidence exists for each candidate view?',
            allowed_candidate_source_classes=[SourceClass.primary],
            allowed_verification_source_classes=[SourceClass.primary, SourceClass.secondary],
            statement_source_url='https://example.com/a',
            statement_published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
            verdict=Verdict.supported,
            confidence=0.9,
            rationale='Rationale A',
            citation_notes='Notes A',
            evidence_bundle=None,
        ),
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim B',
            issue_tag='Election Integrity',
            issue_frame_key='tx-2026-us-senate-election-integrity',
            comparison_question='What verifiable evidence exists for each candidate view?',
            allowed_candidate_source_classes=[SourceClass.primary],
            allowed_verification_source_classes=[SourceClass.primary, SourceClass.secondary],
            statement_source_url='https://example.com/b',
            statement_published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            verdict=Verdict.mixed,
            confidence=0.5,
            rationale='Rationale B',
            citation_notes='Notes B',
            evidence_bundle=None,
        ),
    ]
    frame_policies = _build_issue_frame_policy_by_key(issue_rows)

    policy = _resolve_issue_frame_policy(issue_rows, frame_policies)
    assert policy is not None
    assert policy.frame_key == 'tx-2026-us-senate-election-integrity'


def test_resolve_issue_frame_policy_returns_none_for_mixed_mapped_and_unmapped_rows() -> None:
    issue_rows = [
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim A',
            issue_tag='Election Integrity',
            issue_frame_key='tx-2026-us-senate-election-integrity',
            comparison_question='What verifiable evidence exists for each candidate view?',
            allowed_candidate_source_classes=[SourceClass.primary],
            allowed_verification_source_classes=[SourceClass.primary, SourceClass.secondary],
            statement_source_url='https://example.com/a',
            statement_published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
            verdict=Verdict.supported,
            confidence=0.9,
            rationale='Rationale A',
            citation_notes='Notes A',
            evidence_bundle=None,
        ),
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim B',
            issue_tag='Election Integrity',
            issue_frame_key=None,
            comparison_question=None,
            allowed_candidate_source_classes=None,
            allowed_verification_source_classes=None,
            statement_source_url='https://example.com/b',
            statement_published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            verdict=Verdict.insufficient,
            confidence=0.1,
            rationale='Rationale B',
            citation_notes=None,
            evidence_bundle=None,
        ),
    ]
    frame_policies = _build_issue_frame_policy_by_key(issue_rows)

    assert _resolve_issue_frame_policy(issue_rows, frame_policies) is None


def test_resolve_issue_frame_policy_returns_none_for_multiple_frame_keys() -> None:
    issue_rows = [
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim A',
            issue_tag='Election Integrity',
            issue_frame_key='tx-2026-us-senate-election-integrity',
            comparison_question='Question A',
            allowed_candidate_source_classes=[SourceClass.primary],
            allowed_verification_source_classes=[SourceClass.primary, SourceClass.secondary],
            statement_source_url='https://example.com/a',
            statement_published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
            verdict=Verdict.supported,
            confidence=0.9,
            rationale='Rationale A',
            citation_notes='Notes A',
            evidence_bundle=None,
        ),
        _CompareRow(
            candidate_id=uuid.uuid4(),
            claim_id=uuid.uuid4(),
            claim_text='Claim B',
            issue_tag='Election Integrity',
            issue_frame_key='tx-2026-us-senate-voting-process',
            comparison_question='Question B',
            allowed_candidate_source_classes=[SourceClass.primary],
            allowed_verification_source_classes=[SourceClass.primary, SourceClass.secondary],
            statement_source_url='https://example.com/b',
            statement_published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            verdict=Verdict.mixed,
            confidence=0.5,
            rationale='Rationale B',
            citation_notes='Notes B',
            evidence_bundle=None,
        ),
    ]
    frame_policies = _build_issue_frame_policy_by_key(issue_rows)

    assert _resolve_issue_frame_policy(issue_rows, frame_policies) is None
