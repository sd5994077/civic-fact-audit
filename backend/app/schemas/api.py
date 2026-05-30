import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from app.models.enums import (
    AdminJobStatus,
    ClaimStatus,
    EvidenceLinkType,
    ProposalStatus,
    ProposalType,
    RaceStage,
    SourceClass,
    SourceOrigin,
    StatementSourceType,
    Verdict,
)


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorPayload


class CandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    approval_token: str | None = Field(default=None, min_length=1, max_length=4096)
    party: str | None = Field(default=None, max_length=128)
    office: str | None = Field(default=None, max_length=255)
    state: str | None = Field(default=None, max_length=32)
    election_cycle: int | None = Field(default=None, ge=1900, le=2100)
    race_stage: RaceStage | None = None
    is_active: bool = True
    roster_status: str | None = Field(default=None, max_length=64)
    roster_source_url: HttpUrl | None = None
    roster_checked_at: datetime | None = None
    roster_notes: str | None = None


class CandidateUpdate(BaseModel):
    approval_token: str | None = Field(default=None, min_length=1, max_length=4096)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    party: str | None = Field(default=None, max_length=128)
    office: str | None = Field(default=None, max_length=255)
    state: str | None = Field(default=None, max_length=32)
    election_cycle: int | None = Field(default=None, ge=1900, le=2100)
    race_stage: RaceStage | None = None
    is_active: bool | None = None
    roster_status: str | None = Field(default=None, max_length=64)
    roster_source_url: HttpUrl | None = None
    roster_checked_at: datetime | None = None
    roster_notes: str | None = None


class CandidatePublicRead(BaseModel):
    id: uuid.UUID
    name: str
    party: str | None
    office: str | None
    state: str | None
    election_cycle: int | None
    race_stage: RaceStage | None
    created_at: datetime


class CandidateRead(CandidatePublicRead):
    is_active: bool = True
    roster_status: str | None = None
    roster_source_url: str | None = None
    roster_checked_at: datetime | None = None
    roster_notes: str | None = None


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
    is_published: bool = False
    published_at: datetime | None = None
    published_by_reviewer_id: str | None = None
    created_at: datetime


class AddSourceRequest(BaseModel):
    url: HttpUrl
    source_class: SourceClass
    source_origin: SourceOrigin = SourceOrigin.verification
    publisher: str | None = Field(default=None, max_length=255)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    is_direct_candidate_quote: bool = False


class SourceRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    url: str
    source_class: SourceClass
    source_origin: SourceOrigin
    publisher: str | None
    quality_score: float
    created_at: datetime


class EvaluateClaimRequest(BaseModel):
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=10)
    citation_notes: str | None = None
    approval_token: str | None = Field(default=None, min_length=1, max_length=4096)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str
    reviewer_id: str
    role: str


class AuthMeResponse(BaseModel):
    reviewer_id: str
    role: str


class ClaimEvaluationRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    verdict: Verdict
    confidence: float
    rationale: str
    citation_notes: str | None
    reviewer_id: str
    created_at: datetime


class PublishClaimResponse(BaseModel):
    claim_id: uuid.UUID
    is_published: bool
    published_at: datetime | None
    published_by_reviewer_id: str | None
    publish_note: str | None = None


class PublishQueueItem(BaseModel):
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    candidate_name: str
    candidate_party: str | None
    statement_source_url: str
    statement_published_at: datetime
    latest_verdict: Verdict | None
    latest_confidence: float | None
    latest_rationale: str | None
    latest_citation_notes: str | None
    latest_reviewer_id: str | None
    primary_source_count: int
    secondary_source_count: int
    verification_primary_count: int
    verification_secondary_count: int
    publish_gate_passed: bool
    publish_gate_failures: list[str] = Field(default_factory=list)
    is_published: bool = False
    published_at: datetime | None = None
    published_by_reviewer_id: str | None = None


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


class SourceRecommendationRead(BaseModel):
    template_id: str
    rank: int = Field(ge=1)
    source_class: SourceClass
    source_category: Literal['primary_record', 'civic_research', 'fact_check', 'secondary_news']
    source_origin: SourceOrigin
    url: str
    publisher: str
    rationale: str
    validation_status: str | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    final_url: str | None = None
    page_title: str | None = None
    topic_overlap_score: float | None = Field(default=None, ge=0, le=1)
    validation_note: str | None = None
    page_type: Literal[
        'search_results',
        'homepage',
        'section_page',
        'evidence_page',
        'article',
        'pdf_or_report',
        'no_results',
        'unknown',
    ] | None = None
    recommendation_role: Literal[
        'discovery_only',
        'attachable_evidence',
        'candidate_quote_only',
        'rejected',
    ] = 'attachable_evidence'
    discovery_url: str | None = None
    evidence_url: str | None = None
    official_url: str | None = None
    matched_anchors: list[str] = Field(default_factory=list)
    missing_anchors: list[str] = Field(default_factory=list)


class SourceRecommendationResponse(BaseModel):
    claim_id: uuid.UUID
    policy_version: str
    verification_primary_count: int = Field(ge=0)
    verification_secondary_count: int = Field(ge=0)
    missing_source_classes: list[SourceClass] = Field(default_factory=list)
    recommendations: list[SourceRecommendationRead] = Field(default_factory=list)


class BulkSourceAttachItem(BaseModel):
    claim_id: uuid.UUID
    url: HttpUrl
    source_class: SourceClass
    source_origin: SourceOrigin = SourceOrigin.verification
    publisher: str | None = Field(default=None, max_length=255)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    is_direct_candidate_quote: bool = False


class BulkSourceAttachRequest(BaseModel):
    approval_token: str | None = Field(default=None, min_length=1, max_length=4096)
    items: list[BulkSourceAttachItem] = Field(default_factory=list)


class DualControlApprovalTokenRequest(BaseModel):
    action: str = Field(min_length=1, max_length=128)


class DualControlApprovalTokenResponse(BaseModel):
    action: str
    approval_reviewer_id: str
    approval_token: str
    expires_at: datetime


class BulkSourceAttachResultItem(BaseModel):
    claim_id: uuid.UUID
    url: str
    source_class: SourceClass
    source_origin: SourceOrigin
    status: str
    error: ErrorPayload | None = None


class BulkSourceAttachResponse(BaseModel):
    bulk_operation_id: str
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
    candidate_source_count: int
    verification_source_count: int
    missing_source_classes: list[SourceClass]


class ClaimSearchResult(BaseModel):
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    status: ClaimStatus
    fact_checkable: bool
    is_published: bool
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_party: str | None
    candidate_office: str | None
    candidate_state: str | None
    election_cycle: int | None
    race_stage: RaceStage | None
    rank: float


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
    candidate_source_count: int
    verification_source_count: int
    latest_verdict: Verdict | None
    latest_confidence: float | None
    latest_rationale: str | None
    latest_citation_notes: str | None
    latest_reviewer_id: str | None
    latest_evaluated_at: datetime | None
    warnings: list['ParityWarningRead'] = Field(default_factory=list)


ClaimWorkbenchState = Literal[
    'Needs Evidence',
    'Needs Review',
    'Needs Second Reviewer',
    'Ready to Publish',
    'Published',
    'Insufficient Evidence',
]
ClaimWorkbenchSecondReviewerAction = Literal['publish_handoff', 'overwrite_handoff']


class ClaimWorkbenchChecklistItem(BaseModel):
    code: str
    label: str
    passed: bool
    blocking: bool


class ClaimWorkbenchItem(BaseModel):
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
    fact_checkable: bool
    is_published: bool
    published_at: datetime | None = None
    published_by_reviewer_id: str | None = None
    reviewer_state: ClaimWorkbenchState
    second_reviewer_action: ClaimWorkbenchSecondReviewerAction | None = None
    primary_source_count: int
    secondary_source_count: int
    candidate_source_count: int
    verification_source_count: int
    verification_primary_count: int
    verification_secondary_count: int
    latest_verdict: Verdict | None
    latest_confidence: float | None
    latest_rationale: str | None
    latest_citation_notes: str | None
    latest_reviewer_id: str | None
    latest_evaluated_at: datetime | None
    publish_gate_passed: bool
    publish_gate_failures: list[str] = Field(default_factory=list)
    checklist: list[ClaimWorkbenchChecklistItem] = Field(default_factory=list)


class CompareRaceMeta(BaseModel):
    state: str
    office: str
    election_cycle: int | None = None
    race_stage: RaceStage | None = None
    as_of: datetime
    disclaimer: str


class CompareIssueFramePolicy(BaseModel):
    frame_key: str | None = None
    comparison_question: str | None = None
    allowed_candidate_source_classes: list[SourceClass] = Field(default_factory=list)
    allowed_verification_source_classes: list[SourceClass] = Field(default_factory=list)


class ParityWarningRead(BaseModel):
    code: str
    severity: str
    is_confidence_blocking: bool
    message: str


class EvidenceBundleLinkRead(BaseModel):
    id: uuid.UUID
    bundle_id: uuid.UUID
    statement_id: uuid.UUID | None
    source_id: uuid.UUID | None
    url: str
    label: str | None
    link_type: EvidenceLinkType
    source_class: SourceClass | None = None
    source_origin: SourceOrigin | None = None
    publisher: str | None = None
    quality_score: float | None = None
    display_order: int
    created_at: datetime


class ClaimEvidenceBundleRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    is_curated: bool
    stance_links: list[EvidenceBundleLinkRead] = Field(default_factory=list)
    verification_links: list[EvidenceBundleLinkRead] = Field(default_factory=list)


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
    evidence_bundle: ClaimEvidenceBundleRead | None = None
    warnings: list[ParityWarningRead] = Field(default_factory=list)


class CompareIssue(BaseModel):
    issue_tag: str
    frame_policy: CompareIssueFramePolicy | None = None
    warnings: list[ParityWarningRead] = Field(default_factory=list)
    items: list[CompareClaimItem]


class CompareResponse(BaseModel):
    race: CompareRaceMeta
    candidates: list[CandidatePublicRead]
    issues: list[CompareIssue]


class ClaimProposalCreateRequest(BaseModel):
    proposal_type: ProposalType
    proposal_payload: dict[str, Any]


class ClaimProposalRead(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    proposal_type: ProposalType
    status: ProposalStatus
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    proposal_payload: dict[str, Any]
    review_notes: str | None
    claim_context: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ClaimProposalDecisionRequest(BaseModel):
    review_notes: str | None = None


class ClaimProposalApplyResponse(BaseModel):
    proposal_id: uuid.UUID
    status: ProposalStatus
    applied_effect: str


class AdminJobRunCreateRequest(BaseModel):
    job_type: str = Field(min_length=1, max_length=128)
    input_payload: dict[str, Any] = Field(default_factory=dict)


class AdminJobRunRead(BaseModel):
    id: uuid.UUID
    job_type: str
    status: AdminJobStatus
    requested_by_reviewer_id: str
    input_payload: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    attempt_count: int = 0
    max_attempts: int = 3
    next_attempt_at: datetime | None = None
    lease_expires_at: datetime | None = None
    last_error_code: str | None = None
    result_summary: dict[str, Any] | None
    error_details: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class AdminJobInputSchemaRead(BaseModel):
    required_fields: list[str] = Field(default_factory=list)
    allowed_fields: list[str] = Field(default_factory=list)
    field_types: dict[str, str] = Field(default_factory=dict)
    allowed_values: dict[str, list[str]] = Field(default_factory=dict)
    supports_dry_run: bool = False


class AdminJobTypeMetadataRead(BaseModel):
    job_type: str
    description: str | None = None
    input_schema: AdminJobInputSchemaRead


class AdminIntakeProfileRead(BaseModel):
    profile_id: str
    label: str
    state: str
    office: str
    election_cycle: int
    race_stage: str
    statement_batches: list[str] = Field(default_factory=list)


class AdminIntakeProfileDetailRead(AdminIntakeProfileRead):
    roster_seed_module: str
    statement_batch_modules: dict[str, str] = Field(default_factory=dict)
    admin_job_modules: dict[str, str] = Field(default_factory=dict)


class AdminIntakeProfileCreateRequest(BaseModel):
    approval_token: str | None = Field(default=None, min_length=1, max_length=4096)
    profile_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)
    state: str = Field(min_length=1, max_length=32)
    office: str = Field(min_length=1, max_length=255)
    election_cycle: int = Field(ge=1900, le=2100)
    race_stage: RaceStage
    roster_seed_module: str = Field(min_length=1, max_length=255)
    statement_batch_modules: dict[str, str] = Field(default_factory=dict)
    admin_job_modules: dict[str, str] = Field(default_factory=dict)


class AdminIntakeProfileUpdateRequest(BaseModel):
    approval_token: str | None = Field(default=None, min_length=1, max_length=4096)
    label: str | None = Field(default=None, min_length=1, max_length=255)
    state: str | None = Field(default=None, min_length=1, max_length=32)
    office: str | None = Field(default=None, min_length=1, max_length=255)
    election_cycle: int | None = Field(default=None, ge=1900, le=2100)
    race_stage: RaceStage | None = None
    roster_seed_module: str | None = Field(default=None, min_length=1, max_length=255)
    statement_batch_modules: dict[str, str] | None = None
    admin_job_modules: dict[str, str] | None = None


class AdminIntakeProfilesResponse(BaseModel):
    version: str
    profiles: list[AdminIntakeProfileDetailRead] = Field(default_factory=list)


class AdminJobMetadataResponse(BaseModel):
    allowlist_version: str
    intake_profile_version: str
    synchronous_execution: bool = False
    jobs: list[AdminJobTypeMetadataRead] = Field(default_factory=list)
    intake_profiles: list[AdminIntakeProfileRead] = Field(default_factory=list)


class AdminAuditEventRead(BaseModel):
    id: uuid.UUID
    actor_reviewer_id: str
    action: str
    entity_type: str
    entity_id: str
    before_payload: dict[str, Any] | None
    after_payload: dict[str, Any] | None
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class WorkerHealthTerminalFailureSummary(BaseModel):
    id: uuid.UUID
    job_type: str
    attempt_count: int
    max_attempts: int
    last_error_code: str | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ModerationRiskItem(BaseModel):
    reviewer_id: str
    violation_count: int
    last_violation_at: datetime | None = None


class ModerationRiskResponse(BaseModel):
    risks: list[ModerationRiskItem]
    policy_version: str
    window_days: int


class WorkerHealthResponse(BaseModel):
    worker_alive: bool
    queue_depth: int
    due_depth: int
    retry_queue_depth: int
    oldest_queued_age_seconds: float | None = None
    oldest_due_age_seconds: float | None = None
    running_count: int
    terminal_failure_count: int
    recent_terminal_failures: list[WorkerHealthTerminalFailureSummary] = Field(default_factory=list)
    checked_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiKeyRead(BaseModel):
    id: uuid.UUID
    name: str
    created_by_reviewer_id: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyCreatedResponse(ApiKeyRead):
    plaintext_key: str


class PublicClaimRead(BaseModel):
    claim_id: uuid.UUID
    claim_text: str
    issue_tag: str | None
    published_at: datetime
    verdict: Verdict | None
    confidence: float | None
    rationale: str | None
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_party: str | None
    candidate_office: str | None
    candidate_state: str | None
    election_cycle: int | None
    race_stage: RaceStage | None
    statement_source_url: str
    statement_published_at: datetime


class PublicRaceSummaryRead(BaseModel):
    state: str | None
    office: str | None
    election_cycle: int | None
    race_stage: RaceStage | None
    candidate_count: int
    published_claim_count: int
    latest_published_at: datetime | None


class NotificationEventRead(BaseModel):
    id: uuid.UUID
    event_type: str
    claim_id: uuid.UUID | None
    reviewer_id: uuid.UUID
    recipient_email: str
    transport: str
    status: str
    error_message: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class NotificationTestRequest(BaseModel):
    reviewer_id: uuid.UUID
    event_type: Literal[
        'claim_ready_for_review',
        'claim_ready_for_publish',
        'proposal_needs_triage',
    ] = 'claim_ready_for_publish'
