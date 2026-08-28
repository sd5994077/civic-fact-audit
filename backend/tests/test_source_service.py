import uuid
import json

from app.models.enums import RaceStage, SourceClass, SourceOrigin
from app.models.entities import AdminAuditEvent
from app.core.errors import AppError
from app.schemas.api import BulkSourceAttachItem
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
        self.is_published = False


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

    def delete(self, value):
        if value in self.scalar_values:
            self.scalar_values.remove(value)


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
    assert 'sources.policy_flagged' in compiled
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
    assert SourceService._bulk_status_from_error_code('source_admission_policy_violation') == 'policy_violation'
    assert SourceService._bulk_status_from_error_code('something_else') == 'error'


def test_get_partisan_match_detects_publisher_rule_from_config() -> None:
    match = SourceService.get_partisan_match(publisher='Republican Party of Texas', url='https://example.com/news')
    assert match is not None
    assert match.field == 'publisher'
    assert match.pattern == 'republican party'


def test_get_partisan_match_detects_domain_rule_from_config() -> None:
    match = SourceService.get_partisan_match(publisher='Neutral Publisher', url='https://subdomain.dailykos.com/story')
    assert match is not None
    assert match.field == 'domain'
    assert match.pattern == 'dailykos.com'


def test_get_partisan_match_detects_domain_rule_with_port_and_userinfo() -> None:
    match = SourceService.get_partisan_match(
        publisher='Neutral Publisher',
        url='https://user:token@subdomain.dailykos.com:443/story',
    )
    assert match is not None
    assert match.field == 'domain'
    assert match.pattern == 'dailykos.com'


def test_add_source_candidate_direct_quote_accepts_social_url_with_port_and_userinfo(monkeypatch) -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    monkeypatch.setattr(
        'app.services.source_service.EvidenceBundleService.sync_claim_bundle',
        lambda *_args, **_kwargs: None,
    )
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://user@x.com:443/candidate/status/123',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.candidate,
            'publisher': 'Republican Party of Texas',
            'quality_score': 0.8,
            'is_direct_candidate_quote': True,
        },
    )()

    SourceService.add_source(db, claim_id, payload)

    assert db.committed == 1
    assert db.rolled_back == 0


def test_has_minimum_evidence_requires_verification_origin() -> None:
    db = _FakeDb(
        [
            (SourceClass.primary,),
        ]
    )
    assert SourceService.has_minimum_evidence(db, claim_id='unused') is False

    db_ok = _FakeDb(
        [
            (SourceClass.primary,),
            (SourceClass.secondary,),
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


def test_add_source_preserves_reviewer_supplied_http_url(monkeypatch) -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    supplied_url = 'http://example.gov/records/item/?record=7&utm_source=review'
    monkeypatch.setattr(
        'app.services.source_service.SourceService.validate_source_admission',
        lambda _payload: {'status': 'ok'},
    )
    monkeypatch.setattr(
        'app.services.source_service.EvidenceBundleService.sync_claim_bundle',
        lambda *_args, **_kwargs: None,
    )
    payload = type(
        'Payload',
        (),
        {
            'url': supplied_url,
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Example Agency',
            'quality_score': 0.9,
            'is_direct_candidate_quote': False,
        },
    )()

    SourceService.add_source(db, claim_id, payload)

    assert db.added[0].url == supplied_url


def test_add_source_uses_non_destructive_url_key_for_duplicate_detection(monkeypatch) -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    db.scalar_values = ['https://example.gov/records/item?record=7']
    monkeypatch.setattr(
        'app.services.source_service.SourceService.validate_source_admission',
        lambda _payload: {'status': 'ok'},
    )
    payload = type(
        'Payload',
        (),
        {
            'url': 'http://example.gov/records/item/?utm_source=review&record=7',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Example Agency',
            'quality_score': 0.9,
            'is_direct_candidate_quote': False,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected duplicate source rejection'
    except AppError as exc:
        assert exc.code == 'duplicate_source'

    assert db.added == []


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


def test_add_source_blocks_partisan_verification_sources() -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://www.dailykos.com/stories/example',
            'source_class': SourceClass.secondary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Daily Kos',
            'quality_score': 0.5,
            'is_direct_candidate_quote': False,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected source admission policy violation'
    except AppError as exc:
        assert exc.code == 'source_admission_policy_violation'
        assert exc.details['rejection_field'] == 'source_origin'
        assert exc.details['matched_rule']['field'] in {'publisher', 'domain'}


def test_add_source_blocks_discovery_search_url_for_verification_origin() -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://www.congress.gov/search?q=cornyn',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Congress.gov',
            'quality_score': 0.8,
            'is_direct_candidate_quote': False,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected discovery link attach to be blocked'
    except AppError as exc:
        assert exc.code == 'source_discovery_link_not_attachable'
        assert exc.details['rejection_field'] == 'url'
        assert exc.details['page_type'] == 'search_results'


def test_classify_url_page_type_treats_root_query_as_search() -> None:
    page_type = SourceService._classify_url_page_type('https://www.congress.gov/?q=cornyn')
    assert page_type == 'search_results'


def test_classify_url_page_type_keeps_article_with_query_as_content() -> None:
    page_type = SourceService._classify_url_page_type('https://example.com/articles/cornyn-votes?q=tracking')
    assert page_type == 'content'


def test_add_source_blocks_candidate_social_url_for_verification_origin() -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://x.com/examplecandidate/status/123',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Example Candidate',
            'quality_score': 0.5,
            'is_direct_candidate_quote': True,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected source admission policy violation'
    except AppError as exc:
        assert exc.code == 'source_admission_policy_violation'
        assert exc.details['rejection_field'] == 'source_origin'
        assert 'allowed_social_domains' in exc.details


def test_add_source_blocks_candidate_social_url_without_direct_quote_flag() -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://x.com/examplecandidate/status/123',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.candidate,
            'publisher': 'Example Candidate',
            'quality_score': 0.5,
            'is_direct_candidate_quote': False,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected source admission policy violation'
    except AppError as exc:
        assert exc.code == 'source_admission_policy_violation'
        assert exc.details['rejection_field'] == 'is_direct_candidate_quote'
        assert exc.details['source_origin'] == SourceOrigin.candidate.value


def test_add_source_blocks_partisan_candidate_without_direct_quote_flag() -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://x.com/examplecandidate/status/123',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.candidate,
            'publisher': 'RNC',
            'quality_score': 0.5,
            'is_direct_candidate_quote': False,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected source admission policy violation'
    except AppError as exc:
        assert exc.code == 'source_admission_policy_violation'
        assert exc.details['rejection_field'] == 'is_direct_candidate_quote'


def test_add_source_blocks_partisan_candidate_direct_quote_on_non_social_url() -> None:
    claim_id = 'claim-1'
    db = _FakeDbForAddSource(claim_id=claim_id)
    payload = type(
        'Payload',
        (),
        {
            'url': 'https://www.dailykos.com/stories/example',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.candidate,
            'publisher': 'RNC',
            'quality_score': 0.5,
            'is_direct_candidate_quote': True,
        },
    )()

    try:
        SourceService.add_source(db, claim_id, payload)
        assert False, 'Expected source admission policy violation'
    except AppError as exc:
        assert exc.code == 'source_admission_policy_violation'
        assert exc.details['rejection_field'] == 'url'


def test_add_source_allows_partisan_candidate_direct_quote_on_social_url(monkeypatch) -> None:
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
            'url': 'https://x.com/examplecandidate/status/123',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.candidate,
            'publisher': 'RNC',
            'quality_score': 0.5,
            'is_direct_candidate_quote': True,
        },
    )()

    SourceService.add_source(db, claim_id, payload)
    assert len(sync_calls) == 1


def test_attach_sources_bulk_blocks_verification_items_when_reviewers_match(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id=claim_id)
    monkeypatch.setattr(
        'app.services.source_service.AuthService.resolve_active_reviewer_id',
        lambda _db, reviewer_id, *, allowed_roles=None: reviewer_id.strip().lower() if reviewer_id else None,
    )
    items = [
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://example.gov/record',
            source_class=SourceClass.primary,
            source_origin=SourceOrigin.verification,
            quality_score=0.9,
        )
    ]
    try:
        SourceService.attach_sources_bulk(
            db,  # type: ignore[arg-type]
            approval_reviewer_id='ADMIN@LOCAL',
            applying_reviewer_id=' admin@local ',
            items=items,
        )
        assert False, 'Expected bulk_attach_dual_control_required'
    except AppError as exc:
        assert exc.code == 'bulk_attach_dual_control_required'
        assert exc.status_code == 409
        assert exc.details['approval_reviewer_id'] == 'admin@local'
        assert exc.details['applying_reviewer_id'] == 'admin@local'
        assert exc.details['action'] == 'bulk_attach_verification_sources'
        assert isinstance(exc.details['bulk_operation_id'], str)


def test_attach_sources_bulk_allows_candidate_origin_when_reviewers_match(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id=claim_id)
    monkeypatch.setattr(
        'app.services.source_service.EvidenceBundleService.sync_claim_bundle',
        lambda *_args, **_kwargs: None,
    )
    items = [
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://x.com/candidate/status/1',
            source_class=SourceClass.primary,
            source_origin=SourceOrigin.candidate,
            quality_score=0.6,
            is_direct_candidate_quote=True,
        )
    ]

    result = SourceService.attach_sources_bulk(
        db,  # type: ignore[arg-type]
        approval_reviewer_id='admin@local',
        applying_reviewer_id='admin@local',
        items=items,
    )

    assert result['total'] == 1
    assert result['attached'] == 1
    assert result['failed'] == 0
    assert result['results'][0]['status'] == 'attached'
    assert isinstance(result['bulk_operation_id'], str)


def test_attach_sources_bulk_mixed_batch_enforces_verification_only_and_writes_audit(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id=claim_id)
    monkeypatch.setattr(
        'app.services.source_service.AuthService.resolve_active_reviewer_id',
        lambda _db, reviewer_id, *, allowed_roles=None: reviewer_id.strip().lower() if reviewer_id else None,
    )
    monkeypatch.setattr(
        'app.services.source_service.EvidenceBundleService.sync_claim_bundle',
        lambda *_args, **_kwargs: None,
    )
    items = [
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://example.gov/record-1',
            source_class=SourceClass.primary,
            source_origin=SourceOrigin.verification,
            quality_score=0.9,
        ),
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://example.gov/duplicate',
            source_class=SourceClass.secondary,
            source_origin=SourceOrigin.verification,
            quality_score=0.5,
        ),
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://x.com/candidate/status/1',
            source_class=SourceClass.primary,
            source_origin=SourceOrigin.candidate,
            quality_score=0.6,
            is_direct_candidate_quote=True,
        ),
    ]

    def _fake_add_source(_db, _claim_id, payload, *, commit=True):  # type: ignore[no-untyped-def]
        if 'duplicate' in str(payload.url):
            raise AppError('duplicate_source', 'Duplicate source', status_code=409)
        return []

    monkeypatch.setattr('app.services.source_service.SourceService.add_source', _fake_add_source)

    result = SourceService.attach_sources_bulk(
        db,  # type: ignore[arg-type]
        approval_reviewer_id='Approver@Local',
        applying_reviewer_id='applier@local',
        items=items,
    )

    assert result['total'] == 3
    assert result['attached'] == 2
    assert result['failed'] == 1
    assert [row['status'] for row in result['results']] == ['attached', 'duplicate', 'attached']
    assert isinstance(result['bulk_operation_id'], str)
    events = [item for item in db.added if isinstance(item, AdminAuditEvent)]
    assert len(events) == 1
    metadata = json.loads(events[0].metadata_payload or '{}')
    assert metadata['bulk_operation_id'] == result['bulk_operation_id']
    assert metadata['status_counts']['attached'] == 2
    assert metadata['status_counts']['duplicate'] == 1
    assert metadata['status_counts']['policy_violation'] == 0
    assert metadata['status_counts']['claim_not_found'] == 0
    assert metadata['status_counts']['error'] == 0
    assert metadata['approval_reviewer_id'] == 'approver@local'
    assert metadata['applying_reviewer_id'] == 'applier@local'
    assert metadata['dual_control_enforced'] is True


def test_attach_sources_bulk_mixed_batch_same_reviewer_blocks_only_verification_items(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id=claim_id)
    monkeypatch.setattr(
        'app.services.source_service.EvidenceBundleService.sync_claim_bundle',
        lambda *_args, **_kwargs: None,
    )
    items = [
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://example.gov/record-1',
            source_class=SourceClass.primary,
            source_origin=SourceOrigin.verification,
            quality_score=0.9,
        ),
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://x.com/candidate/status/1',
            source_class=SourceClass.primary,
            source_origin=SourceOrigin.candidate,
            quality_score=0.6,
            is_direct_candidate_quote=True,
        ),
    ]

    def _fake_add_source(_db, _claim_id, payload, *, commit=True):  # type: ignore[no-untyped-def]
        assert payload.source_origin == SourceOrigin.candidate
        return []

    monkeypatch.setattr('app.services.source_service.SourceService.add_source', _fake_add_source)

    result = SourceService.attach_sources_bulk(
        db,  # type: ignore[arg-type]
        approval_reviewer_id='admin@local',
        applying_reviewer_id='admin@local',
        items=items,
    )

    assert result['total'] == 2
    assert result['attached'] == 1
    assert result['failed'] == 1
    assert result['results'][0]['source_origin'] == SourceOrigin.verification
    assert result['results'][0]['status'] == 'error'
    assert result['results'][0]['error']['code'] == 'bulk_attach_dual_control_required'
    assert result['results'][1]['source_origin'] == SourceOrigin.candidate
    assert result['results'][1]['status'] == 'attached'


def test_attach_sources_bulk_operation_id_is_deterministic(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id=claim_id)
    monkeypatch.setattr(
        'app.services.source_service.AuthService.resolve_active_reviewer_id',
        lambda _db, reviewer_id, *, allowed_roles=None: reviewer_id.strip().lower() if reviewer_id else None,
    )
    monkeypatch.setattr(
        'app.services.source_service.SourceService.add_source',
        lambda *_args, **_kwargs: [],
    )
    items = [
        BulkSourceAttachItem(
            claim_id=claim_id,
            url='https://example.gov/record',
            source_class=SourceClass.primary,
            source_origin=SourceOrigin.verification,
            quality_score=0.9,
        )
    ]
    first = SourceService.attach_sources_bulk(
        db,  # type: ignore[arg-type]
        approval_reviewer_id='approver@local',
        applying_reviewer_id='applier@local',
        items=items,
    )
    second = SourceService.attach_sources_bulk(
        db,  # type: ignore[arg-type]
        approval_reviewer_id='approver@local',
        applying_reviewer_id='applier@local',
        items=items,
    )
    assert first['bulk_operation_id'] == second['bulk_operation_id']


def test_attach_sources_bulk_operation_id_ignores_item_order(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id=claim_id)
    monkeypatch.setattr(
        'app.services.source_service.AuthService.resolve_active_reviewer_id',
        lambda _db, reviewer_id, *, allowed_roles=None: reviewer_id.strip().lower() if reviewer_id else None,
    )
    monkeypatch.setattr(
        'app.services.source_service.SourceService.add_source',
        lambda *_args, **_kwargs: [],
    )
    item_a = BulkSourceAttachItem(
        claim_id=claim_id,
        url='https://example.gov/record-a',
        source_class=SourceClass.primary,
        source_origin=SourceOrigin.verification,
        quality_score=0.9,
    )
    item_b = BulkSourceAttachItem(
        claim_id=claim_id,
        url='https://example.gov/record-b',
        source_class=SourceClass.secondary,
        source_origin=SourceOrigin.verification,
        quality_score=0.8,
    )
    first = SourceService.attach_sources_bulk(
        db,  # type: ignore[arg-type]
        approval_reviewer_id='approver@local',
        applying_reviewer_id='applier@local',
        items=[item_a, item_b],
    )
    second = SourceService.attach_sources_bulk(
        db,  # type: ignore[arg-type]
        approval_reviewer_id='approver@local',
        applying_reviewer_id='applier@local',
        items=[item_b, item_a],
    )
    assert first['bulk_operation_id'] == second['bulk_operation_id']


def test_add_source_auto_fills_quality_score_when_omitted(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id)
    monkeypatch.setattr('app.services.source_service.EvidenceBundleService.sync_claim_bundle', lambda *_a, **_kw: None)

    from app.schemas.api import AddSourceRequest

    payload = AddSourceRequest(
        url='https://cbo.gov/report/2024',
        source_class=SourceClass.primary,
        source_origin=SourceOrigin.verification,
    )
    assert payload.quality_score is None

    SourceService.add_source(db, claim_id, payload)

    assert len(db.added) == 1
    source = db.added[0]
    assert source.quality_score is not None
    assert 0.0 <= source.quality_score <= 1.0
    assert source.quality_score == 1.0


def test_add_source_preserves_explicit_quality_score(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id)
    monkeypatch.setattr('app.services.source_service.EvidenceBundleService.sync_claim_bundle', lambda *_a, **_kw: None)

    from app.schemas.api import AddSourceRequest

    payload = AddSourceRequest(
        url='https://example.com/article',
        source_class=SourceClass.secondary,
        source_origin=SourceOrigin.verification,
        quality_score=0.55,
    )

    SourceService.add_source(db, claim_id, payload)

    source = db.added[0]
    assert source.quality_score == 0.55


def test_delete_source_succeeds_for_unpublished_claim(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id)
    fake_source = type(
        'SourceObj',
        (),
        {
            'id': source_id,
            'claim_id': claim_id,
            'url': 'https://example.com/source',
            'source_class': SourceClass.primary,
            'source_origin': SourceOrigin.verification,
            'publisher': 'Example',
            'quality_score': 0.8,
        },
    )()
    db.scalar_values = [fake_source]

    monkeypatch.setattr(
        SourceService,
        '_get_claim_for_source_mutation',
        staticmethod(lambda *_args, **_kwargs: _FakeClaim(claim_id)),
    )
    monkeypatch.setattr(
        SourceService,
        '_get_source_for_claim_mutation',
        staticmethod(lambda *_args, **_kwargs: fake_source),
    )
    monkeypatch.setattr('app.services.source_service.EvidenceBundleService.sync_claim_bundle', lambda *_args, **_kwargs: None)
    audit_calls = []
    monkeypatch.setattr(
        'app.services.source_service.AdminAuditService.record_event',
        lambda *_args, **kwargs: audit_calls.append(kwargs),
    )

    sources = SourceService.delete_source(
        db,  # type: ignore[arg-type]
        claim_id=claim_id,
        source_id=source_id,
        reviewer_id='reviewer@local',
    )

    assert db.committed == 1
    assert sources == []
    assert len(audit_calls) == 1
    assert audit_calls[0]['action'] == 'claim_source_deleted'


def test_delete_source_blocks_published_claim(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id)
    published_claim = _FakeClaim(claim_id)
    published_claim.is_published = True
    monkeypatch.setattr(
        SourceService,
        '_get_claim_for_source_mutation',
        staticmethod(lambda *_args, **_kwargs: published_claim),
    )

    try:
        SourceService.delete_source(
            db,  # type: ignore[arg-type]
            claim_id=claim_id,
            source_id=source_id,
            reviewer_id='reviewer@local',
        )
        assert False, 'Expected published-claim delete to be blocked'
    except AppError as exc:
        assert exc.code == 'source_delete_not_allowed_for_published_claim'
        assert exc.status_code == 409


def test_delete_source_raises_not_found_when_source_missing(monkeypatch) -> None:
    claim_id = uuid.uuid4()
    source_id = uuid.uuid4()
    db = _FakeDbForAddSource(claim_id)
    monkeypatch.setattr(
        SourceService,
        '_get_claim_for_source_mutation',
        staticmethod(lambda *_args, **_kwargs: _FakeClaim(claim_id)),
    )
    monkeypatch.setattr(
        SourceService,
        '_get_source_for_claim_mutation',
        staticmethod(lambda *_args, **_kwargs: None),
    )

    try:
        SourceService.delete_source(
            db,  # type: ignore[arg-type]
            claim_id=claim_id,
            source_id=source_id,
            reviewer_id='reviewer@local',
        )
        assert False, 'Expected source_not_found'
    except AppError as exc:
        assert exc.code == 'source_not_found'
        assert exc.status_code == 404
