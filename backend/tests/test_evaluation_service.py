from app.models.enums import RaceStage
from app.services.evaluation_service import EvaluationService


def test_build_review_queue_query_has_race_filters_and_minimum_evidence_having() -> None:
    query = EvaluationService._build_review_queue_query(
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=RaceStage.primary_runoff,
        require_minimum_evidence=True,
    )

    compiled = str(query)
    assert 'lower(candidates.state)' in compiled
    assert 'lower(candidates.office)' in compiled
    assert 'candidates.election_cycle =' in compiled
    assert 'candidates.race_stage =' in compiled
    assert 'HAVING' in compiled


def test_build_review_queue_query_without_minimum_evidence_has_no_having() -> None:
    query = EvaluationService._build_review_queue_query(
        state=None,
        office=None,
        election_cycle=None,
        race_stage=None,
        require_minimum_evidence=False,
    )

    compiled = str(query)
    assert 'HAVING' not in compiled
