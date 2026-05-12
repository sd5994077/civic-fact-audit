from datetime import datetime, timezone
import uuid

from app.api.v1.compare import _filter_compare_payload, _to_export_rows
from app.models.enums import RaceStage, SourceClass, SourceOrigin, Verdict
from app.schemas.api import (
    CandidateRead,
    CompareClaimItem,
    CompareIssue,
    CompareRaceMeta,
    CompareResponse,
    ParityWarningRead,
    SourceRead,
)


def _build_compare_response() -> CompareResponse:
    candidate = CandidateRead(
        id=uuid.uuid4(),
        name='Candidate A',
        party='Independent',
        office='US Senate',
        state='TX',
        election_cycle=2026,
        race_stage=RaceStage.primary,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    item = CompareClaimItem(
        candidate_id=candidate.id,
        claim_id=uuid.uuid4(),
        claim_text='Claim text',
        issue_tag='Energy',
        statement_source_url='https://example.com/statement',
        statement_published_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
        verdict=Verdict.supported,
        confidence=0.92,
        rationale='Rationale text',
        citation_notes='Has citations',
        sources=[
            SourceRead(
                id=uuid.uuid4(),
                claim_id=uuid.uuid4(),
                url='https://example.com/source-primary',
                source_class=SourceClass.primary,
                source_origin=SourceOrigin.verification,
                publisher='Publisher 1',
                quality_score=0.95,
                created_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
            ),
            SourceRead(
                id=uuid.uuid4(),
                claim_id=uuid.uuid4(),
                url='https://example.com/source-secondary',
                source_class=SourceClass.secondary,
                source_origin=SourceOrigin.candidate,
                publisher='Publisher 2',
                quality_score=0.4,
                created_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
            ),
        ],
        warnings=[
            ParityWarningRead(
                code='missing_verification_secondary',
                severity='critical',
                is_confidence_blocking=True,
                message='Missing secondary verification source.',
            )
        ],
    )
    return CompareResponse(
        race=CompareRaceMeta(
            state='TX',
            office='US Senate',
            election_cycle=2026,
            race_stage=RaceStage.primary,
            as_of=datetime(2026, 5, 1, tzinfo=timezone.utc),
            disclaimer='Disclaimer',
        ),
        candidates=[candidate],
        issues=[
            CompareIssue(
                issue_tag='Energy',
                warnings=[
                    ParityWarningRead(
                        code='source_class_imbalance_primary',
                        severity='warning',
                        is_confidence_blocking=False,
                        message='Imbalance.',
                    )
                ],
                items=[item],
            )
        ],
    )


def test_filter_compare_payload_applies_thresholds() -> None:
    payload = _build_compare_response()
    filtered = _filter_compare_payload(
        payload,
        issue_contains='ener',
        min_confidence=0.9,
        min_source_quality=0.9,
    )
    assert len(filtered.issues) == 1
    assert len(filtered.issues[0].items) == 1

    filtered_out = _filter_compare_payload(
        payload,
        issue_contains='ener',
        min_confidence=0.95,
        min_source_quality=0.9,
    )
    assert len(filtered_out.issues) == 0


def test_to_export_rows_includes_traceability_fields() -> None:
    rows = _to_export_rows(_build_compare_response())
    assert len(rows) == 1
    row = rows[0]
    assert row['state'] == 'TX'
    assert row['office'] == 'US Senate'
    assert row['election_cycle'] == 2026
    assert row['race_stage'] == 'primary'
    assert row['issue_tag'] == 'Energy'
    assert row['verdict'] == 'supported'
    assert row['confidence'] == 0.92
    assert row['citation_notes_present'] is True
    assert row['source_count'] == 2
    assert row['primary_source_count'] == 1
    assert row['secondary_source_count'] == 1
    assert row['candidate_source_count'] == 1
    assert row['verification_source_count'] == 1
    assert 'missing_verification_secondary' in row['warning_codes']


def test_compare_race_disclaimer_uses_non_recommendation_language() -> None:
    payload = _build_compare_response()
    assert 'endorsement' not in payload.race.disclaimer.lower() or 'not an endorsement' in payload.race.disclaimer.lower()
