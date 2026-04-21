import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.models.enums import ClaimStatus, RaceStage, SourceClass, StatementSourceType, Verdict


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorPayload


class CandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    party: str | None = Field(default=None, max_length=128)
    office: str | None = Field(default=None, max_length=255)
    state: str | None = Field(default=None, max_length=32)
    election_cycle: int | None = Field(default=None, ge=1900, le=2100)
    race_stage: RaceStage | None = None


class CandidateRead(BaseModel):
    id: uuid.UUID
    name: str
    party: str | None
    office: str | None
    state: str | None
    election_cycle: int | None
    race_stage: RaceStage | None
    created_at: datetime


class StatementCreate(BaseModel):
    candidate_id: uuid.UUID
    source_type: StatementSourceType
    source_url: HttpUrl
    statement_text: str = Field(min_length=10)
    published_at: datetime


class StatementRead(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    source_type: StatementSourceType
    source_url: str
    statement_text: str
    published_at: datetime
    created_at: datetime


class ExtractClaimsRequest(BaseModel):
    statement_id: uuid.UUID
    max_claims: int = Field(default=10, ge=1, le=25)


class ClaimRead(BaseModel):
    id: uuid.UUID
    statement_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    extraction_confidence: float
    extraction_method: str
    status: ClaimStatus
    created_at: datetime


class AddSourceRequest(BaseModel):
    url: HttpUrl
    source_class: SourceClass
    publisher: str | None = Field(default=None, max_length=255)
    quality_score: float = Field(ge=0, le=1)


class SourceRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    url: str
    source_class: SourceClass
    publisher: str | None
    quality_score: float
    created_at: datetime


class EvaluateClaimRequest(BaseModel):
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=10)
    citation_notes: str | None = None
    reviewer_id: str = Field(min_length=1, max_length=255)


class ClaimEvaluationRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    verdict: Verdict
    confidence: float
    rationale: str
    citation_notes: str | None
    reviewer_id: str
    created_at: datetime


class ScoreBreakdown(BaseModel):
    formula_version: str
    include_insufficient_in_denominator: bool
    evaluated_claims_denominator: int
    supported_claims_numerator: int
    unsupported_claims_numerator: int
    claims_with_minimum_evidence_numerator: int


class CandidateScoreResponse(BaseModel):
    candidate_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    fact_support_rate: float
    false_claim_rate: float
    evidence_sufficiency_rate: float
    composite_score: float | None
    breakdown: ScoreBreakdown


class ExtractClaimsResponse(BaseModel):
    statement_id: uuid.UUID
    created_claims: list[ClaimRead]


class SourceListResponse(BaseModel):
    claim_id: uuid.UUID
    sources: list[SourceRead]


class BulkSourceAttachItem(BaseModel):
    claim_id: uuid.UUID
    url: HttpUrl
    source_class: SourceClass
    publisher: str | None = Field(default=None, max_length=255)
    quality_score: float = Field(ge=0, le=1)


class BulkSourceAttachResultItem(BaseModel):
    claim_id: uuid.UUID
    url: str
    source_class: SourceClass
    status: str
    error: ErrorPayload | None = None


class BulkSourceAttachResponse(BaseModel):
    total: int
    attached: int
    failed: int
    results: list[BulkSourceAttachResultItem]


class EvidenceQueueItem(BaseModel):
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    status: ClaimStatus
    statement_source_url: str
    statement_published_at: datetime
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_party: str | None
    candidate_office: str | None
    candidate_state: str | None
    election_cycle: int | None
    race_stage: RaceStage | None
    primary_source_count: int
    secondary_source_count: int
    missing_source_classes: list[SourceClass]


class ReviewQueueItem(BaseModel):
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    status: ClaimStatus
    statement_source_url: str
    statement_published_at: datetime
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_party: str | None
    candidate_office: str | None
    candidate_state: str | None
    election_cycle: int | None
    race_stage: RaceStage | None
    primary_source_count: int
    secondary_source_count: int
    latest_verdict: Verdict | None
    latest_confidence: float | None
    latest_rationale: str | None
    latest_citation_notes: str | None
    latest_reviewer_id: str | None
    latest_evaluated_at: datetime | None


class CompareRaceMeta(BaseModel):
    state: str
    office: str
    election_cycle: int | None = None
    race_stage: RaceStage | None = None
    as_of: datetime
    disclaimer: str


class CompareClaimItem(BaseModel):
    candidate_id: uuid.UUID
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    statement_source_url: str
    statement_published_at: datetime
    verdict: Verdict
    confidence: float
    rationale: str
    citation_notes: str | None
    sources: list[SourceRead]


class CompareIssue(BaseModel):
    issue_tag: str
    items: list[CompareClaimItem]


class CompareResponse(BaseModel):
    race: CompareRaceMeta
    candidates: list[CandidateRead]
    issues: list[CompareIssue]
