import uuid
from datetime import datetime, timezone

from app.models.enums import EvidenceLinkType, RaceStage, SourceClass, SourceOrigin, Verdict
from app.services.comparison_service import (
    PUBLIC_EVIDENCE_LINKS_PER_SIDE,
    ComparisonService,
    _CompareRow,
    _build_issue_warnings,
    _build_item_warnings,
    _build_issue_frame_policy_by_key,
    _curate_public_evidence_bundle,
    _resolve_issue_frame_policy,
    _resolve_issue_tag,
    _sanitize_public_citation_notes,
    _sanitize_public_rationale,
)
from app.schemas.api import ClaimEvidenceBundleRead, CompareClaimItem, EvidenceBundleLinkRead


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


def _bundle_link(order: int, link_type: EvidenceLinkType) -> EvidenceBundleLinkRead:
    return EvidenceBundleLinkRead(
        id=uuid.uuid4(),
        bundle_id=uuid.uuid4(),
        statement_id=None,
        source_id=uuid.uuid4(),
        url=f'https://example.com/{link_type.value}/{order}',
        label=f'Link {order}',
        link_type=link_type,
        source_class=SourceClass.secondary,
        source_origin=SourceOrigin.verification,
        publisher='Publisher',
        quality_score=0.8,
        display_order=order,
        created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


def test_curate_public_evidence_bundle_caps_links_per_side() -> None:
    bundle = ClaimEvidenceBundleRead(
        id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        is_curated=False,
        stance_links=[_bundle_link(i, EvidenceLinkType.stance) for i in range(8)],
        verification_links=[_bundle_link(i, EvidenceLinkType.verification) for i in range(7)],
    )

    curated = _curate_public_evidence_bundle(bundle, per_side_limit=PUBLIC_EVIDENCE_LINKS_PER_SIDE)

    assert curated is not None
    assert len(curated.stance_links) == PUBLIC_EVIDENCE_LINKS_PER_SIDE
    assert len(curated.verification_links) == PUBLIC_EVIDENCE_LINKS_PER_SIDE
    assert [link.display_order for link in curated.stance_links] == [0, 1, 2, 3, 4]
    assert [link.display_order for link in curated.verification_links] == [0, 1, 2, 3, 4]


def test_build_item_warnings_flags_missing_verification_classes() -> None:
    warnings = _build_item_warnings(sources=[], evidence_bundle=None)
    codes = {warning.code for warning in warnings}
    assert 'missing_verification_primary' in codes
    assert 'missing_verification_secondary' in codes


def test_build_issue_warnings_flags_imbalance() -> None:
    item_balanced = CompareClaimItem(
        candidate_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        claim_text='Claim A',
        issue_tag='Economy',
        statement_source_url='https://example.com/a',
        statement_published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        verdict=Verdict.supported,
        confidence=0.9,
        rationale='Rationale A',
        citation_notes=None,
        sources=[],
        evidence_bundle=None,
        warnings=[],
    )
    item_missing = CompareClaimItem(
        candidate_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        claim_text='Claim B',
        issue_tag='Economy',
        statement_source_url='https://example.com/b',
        statement_published_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        verdict=Verdict.mixed,
        confidence=0.6,
        rationale='Rationale B',
        citation_notes=None,
        sources=[],
        evidence_bundle=None,
        warnings=_build_item_warnings(sources=[], evidence_bundle=None),
    )
    issue_warnings = _build_issue_warnings([item_balanced, item_missing])
    codes = {warning.code for warning in issue_warnings}
    assert 'source_class_imbalance_primary' in codes
    assert 'source_class_imbalance_secondary' in codes


def test_sanitize_public_rationale_redacts_moderation_violation() -> None:
    rationale, warnings = _sanitize_public_rationale('You should vote for this candidate.')
    assert 'vote for' not in rationale.lower()
    assert any(w.code == 'moderation_policy_redacted_rationale' for w in warnings)


def test_sanitize_public_citation_notes_redacts_moderation_violation() -> None:
    citation_notes, warnings = _sanitize_public_citation_notes('Voters should choose this person.')
    assert citation_notes is not None
    assert 'choose this person' not in citation_notes.lower()
    assert any(w.code == 'moderation_policy_redacted_citation_notes' for w in warnings)
