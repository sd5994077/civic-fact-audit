import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import RaceStage
from app.schemas.api import (
    AddSourceRequest,
    BulkSourceAttachItem,
    BulkSourceAttachResponse,
    ClaimRead,
    EvidenceQueueItem,
    ErrorResponse,
    ExtractClaimsRequest,
    ExtractClaimsResponse,
    SourceListResponse,
    SourceRead,
)
from app.services.claim_extraction_service import ClaimExtractionService
from app.services.source_service import SourceService

router = APIRouter(prefix='/claims')


@router.post('/extract', response_model=ExtractClaimsResponse, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}})
def extract_claims(payload: ExtractClaimsRequest, db: Session = Depends(get_db)) -> ExtractClaimsResponse:
    claims = ClaimExtractionService.extract_claims(db, payload.statement_id, payload.max_claims)
    return ExtractClaimsResponse(
        statement_id=payload.statement_id,
        created_claims=[ClaimRead.model_validate(claim, from_attributes=True) for claim in claims],
    )


@router.post('/{claim_id}/sources', response_model=SourceListResponse, responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}})
def add_source(claim_id: uuid.UUID, payload: AddSourceRequest, db: Session = Depends(get_db)) -> SourceListResponse:
    sources = SourceService.add_source(db, claim_id, payload)
    return SourceListResponse(
        claim_id=claim_id,
        sources=[SourceRead.model_validate(source, from_attributes=True) for source in sources],
    )


@router.post(
    '/sources/bulk',
    response_model=BulkSourceAttachResponse,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}},
)
def add_sources_bulk(payload: list[BulkSourceAttachItem], db: Session = Depends(get_db)) -> BulkSourceAttachResponse:
    response = SourceService.attach_sources_bulk(db, payload)
    return BulkSourceAttachResponse.model_validate(response)


@router.get(
    '/evidence-queue',
    response_model=list[EvidenceQueueItem],
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}},
)
def evidence_queue(
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    include_only_missing: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[EvidenceQueueItem]:
    rows = SourceService.list_evidence_queue(
        db,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
        include_only_missing=include_only_missing,
        limit=limit,
    )
    return [EvidenceQueueItem.model_validate(row) for row in rows]
