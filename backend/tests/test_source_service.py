from app.models.enums import RaceStage, SourceClass, SourceOrigin
from app.core.errors import AppError
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


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _FakeClaim:
    def __init__(self, id_):
        self.id = id_


class _FakeDbForAddSource:
    def __init__(self, claim_id):
        self._claim_id = claim_id
        self.added = []
        self.committed = 0
        self.rolled_back = 0
        self.scalar_values = []

    def get(self, _model, id_):
        if id_ == self._claim_id:
            return _FakeClaim(self._claim_id)
        return None

    def add(self, value):
        self.added.append(value)
        self.scalar_values.append(value)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def flush(self):
        return None

    def scalars(self, *_args, **_kwargs):
        return _FakeScalarResult(self.scalar_values)


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


def test_add_source_syncs_evidence_bundle(monkeypatch) -> None:
    sync_calls = []

    def _fake_sync(db, claim_id, *, commit):
        sync_calls.append((db, claim_id, commit))

    monkeypatch.setattr('app.services.source_service.EvidenceBundleService.sync_claim_bundle', _fake_sync)

    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://example.com/source',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Example',
            'quality_score': 0.9,
        },
    )()

    SourceService.add_source(db, claim_id, payload)

    assert len(sync_calls) == 1
    assert sync_calls[0][1] == claim_id
    assert sync_calls[0][2] is False
    assert db.committed == 1
    assert db.rolled_back == 0


def test_add_source_rolls_back_if_bundle_sync_fails(monkeypatch) -> None:
    def _fake_sync(_db, _claim_id, *, commit):
        assert commit is False
        raise AppError('bundle_sync_failed', 'bundle sync failed', status_code=500)

    monkeypatch.setattr('app.services.source_service.EvidenceBundleService.sync_claim_bundle', _fake_sync)

    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://example.com/source',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Example',
            'quality_score': 0.9,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected AppError when bundle sync fails'
    except AppError as exc:
        assert exc.code == 'bundle_sync_failed'

    assert db.committed == 0
    assert db.rolled_back == 1
