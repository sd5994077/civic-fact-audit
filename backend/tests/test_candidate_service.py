from app.models.enums import RaceStage
from app.services.candidate_service import CandidateService


def test_build_candidate_query_applies_all_filters() -> None:
    query = CandidateService._build_candidate_query(
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=RaceStage.primary,
    )

    compiled = str(query)
    assert 'lower(candidates.state)' in compiled
    assert 'lower(candidates.office)' in compiled
    assert 'candidates.election_cycle =' in compiled
    assert 'candidates.race_stage =' in compiled


def test_build_candidate_query_without_optional_filters() -> None:
    query = CandidateService._build_candidate_query(
        state=None,
        office=None,
        election_cycle=None,
        race_stage=None,
    )

    compiled = str(query)
    assert 'WHERE' not in compiled
