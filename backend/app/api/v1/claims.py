import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.rate_limiter import ADMIN_WRITE_LIMIT, EXTRACT_LIMIT, WRITE_STANDARD_LIMIT, ip_rate_limit
from app.db.database import get_db
from app.models.enums import ClaimStatus, ProposalStatus, ProposalType, RaceStage
from app.schemas.api import (
    AddSourceRequest,
    BulkSourceAttachRequest,
    BulkSourceAttachResponse,
    ClaimProposalApplyResponse,
    ClaimProposalCreateRequest,
    ClaimProposalDecisionRequest,
    ClaimProposalRead,
    ClaimRead,
    ClaimSearchResult,
    EvidenceQueueItem,
    ErrorResponse,
    ExtractClaimsRequest,
    ExtractClaimsResponse,
    SourceListResponse,
    SourceRead,
)
from app.services.auth_dependency_service import require_reviewer_or_admin
from app.services.auth_service import AuthIdentity, AuthService
from app.services.claim_extraction_service import ClaimExtractionService
from app.services.proposal_service import ProposalService
from app.services.search_service import SearchService
from app.services.source_service import SourceService

router = APIRouter(prefix='/claims')


@router.post(
    '/extract',
    response_model=ExtractClaimsResponse,
    responses={
        400: {'model': ErrorResponse},
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def extract_claims(
    payload: ExtractClaimsRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(EXTRACT_LIMIT, endpoint_key='extract_claims')),
) -> ExtractClaimsResponse:
    _ = identity
    claims = ClaimExtractionService.extract_claims(db, payload.statement_id, payload.max_claims)
    return ExtractClaimsResponse(
        statement_id=payload.statement_id,
        created_claims=[ClaimRead.model_validate(claim, from_attributes=True) for claim in claims],
    )


@router.post(
    '/{claim_id}/sources',
    response_model=SourceListResponse,
    responses={
        400: {'model': ErrorResponse},
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def add_source(
    claim_id: uuid.UUID,
    payload: AddSourceRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='add_source')),
) -> SourceListResponse:
    _ = identity
    sources = SourceService.add_source(db, claim_id, payload)
    return SourceListResponse(
        claim_id=claim_id,
        sources=[SourceRead.model_validate(source, from_attributes=True) for source in sources],
    )


@router.post(
    '/sources/bulk',
    response_model=BulkSourceAttachResponse,
    responses={
        400: {'model': ErrorResponse},
        401: {'model': ErrorResponse},
        403: {'model': ErrorResponse},
        404: {'model': ErrorResponse},
        409: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        429: {'model': ErrorResponse},
    },
)
def add_sources_bulk(
    payload: BulkSourceAttachRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='sources_bulk')),
) -> BulkSourceAttachResponse:
    approval_reviewer_id: str | None = None
    if payload.approval_token is not None:
        approval_identity = AuthService.identity_from_dual_control_approval_token(
            db,
            payload.approval_token,
            expected_action='bulk_attach_verification_sources',
        )
        approval_reviewer_id = approval_identity.reviewer_id
    response = SourceService.attach_sources_bulk(
        db,
        approval_reviewer_id=approval_reviewer_id,
        applying_reviewer_id=identity.reviewer_id,
        items=payload.items,
    )
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


@router.get(
    '/search',
    response_model=list[ClaimSearchResult],
    responses={400: {'model': ErrorResponse}, 401: {'model': ErrorResponse}, 403: {'model': ErrorResponse}, 429: {'model': ErrorResponse}},
)
def search_claims(
    q: str = Query(min_length=2, max_length=256),
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    status: ClaimStatus | None = Query(default=None),
    fact_checkable: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(WRITE_STANDARD_LIMIT, endpoint_key='search_claims')),
) -> list[ClaimSearchResult]:
    _ = identity
    rows = SearchService.search_claims(
        db,
        q=q,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
        status=status,
        fact_checkable=fact_checkable,
        limit=limit,
    )
    return [ClaimSearchResult.model_validate(row) for row in rows]


@router.post(
    '/{claim_id}/proposals',
    response_model=ClaimProposalRead,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 422: {'model': ErrorResponse}, 429: {'model': ErrorResponse}},
)
def create_claim_proposal(
    claim_id: uuid.UUID,
    payload: ClaimProposalCreateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(WRITE_STANDARD_LIMIT, endpoint_key='create_proposal')),
) -> ClaimProposalRead:
    proposal = ProposalService.create_proposal(db, claim_id, payload, proposed_by=identity.reviewer_id)
    return ClaimProposalRead.model_validate(ProposalService._to_read_model(proposal))


@router.get(
    '/proposals',
    response_model=list[ClaimProposalRead],
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 422: {'model': ErrorResponse}},
)
def list_claim_proposals(
    status: str | None = Query(default=None),
    proposal_type: str | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=32),
    office: str | None = Query(default=None, min_length=2, max_length=255),
    election_cycle: int | None = Query(default=None, ge=1900, le=2100),
    race_stage: RaceStage | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
) -> list[ClaimProposalRead]:
    _ = identity
    try:
        parsed_status = ProposalStatus(status) if status is not None else None
    except ValueError as exc:
        raise AppError('invalid_filter', 'Invalid proposal status filter.', status_code=422) from exc
    try:
        parsed_type = ProposalType(proposal_type) if proposal_type is not None else None
    except ValueError as exc:
        raise AppError('invalid_filter', 'Invalid proposal type filter.', status_code=422) from exc
    rows = ProposalService.list_proposals(
        db,
        status=parsed_status,
        proposal_type=parsed_type,
        state=state,
        office=office,
        election_cycle=election_cycle,
        race_stage=race_stage,
        limit=limit,
    )
    return [ClaimProposalRead.model_validate(row) for row in rows]


@router.post(
    '/proposals/{proposal_id}/approve',
    response_model=ClaimProposalRead,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 429: {'model': ErrorResponse}},
)
def approve_claim_proposal(
    proposal_id: uuid.UUID,
    payload: ClaimProposalDecisionRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='approve_proposal')),
) -> ClaimProposalRead:
    proposal = ProposalService.approve_proposal(
        db,
        proposal_id,
        reviewer_id=identity.reviewer_id,
        review_notes=payload.review_notes,
    )
    return ClaimProposalRead.model_validate(ProposalService._to_read_model(proposal))


@router.post(
    '/proposals/{proposal_id}/reject',
    response_model=ClaimProposalRead,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 429: {'model': ErrorResponse}},
)
def reject_claim_proposal(
    proposal_id: uuid.UUID,
    payload: ClaimProposalDecisionRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='reject_proposal')),
) -> ClaimProposalRead:
    proposal = ProposalService.reject_proposal(
        db,
        proposal_id,
        reviewer_id=identity.reviewer_id,
        review_notes=payload.review_notes,
    )
    return ClaimProposalRead.model_validate(ProposalService._to_read_model(proposal))


@router.post(
    '/proposals/{proposal_id}/apply',
    response_model=ClaimProposalApplyResponse,
    responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}, 409: {'model': ErrorResponse}, 422: {'model': ErrorResponse}, 429: {'model': ErrorResponse}},
)
def apply_claim_proposal(
    proposal_id: uuid.UUID,
    payload: ClaimProposalDecisionRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_reviewer_or_admin),
    _rl: None = Depends(ip_rate_limit(ADMIN_WRITE_LIMIT, endpoint_key='apply_proposal')),
) -> ClaimProposalApplyResponse:
    result = ProposalService.apply_proposal(
        db,
        proposal_id,
        reviewer_id=identity.reviewer_id,
        review_notes=payload.review_notes,
    )
    return ClaimProposalApplyResponse(
        proposal_id=result['proposal'].id,
        status=result['proposal'].status,
        applied_effect=result['applied_effect'],
    )
