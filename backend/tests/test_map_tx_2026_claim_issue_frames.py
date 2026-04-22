from types import SimpleNamespace

from app.scripts.map_tx_2026_claim_issue_frames import (
    _match_frame_definition,
    _should_map_claim,
)


def test_match_frame_definition_maps_public_education_budget_claim() -> None:
    frame = _match_frame_definition(
        'Education',
        'When I entered the classroom, the Texas Legislature had just gutted the public education budget by $5 billion.',
    )

    assert frame is not None
    assert frame.frame_key == 'tx-2026-us-senate-public-education-funding'


def test_match_frame_definition_maps_supreme_court_claim_to_specific_frame() -> None:
    frame = _match_frame_definition(
        'Democracy & Rule of Law',
        'Helped confirm all three of President Trump Supreme Court Justices, including Neil Gorsuch.',
    )

    assert frame is not None
    assert frame.frame_key == 'tx-2026-us-senate-supreme-court-confirmations'


def test_match_frame_definition_falls_back_to_issue_tag_level_frame() -> None:
    frame = _match_frame_definition(
        'Border & Immigration',
        'Immigration policy has changed significantly in recent years.',
    )

    assert frame is not None
    assert frame.frame_key == 'tx-2026-us-senate-border-enforcement-record'


def test_match_frame_definition_returns_none_for_unknown_issue_tag() -> None:
    assert _match_frame_definition('Agriculture', 'Farm output increased year over year.') is None


def test_match_frame_definition_returns_none_for_ambiguous_tag_without_keyword_match() -> None:
    frame = _match_frame_definition(
        'Democracy & Rule of Law',
        'The judiciary must remain accountable to constitutional checks and balances.',
    )
    assert frame is None


def test_should_map_claim_rejects_non_fact_checkable_or_campaign_claims() -> None:
    slogan_claim = SimpleNamespace(fact_checkable=True, issue_tag='Campaign Messaging')
    non_fact_claim = SimpleNamespace(fact_checkable=False, issue_tag='Economy')
    good_claim = SimpleNamespace(fact_checkable=True, issue_tag='Economy')

    assert _should_map_claim(slogan_claim) is False
    assert _should_map_claim(non_fact_claim) is False
    assert _should_map_claim(good_claim) is True
