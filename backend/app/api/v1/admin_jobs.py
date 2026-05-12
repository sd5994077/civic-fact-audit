import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import AdminJobStatus
from app.schemas.api import AdminJobMetadataResponse, AdminJobRunCreateRequest, AdminJobRunRead, ErrorResponse
from app.services.admin_job_service import AdminJobService
from app.services.auth_dependency_service import require_admin
from app.services.auth_service import AuthIdentity

router = APIRouter(prefix='/admin/jobs')


@router.post(
    '',
    response_model=AdminJobRunRead,
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 422: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
def create_admin_job(
    payload: AdminJobRunCreateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> AdminJobRunRead:
    job_run = AdminJobService.create_and_run_job(db, payload, requested_by_reviewer_id=identity.reviewer_id)
    return AdminJobRunRead.model_validate(job_run)


@router.get(
    '/metadata',
    response_model=AdminJobMetadataResponse,
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}},
)
def get_admin_job_metadata(identity: AuthIdentity = Depends(require_admin)) -> AdminJobMetadataResponse:
    _ = identity
    metadata = AdminJobService.get_job_metadata()
    return AdminJobMetadataResponse.model_validate(metadata)


@router.get(
    '',
    response_model=list[AdminJobRunRead],
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 422: {'model': ErrorResponse}},
)
def list_admin_jobs(
    status: AdminJobStatus | None = Query(default=None),
    job_type: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> list[AdminJobRunRead]:
    _ = identity
    rows = AdminJobService.list_job_runs(db, status=status, job_type=job_type, limit=limit)
    return [AdminJobRunRead.model_validate(row) for row in rows]


@router.get(
    '/{job_run_id}',
    response_model=AdminJobRunRead,
    responses={401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def get_admin_job(
    job_run_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> AdminJobRunRead:
    _ = identity
    row = AdminJobService.get_job_run(db, job_run_id)
    return AdminJobRunRead.model_validate(row)
