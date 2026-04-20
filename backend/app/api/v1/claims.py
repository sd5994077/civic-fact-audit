import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.api import (
    AddSourceRequest,
    ClaimRead,
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
