from app.models.enums import RaceStage, SourceClass, SourceOrigin
from app.services.source_service import SourceService


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def mappings(self):
        return self


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return _FakeExecuteResult(self._rows)


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
    assert 'claims.fact_checkable' in compiled
    assert 'sources.source_origin' in compiled
    assert 'sources.source_class' in compiled
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


def test_has_minimum_evidence_requires_verification_origin() -> None:
    db = _FakeDb(
        [
            (SourceClass.primary, SourceOrigin.candidate),
            (SourceClass.secondary, SourceOrigin.candidate),
            (SourceClass.primary, SourceOrigin.verification),
        ]
    )
    assert SourceService.has_minimum_evidence(db, claim_id='unused') is False

    db_ok = _FakeDb(
        [
            (SourceClass.primary, SourceOrigin.verification),
            (SourceClass.secondary, SourceOrigin.verification),
        ]
    )
    assert SourceService.has_minimum_evidence(db_ok, claim_id='unused') is True


def test_list_evidence_queue_missing_classes_are_verification_based() -> None:
    db = _FakeDb(
        [
            {
                'claim_id': 'c1',
                'claim_text': 'text',
                'issue_tag': 'Issue',
                'status': 'draft',
                'statement_source_url': 'https://example.com',
                'published_at': '2026-01-01T00:00:00Z',
                'candidate_id': 'cand1',
                'candidate_name': 'Candidate',
                'party': 'X',
                'office': 'US Senate',
                'state': 'TX',
                'election_cycle': 2026,
                'race_stage': None,
                'primary_count': 2,
                'secondary_count': 2,
                'candidate_count': 2,
                'verification_count': 0,
                'verification_primary_count': 0,
                'verification_secondary_count': 0,
            }
        ]
    )
    rows = SourceService.list_evidence_queue(db, include_only_missing=False)
    assert rows[0]['missing_source_classes'] == [SourceClass.primary, SourceClass.secondary]
