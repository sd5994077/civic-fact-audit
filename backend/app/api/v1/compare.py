from datetime import datetime, timezone
import csv
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.database import get_db
from app.models.enums import RaceStage
from app.schemas.api import CompareResponse, ErrorResponse
from app.services.comparison_service import ComparisonService

router = APIRouter()


def _clamp_probability(value: float, *, field_name: str) -> float:
    if value < 0 or value > 1:
        raise ValueError(f'{field_name} must be between 0 and 1.')
    return value


def _filter_compare_payload(
    payload: CompareResponse,
    *,
    issue_contains: str | None,
    min_confidence: float,
    min_source_quality: float,
) -> CompareResponse:
    needle = (issue_contains or '').strip().lower()
    filtered_issues = []
    for issue in payload.issues:
        tag_match = not needle or needle in issue.issue_tag.lower()
        if not tag_match:
            continue
        issue_items = []
        for item in issue.items:
            if item.confidence < min_confidence:
                continue
            quality_ok = min_source_quality <= 0 or any((src.quality_score or 0) >= min_source_quality for src in item.sources)
            if not quality_ok:
                continue
            issue_items.append(item)
        if issue_items:
            filtered_issues.append(issue.model_copy(update={'items': issue_items}))
    return payload.model_copy(update={'issues': filtered_issues})


def _to_export_rows(payload: CompareResponse) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for issue in payload.issues:
        for item in issue.items:
            source_count = len(item.sources)
            primary_count = sum(1 for src in item.sources if src.source_class.value == 'primary')
            secondary_count = source_count - primary_count
            candidate_count = sum(1 for src in item.sources if src.source_origin.value == 'candidate')
            verification_count = source_count - candidate_count
            warning_codes = sorted({warning.code for warning in issue.warnings + item.warnings})
            rows.append(
                {
                    'state': payload.race.state,
                    'office': payload.race.office,
                    'election_cycle': payload.race.election_cycle,
                    'race_stage': None if payload.race.race_stage is None else payload.race.race_stage.value,
                    'issue_tag': issue.issue_tag,
                    'candidate_id': str(item.candidate_id),
                    'claim_id': str(item.claim_id),
                    'verdict': item.verdict.value,
                    'confidence': round(item.confidence, 4),
                    'citation_notes_present': bool((item.citation_notes or '').strip()),
                    'source_count': source_count,
                    'primary_source_count': primary_count,
                    'secondary_source_count': secondary_count,
                    'candidate_source_count': candidate_count,
                    'verification_source_count': verification_count,
                    'warning_codes': '|'.join(warning_codes),
                }
            )
    return rows


@router.get(
    '/compare',
    response_model=CompareResponse,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}},
)
def compare_office_state(
    state: str = Query(min_length=2, max_length=32, description='Two-letter postal code is recommended (e.g. TX).'),
    office: str = Query(min_length=2, max_length=255, description="Office label (e.g. 'US Senate')."),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100, description='Election cycle year (e.g. 2026).'),
    race_stage: RaceStage | None = Query(default=None, description='Election stage (e.g. primary, general).'),
    stage: RaceStage | None = Query(default=None, description='Alias for race_stage.'),
    limit_issues: int = Query(default=5, ge=1, le=10),
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    ) -> CompareResponse:
    computed_window_start = window_start or datetime(1970, 1, 1, tzinfo=timezone.utc)
    computed_window_end = window_end or datetime.now(timezone.utc)
    selected_stage = race_stage or stage
    return ComparisonService.compare_office_state(
        db=db,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=selected_stage,
        limit_issues=limit_issues,
        window_start=computed_window_start,
        window_end=computed_window_end,
    )


@router.get(
    '/compare/export',
    responses={200: {'content': {'application/json': {}, 'text/csv': {}}}, 400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}},
)
def compare_office_state_export(
    state: str = Query(min_length=2, max_length=32, description='Two-letter postal code is recommended (e.g. TX).'),
    office: str = Query(min_length=2, max_length=255, description="Office label (e.g. 'US Senate')."),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100, description='Election cycle year (e.g. 2026).'),
    race_stage: RaceStage | None = Query(default=None, description='Election stage (e.g. primary, general).'),
    stage: RaceStage | None = Query(default=None, description='Alias for race_stage.'),
    issue_contains: str | None = Query(default=None, max_length=128),
    min_confidence: float = Query(default=0, ge=0, le=1),
    min_source_quality: float = Query(default=0, ge=0, le=1),
    format: str = Query(default='json', pattern='^(json|csv)$'),
    limit_issues: int = Query(default=8, ge=1, le=10),
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    computed_window_start = window_start or datetime(1970, 1, 1, tzinfo=timezone.utc)
    computed_window_end = window_end or datetime.now(timezone.utc)

    try:
        confidence_floor = _clamp_probability(min_confidence, field_name='min_confidence')
        quality_floor = _clamp_probability(min_source_quality, field_name='min_source_quality')
    except ValueError as exc:
        raise AppError('invalid_filter', str(exc), status_code=422)

    selected_stage = race_stage or stage
    compare_payload = ComparisonService.compare_office_state(
        db=db,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=selected_stage,
        limit_issues=limit_issues,
        window_start=computed_window_start,
        window_end=computed_window_end,
    )
    filtered_payload = _filter_compare_payload(
        compare_payload,
        issue_contains=issue_contains,
        min_confidence=confidence_floor,
        min_source_quality=quality_floor,
    )
    rows = _to_export_rows(filtered_payload)

    if format == 'json':
        return {
            'race': filtered_payload.race.model_dump(mode='json'),
            'disclaimer': filtered_payload.race.disclaimer,
            'total_rows': len(rows),
            'rows': rows,
        }

    fieldnames = [
        'state',
        'office',
        'election_cycle',
        'race_stage',
        'issue_tag',
        'candidate_id',
        'claim_id',
        'verdict',
        'confidence',
        'citation_notes_present',
        'source_count',
        'primary_source_count',
        'secondary_source_count',
        'candidate_source_count',
        'verification_source_count',
        'warning_codes',
    ]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    file_suffix = datetime.now(timezone.utc).strftime('%Y%m%d')
    return Response(
        content=buffer.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="compare_export_{file_suffix}.csv"'},
    )
