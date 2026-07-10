import uuid
from datetime import datetime, timezone

import pytest

from app.core.errors import AppError
from app.models.entities import ClaimAiDraft, ClaimEvaluation
from app.models.enums import Verdict
from app.services.claim_ai_draft_service import ClaimAiDraftService


class _FakeClaim:
    def __init__(self) -> None:
        self.id = uuid.uuid4()


class _FakeScalars:
    def __init__(self, rows):  # type: ignore[no-untyped-def]
        self._rows = rows

    def all(self):  # type: ignore[no-untyped-def]
        return list(self._rows)

    def first(self):  # type: ignore[no-untyped-def]
        return self._rows[0] if self._rows else None


class _FakeExecute:
    def __init__(self, rows):  # type: ignore[no-untyped-def]
        self._rows = rows

    def scalars(self):  # type: ignore[no-untyped-def]
        return _FakeScalars(self._rows)


class _FakeDb:
    def __init__(self, *, claim, drafts=None, evaluations=None):  # type: ignore[no-untyped-def]
        self._claim = claim
        self._drafts = drafts or []
        self._evaluations = evaluations or []
        self.added: list = []
        self.committed = False
        self.refreshed: list = []

    def get(self, model, obj_id):  # type: ignore[no-untyped-def]
        if self._claim is not None and obj_id == self._claim.id:
            return self._claim
        return None

    def execute(self, stmt):  # type: ignore[no-untyped-def]
        entity = stmt.column_descriptions[0]['entity']
        if entity is ClaimAiDraft:
            return _FakeExecute(self._drafts)
        if entity is ClaimEvaluation:
            return _FakeExecute(self._evaluations)
        return _FakeExecute([])

    def add(self, item):  # type: ignore[no-untyped-def]
        self.added.append(item)

    def commit(self):  # type: ignore[no-untyped-def]
        self.committed = True

    def refresh(self, item):  # type: ignore[no-untyped-def]
        self.refreshed.append(item)


def _draft_payload(**overrides):  # type: ignore[no-untyped-def]
    payload = {
        'claim_id': uuid.uuid4(),
        'suggested_verdict': Verdict.supported,
        'suggested_confidence': 0.9,
        'model_confidence': 0.9,
        'evidence_sufficiency': 0.9,
        'green_lane_ready': False,
        'rationale': 'Roll call record confirms the vote.',
        'citation_notes': 'Senate roll call vote 1151.',
        'model': 'gpt-4o-mini',
        'subclaims': [{'text': 'voted yes', 'judgment': 'supported', 'notes': 'roll call'}],
        'source_assessments': [
            {
                'source_id': uuid.uuid4(),
                'url': 'https://www.senate.gov/roll_call',
                'source_class': 'primary',
                'source_origin': 'verification',
                'publisher': 'U.S. Senate',
                'supports_claim': 'supports',
                'summary': 'Confirms yes vote.',
                'excerpt': 'Yea',
            }
        ],
        'warnings': [],
        'missing_evidence': [],
    }
    payload.update(overrides)
    return payload


def test_record_draft_persists_and_serializes_nested_payload() -> None:
    claim = _FakeClaim()
    db = _FakeDb(claim=claim)
    payload = _draft_payload(claim_id=claim.id)

    draft = ClaimAiDraftService.record_draft(db, claim_id=claim.id, payload=payload)

    assert db.committed is True
    assert draft in db.added
    assert draft.claim_id == claim.id
    assert draft.model == 'gpt-4o-mini'
    assert draft.suggested_verdict == Verdict.supported
    assert draft.subclaims_payload is not None
    assert draft.source_assessments_payload is not None


def test_record_draft_accepts_string_verdict() -> None:
    claim = _FakeClaim()
    db = _FakeDb(claim=claim)
    payload = _draft_payload(claim_id=claim.id, suggested_verdict='mixed')

    draft = ClaimAiDraftService.record_draft(db, claim_id=claim.id, payload=payload)

    assert draft.suggested_verdict == Verdict.mixed


def test_list_draft_history_raises_when_claim_missing() -> None:
    db = _FakeDb(claim=None)
    with pytest.raises(AppError):
        ClaimAiDraftService.list_draft_history(db, claim_id=uuid.uuid4())


def test_list_draft_history_returns_parsed_payload() -> None:
    claim = _FakeClaim()
    draft = ClaimAiDraft(
        id=uuid.uuid4(),
        claim_id=claim.id,
        model='gpt-4o-mini',
        suggested_verdict=Verdict.supported,
        suggested_confidence=0.9,
        model_confidence=0.9,
        evidence_sufficiency=0.9,
        green_lane_ready=False,
        rationale='Rationale text.',
        citation_notes='Citation text.',
        subclaims_payload='[{"text": "a", "judgment": "supported", "notes": "n"}]',
        source_assessments_payload=None,
        warnings_payload=None,
        missing_evidence_payload='["missing_one"]',
    )
    draft.created_at = datetime.now(timezone.utc)
    db = _FakeDb(claim=claim, drafts=[draft])

    history = ClaimAiDraftService.list_draft_history(db, claim_id=claim.id)

    assert len(history) == 1
    assert history[0]['model'] == 'gpt-4o-mini'
    assert history[0]['subclaims'] == [{'text': 'a', 'judgment': 'supported', 'notes': 'n'}]
    assert history[0]['source_assessments'] == []
    assert history[0]['missing_evidence'] == ['missing_one']


def test_get_draft_diff_returns_none_fields_when_no_draft_or_evaluation() -> None:
    claim = _FakeClaim()
    db = _FakeDb(claim=claim)

    diff = ClaimAiDraftService.get_draft_diff(db, claim_id=claim.id)

    assert diff['draft'] is None
    assert diff['evaluation'] is None
    assert diff['verdict_match'] is None
    assert diff['confidence_delta'] is None


def test_get_draft_diff_computes_verdict_and_confidence_delta() -> None:
    claim = _FakeClaim()
    draft = ClaimAiDraft(
        id=uuid.uuid4(),
        claim_id=claim.id,
        model='gpt-4o-mini',
        suggested_verdict=Verdict.supported,
        suggested_confidence=0.9,
        model_confidence=0.9,
        evidence_sufficiency=0.9,
        green_lane_ready=True,
        rationale='Draft rationale.',
        citation_notes='Draft citation.',
        subclaims_payload=None,
        source_assessments_payload=None,
        warnings_payload=None,
        missing_evidence_payload=None,
    )
    draft.created_at = datetime.now(timezone.utc)

    evaluation = ClaimEvaluation(
        id=uuid.uuid4(),
        claim_id=claim.id,
        verdict=Verdict.mixed,
        confidence=0.75,
        rationale='Reviewer rationale.',
        citation_notes='Reviewer citation.',
        reviewer_id='reviewer@local',
    )
    evaluation.created_at = datetime.now(timezone.utc)

    db = _FakeDb(claim=claim, drafts=[draft], evaluations=[evaluation])

    diff = ClaimAiDraftService.get_draft_diff(db, claim_id=claim.id)

    assert diff['verdict_match'] is False
    assert diff['confidence_delta'] == pytest.approx(-0.15)
    assert diff['rationale_changed'] is True
    assert diff['citation_notes_changed'] is True


def test_get_draft_diff_detects_matching_verdict_and_unchanged_text() -> None:
    claim = _FakeClaim()
    draft = ClaimAiDraft(
        id=uuid.uuid4(),
        claim_id=claim.id,
        model='gpt-4o-mini',
        suggested_verdict=Verdict.supported,
        suggested_confidence=0.9,
        model_confidence=0.9,
        evidence_sufficiency=0.9,
        green_lane_ready=True,
        rationale='Same rationale.',
        citation_notes='Same citation.',
        subclaims_payload=None,
        source_assessments_payload=None,
        warnings_payload=None,
        missing_evidence_payload=None,
    )
    draft.created_at = datetime.now(timezone.utc)

    evaluation = ClaimEvaluation(
        id=uuid.uuid4(),
        claim_id=claim.id,
        verdict=Verdict.supported,
        confidence=0.9,
        rationale='Same rationale.',
        citation_notes='Same citation.',
        reviewer_id='reviewer@local',
    )
    evaluation.created_at = datetime.now(timezone.utc)

    db = _FakeDb(claim=claim, drafts=[draft], evaluations=[evaluation])

    diff = ClaimAiDraftService.get_draft_diff(db, claim_id=claim.id)

    assert diff['verdict_match'] is True
    assert diff['confidence_delta'] == 0.0
    assert diff['rationale_changed'] is False
    assert diff['citation_notes_changed'] is False
