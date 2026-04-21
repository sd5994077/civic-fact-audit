from app.models.enums import RaceStage
from app.services.comparison_service import ComparisonService


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
