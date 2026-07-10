import uuid
from datetime import datetime, timezone

import pytest

from app.core.errors import AppError
from app.models.enums import SourceClass, SourceOrigin
from app.services.review_draft_service import ReviewDraftService, _SourceSnapshot


class _FakeCandidate:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.name = 'Candidate A'
        self.party = 'Independent'
        self.office = 'US Senate'
        self.state = 'TX'
        self.election_cycle = 2026
        self.race_stage = None


class _FakeStatement:
    def __init__(self, candidate_id: uuid.UUID) -> None:
        self.id = uuid.uuid4()
        self.candidate_id = candidate_id
        self.source_url = 'https://example.com/statement'


class _FakeClaim:
    def __init__(self, statement_id: uuid.UUID) -> None:
        self.id = uuid.uuid4()
        self.statement_id = statement_id
        self.claim_text = 'Candidate supported a major tax change.'
        self.issue_tag = 'taxes'
        self.fact_checkable = True


class _FakeSource:
    def __init__(self, *, source_origin: SourceOrigin = SourceOrigin.verification, source_class: SourceClass = SourceClass.primary) -> None:
        self.id = uuid.uuid4()
        self.url = 'https://example.com/source'
        self.source_class = source_class
        self.source_origin = source_origin
        self.policy_flagged = False
        self.publisher = 'Example Publisher'
        self.created_at = datetime.now(timezone.utc)


class _FakeScalars:
    def __init__(self, rows):  # type: ignore[no-untyped-def]
        self._rows = rows

    def all(self):  # type: ignore[no-untyped-def]
        return self._rows


class _FakeExecute:
    def __init__(self, rows):  # type: ignore[no-untyped-def]
        self._rows = rows

    def scalars(self):  # type: ignore[no-untyped-def]
        return _FakeScalars(self._rows)


class _FakeDb:
    def __init__(self, *, claim, statement, candidate, sources):  # type: ignore[no-untyped-def]
        self._claim = claim
        self._statement = statement
        self._candidate = candidate
        self._sources = sources

    def get(self, model, obj_id):  # type: ignore[no-untyped-def]
        from app.models.entities import Candidate, Claim, Statement

        if model is Claim and obj_id == self._claim.id:
            return self._claim
        if model is Statement and obj_id == self._statement.id:
            return self._statement
        if model is Candidate and obj_id == self._candidate.id:
            return self._candidate
        return None

    def execute(self, _stmt):  # type: ignore[no-untyped-def]
        return _FakeExecute(self._sources)


def test_generate_review_draft_requires_verification_sources() -> None:
    candidate = _FakeCandidate()
    statement = _FakeStatement(candidate.id)
    claim = _FakeClaim(statement.id)
    candidate_only_source = _FakeSource(source_origin=SourceOrigin.candidate)
    db = _FakeDb(claim=claim, statement=statement, candidate=candidate, sources=[candidate_only_source])

    try:
        ReviewDraftService.generate_review_draft(db, claim_id=claim.id)  # type: ignore[arg-type]
        assert False, 'Expected review_draft_requires_verification_sources'
    except AppError as exc:
        assert exc.code == 'review_draft_requires_verification_sources'


def test_generate_review_draft_returns_prefill_packet(monkeypatch) -> None:
    candidate = _FakeCandidate()
    statement = _FakeStatement(candidate.id)
    claim = _FakeClaim(statement.id)
    verification_source = _FakeSource(source_origin=SourceOrigin.verification, source_class=SourceClass.primary)
    db = _FakeDb(claim=claim, statement=statement, candidate=candidate, sources=[verification_source])

    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._fetch_source_snapshot',
        lambda _source: _SourceSnapshot(
            source_id=verification_source.id,
            url=verification_source.url,
            source_class=verification_source.source_class,
            source_origin=verification_source.source_origin,
            publisher=verification_source.publisher,
            fetch_status='ok',
            content_excerpt='Evidence excerpt',
            content_type='text/html',
        ),
    )
    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._generate_with_openai',
        lambda _payload: {
            'suggested_verdict': 'supported',
            'suggested_confidence': 0.92,
            'model_confidence': 0.94,
            'evidence_sufficiency': 0.91,
            'green_lane_ready': True,
            'rationale': 'The record supports the specific vote action in the claim.',
            'citation_notes': 'Primary source confirms the vote; secondary context supports interpretation.',
            'subclaims': [{'text': 'Candidate voted for the bill.', 'judgment': 'supported', 'notes': 'Roll call support.'}],
            'source_assessments': [
                {
                    'url': verification_source.url,
                    'source_class': 'primary',
                    'source_origin': 'verification',
                    'publisher': verification_source.publisher,
                    'supports_claim': 'supports',
                    'summary': 'Direct record supports claim language.',
                    'excerpt': 'Candidate voted yea.',
                }
            ],
            'warnings': [],
            'missing_evidence': [],
        },
    )
    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._generate_with_anthropic',
        lambda _payload: pytest.fail('Escalation should not run without secondary verification evidence.'),
    )

    payload = ReviewDraftService.generate_review_draft(db, claim_id=claim.id)  # type: ignore[arg-type]
    assert payload['suggested_verdict'].value == 'supported'
    assert payload['green_lane_ready'] is False  # no secondary verification source attached
    assert 'verification_secondary_source_required' in payload['missing_evidence']


def test_validate_fetch_url_blocks_localhost() -> None:
    try:
        ReviewDraftService._validate_fetch_url('http://localhost/internal')
        assert False, 'Expected review_draft_source_url_blocked'
    except AppError as exc:
        assert exc.code == 'review_draft_source_url_blocked'


def test_validate_fetch_url_blocks_unallowlisted_domain() -> None:
    try:
        ReviewDraftService._validate_fetch_url('https://example.com/path')
        assert False, 'Expected review_draft_source_url_not_allowlisted'
    except AppError as exc:
        assert exc.code == 'review_draft_source_url_not_allowlisted'


def test_generate_review_draft_requires_readable_source(monkeypatch) -> None:
    candidate = _FakeCandidate()
    statement = _FakeStatement(candidate.id)
    claim = _FakeClaim(statement.id)
    verification_source = _FakeSource(source_origin=SourceOrigin.verification, source_class=SourceClass.primary)
    db = _FakeDb(claim=claim, statement=statement, candidate=candidate, sources=[verification_source])

    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._fetch_source_snapshot',
        lambda _source: _SourceSnapshot(
            source_id=verification_source.id,
            url=verification_source.url,
            source_class=verification_source.source_class,
            source_origin=verification_source.source_origin,
            publisher=verification_source.publisher,
            fetch_status='request_error',
            content_excerpt='',
            content_type=None,
        ),
    )
    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._generate_with_openai',
        lambda _payload: {},
    )

    try:
        ReviewDraftService.generate_review_draft(db, claim_id=claim.id)  # type: ignore[arg-type]
        assert False, 'Expected review_draft_source_fetch_failed'
    except AppError as exc:
        assert exc.code == 'review_draft_source_fetch_failed'


def test_generate_review_draft_accepts_truncated_readable_source(monkeypatch) -> None:
    candidate = _FakeCandidate()
    statement = _FakeStatement(candidate.id)
    claim = _FakeClaim(statement.id)
    primary_source = _FakeSource(source_origin=SourceOrigin.verification, source_class=SourceClass.primary)
    secondary_source = _FakeSource(source_origin=SourceOrigin.verification, source_class=SourceClass.secondary)
    db = _FakeDb(claim=claim, statement=statement, candidate=candidate, sources=[primary_source, secondary_source])

    def _snapshot(source):  # type: ignore[no-untyped-def]
        return _SourceSnapshot(
            source_id=source.id,
            url=source.url,
            source_class=source.source_class,
            source_origin=source.source_origin,
            publisher=source.publisher,
            fetch_status='truncated',
            content_excerpt='Readable evidence excerpt from a long article.',
            content_type='text/html',
        )

    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._fetch_source_snapshot',
        _snapshot,
    )
    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._generate_with_openai',
        lambda _payload: {
            'suggested_verdict': 'mixed',
            'suggested_confidence': 0.86,
            'model_confidence': 0.88,
            'evidence_sufficiency': 0.82,
            'green_lane_ready': False,
            'rationale': 'Readable source excerpts support drafting a cautious reviewer summary.',
            'citation_notes': 'Attached sources were readable but truncated during draft fetch.',
            'subclaims': [{'text': 'Claim contains a verifiable budget assertion.', 'judgment': 'mixed', 'notes': 'Readable source context exists.'}],
            'source_assessments': [
                {
                    'url': primary_source.url,
                    'source_class': 'primary',
                    'source_origin': 'verification',
                    'publisher': primary_source.publisher,
                    'supports_claim': 'mixed',
                    'summary': 'Readable but truncated source content was available.',
                    'excerpt': 'Readable evidence excerpt.',
                }
            ],
            'warnings': [],
            'missing_evidence': [],
        },
    )

    payload = ReviewDraftService.generate_review_draft(db, claim_id=claim.id)  # type: ignore[arg-type]
    assert payload['suggested_verdict'].value == 'mixed'
    # truncated means content was fetched (just cut at the char limit) — not a warning condition.
    # Confidence should not be penalised and no fetch warning should appear.
    assert not any(item['code'] in ('source_fetch_incomplete', 'source_fetch_error', 'source_fetch_unreachable') for item in payload['warnings'])
    assert payload['model_confidence'] == pytest.approx(0.88)


def test_generate_review_draft_downgrades_unmatched_source_assessments(monkeypatch) -> None:
    candidate = _FakeCandidate()
    statement = _FakeStatement(candidate.id)
    claim = _FakeClaim(statement.id)
    verification_source = _FakeSource(source_origin=SourceOrigin.verification, source_class=SourceClass.primary)
    db = _FakeDb(claim=claim, statement=statement, candidate=candidate, sources=[verification_source])

    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._fetch_source_snapshot',
        lambda _source: _SourceSnapshot(
            source_id=verification_source.id,
            url=verification_source.url,
            source_class=verification_source.source_class,
            source_origin=verification_source.source_origin,
            publisher=verification_source.publisher,
            fetch_status='ok',
            content_excerpt='Safe text',
            content_type='text/html',
        ),
    )
    monkeypatch.setattr(
        'app.services.review_draft_service.ReviewDraftService._generate_with_openai',
        lambda _payload: {
            'suggested_verdict': 'supported',
            'suggested_confidence': 0.95,
            'model_confidence': 0.95,
            'evidence_sufficiency': 0.95,
            'green_lane_ready': True,
            'rationale': 'Primary source supports a narrow factual claim.',
            'citation_notes': 'Source reviewed and cross-checked.',
            'subclaims': [{'text': 'Narrow factual claim.', 'judgment': 'supported', 'notes': 'Supported by source.'}],
            'source_assessments': [
                {
                    'url': 'https://different.example.com/not-attached',
                    'source_class': 'primary',
                    'source_origin': 'verification',
                    'publisher': 'Different',
                    'supports_claim': 'supports',
                    'summary': 'Claims support but URL is not attached.',
                    'excerpt': 'Untrusted mapping.',
                }
            ],
            'warnings': [],
            'missing_evidence': [],
        },
    )

    payload = ReviewDraftService.generate_review_draft(db, claim_id=claim.id)  # type: ignore[arg-type]
    assert payload['green_lane_ready'] is False
    assert payload['model_confidence'] <= 0.35
    assert any(item['code'] == 'unmatched_source_assessments' for item in payload['warnings'])
