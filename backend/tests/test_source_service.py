from app.models.enums import RaceStage
from app.services.source_service import SourceService


def test_build_evidence_queue_query_has_race_filters_and_missing_having() -> None:
    query = SourceService._build_evidence_queue_query(
        state='TX',
        office='US Senate',
        election_cycle=2026,
        race_stage=RaceStage.primary,
        include_only_missing=True,
    )

    compiled = str(query)
    assert 'lower(candidates.state)' in compiled
    assert 'lower(candidates.office)' in compiled
    assert 'candidates.election_cycle =' in compiled
    assert 'candidates.race_stage =' in compiled
    assert 'HAVING' in compiled


def test_build_evidence_queue_query_without_missing_filter_has_no_having() -> None:
    query = SourceService._build_evidence_queue_query(
        state=None,
        office=None,
        election_cycle=None,
        race_stage=None,
        include_only_missing=False,
    )

    compiled = str(query)
    assert 'HAVING' not in compiled


def test_bulk_status_from_error_code_mappings() -> None:
    assert SourceService._bulk_status_from_error_code('duplicate_source') == 'duplicate'
    assert SourceService._bulk_status_from_error_code('claim_not_found') == 'claim_not_found'
    assert SourceService._bulk_status_from_error_code('something_else') == 'error'
