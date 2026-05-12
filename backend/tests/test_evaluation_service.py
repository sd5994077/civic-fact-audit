from app.models.enums import RaceStage
from app.services.evaluation_service import EvaluationService
from app.models.enums import Verdict
from unittest.mock import patch
import uuid

from app.core.errors import AppError


class _FakeClaim:
    def __init__(self, *, fact_checkable: bool = True) -> None:
        self.fact_checkable = fact_checkable
        self.id = 'claim-id'


class _FakeEval:
    def __init__(self, *, verdict: Verdict = Verdict.supported, rationale: str = 'rationale', citation_notes: str = 'notes') -> None:
        self.verdict = verdict
        self.rationale = rationale
        self.citation_notes = citation_notes


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
    assert 'claims.fact_checkable' in compiled
    assert 'sources.source_origin' in compiled
    assert 'sources.source_class' in compiled
    assert 'sources.policy_flagged' in compiled
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


def test_publish_gate_failures_empty_when_all_rules_pass() -> None:
    claim = _FakeClaim(fact_checkable=True)
    latest_eval = _FakeEval(verdict=Verdict.supported, rationale='Looks good', citation_notes='Cited.')
    with patch('app.services.evaluation_service.SourceService.has_source_class', return_value=True):
        failures = EvaluationService._publish_gate_failures(None, claim, latest_eval)  # type: ignore[arg-type]
    assert failures == []


def test_publish_gate_failures_include_expected_rules() -> None:
    claim = _FakeClaim(fact_checkable=False)
    latest_eval = _FakeEval(verdict=Verdict.insufficient, rationale=' ', citation_notes=' ')
    with patch('app.services.evaluation_service.SourceService.has_source_class', return_value=False):
        failures = EvaluationService._publish_gate_failures(None, claim, latest_eval)  # type: ignore[arg-type]
    assert EvaluationService._PUBLISH_GATE_FACT_CHECKABLE in failures
    assert EvaluationService._PUBLISH_GATE_VERDICT in failures
    assert EvaluationService._PUBLISH_GATE_RATIONALE in failures
    assert EvaluationService._PUBLISH_GATE_CITATION_NOTES in failures
    assert EvaluationService._PUBLISH_GATE_VERIFICATION_PRIMARY in failures
    assert EvaluationService._PUBLISH_GATE_VERIFICATION_SECONDARY in failures


def test_publish_gate_failures_include_moderation_policy_rule() -> None:
    claim = _FakeClaim(fact_checkable=True)
    latest_eval = _FakeEval(
        verdict=Verdict.supported,
        rationale='You should vote for this candidate.',
        citation_notes='Voters should choose this person.',
    )
    with patch('app.services.evaluation_service.SourceService.has_source_class', return_value=True):
        failures = EvaluationService._publish_gate_failures(None, claim, latest_eval)  # type: ignore[arg-type]
    assert EvaluationService._PUBLISH_GATE_MODERATION_POLICY in failures
    assert failures.count(EvaluationService._PUBLISH_GATE_MODERATION_POLICY) == 1


def test_publish_claim_moderation_failure_returns_violation_details(monkeypatch) -> None:
    claim_id = uuid.uuid4()

    class _Db:
        def get(self, _model, id_):  # type: ignore[no-untyped-def]
            if id_ == claim_id:
                return _FakeClaim(fact_checkable=True)
            return None

    latest_eval = _FakeEval(
        verdict=Verdict.supported,
        rationale='You should vote for Candidate A.',
        citation_notes='Vote against Candidate B.',
    )
    monkeypatch.setattr('app.services.evaluation_service.EvaluationService._latest_evaluation', lambda _db, _id: latest_eval)
    monkeypatch.setattr(
        'app.services.evaluation_service.SourceService.has_source_class',
        lambda _db, _claim_id, _source_class, source_origin=None: True,
    )
    try:
        EvaluationService.publish_claim(_Db(), claim_id, approver_id='admin@local')  # type: ignore[arg-type]
        assert False, 'Expected publish_gate_moderation_failure'
    except AppError as exc:
        assert exc.code == 'publish_gate_moderation_failure'
        assert 'latest_evaluation_moderation_policy_violation' in exc.details['failed_checks']
        violations = exc.details.get('moderation_violations', [])
        assert len(violations) == 2
        assert {item['rejection_field'] for item in violations} == {'rationale', 'citation_notes'}
