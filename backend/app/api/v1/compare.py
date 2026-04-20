from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import CompareResponse, ErrorResponse
from app.services.comparison_service import ComparisonService

router = APIRouter()


@router.get(
    '/compare',
    response_model=CompareResponse,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}},
)
def compare_office_state(
    state: str = Query(min_length=2, max_length=32, description='Two-letter postal code is recommended (e.g. TX).'),
    office: str = Query(min_length=2, max_length=255, description="Office label (e.g. 'US Senate')."),
    limit_issues: int = Query(default=5, ge=1, le=10),
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CompareResponse:
    computed_window_start = window_start or datetime(1970, 1, 1, tzinfo=timezone.utc)
    computed_window_end = window_end or datetime.now(timezone.utc)
    return ComparisonService.compare_office_state(
        db=db,
        state=state,
        office=office,
        limit_issues=limit_issues,
        window_start=computed_window_start,
        window_end=computed_window_end,
    )

