from app.models.enums import RaceStage
from app.services.comparison_service import ComparisonService, _resolve_issue_tag


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
