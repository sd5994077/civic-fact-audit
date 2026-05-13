import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import (
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


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Candidate(TimestampMixin, Base):
    __tablename__ = 'candidates'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    party: Mapped[str | None] = mapped_column(String(128), nullable=True)
    office: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    election_cycle: Mapped[int | None] = mapped_column(nullable=True)
    race_stage: Mapped[RaceStage | None] = mapped_column(Enum(RaceStage, name='race_stage'), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text('true'), index=True)
    roster_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    roster_source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    roster_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    roster_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    statements: Mapped[list['Statement']] = relationship(back_populates='candidate', cascade='all, delete-orphan')
    score_snapshots: Mapped[list['ScoreSnapshot']] = relationship(back_populates='candidate', cascade='all, delete-orphan')

    __table_args__ = (Index('ix_candidates_race_context', 'state', 'office', 'election_cycle', 'race_stage'),)


class ReviewerUser(TimestampMixin, Base):
    __tablename__ = 'reviewer_users'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default='reviewer')
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text('true'))


class Statement(TimestampMixin, Base):
    __tablename__ = 'statements'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('candidates.id', ondelete='CASCADE'))
    source_type: Mapped[StatementSourceType] = mapped_column(Enum(StatementSourceType, name='statement_source_type'))
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    candidate: Mapped['Candidate'] = relationship(back_populates='statements')
    claims: Mapped[list['Claim']] = relationship(back_populates='statement', cascade='all, delete-orphan')
    evidence_links: Mapped[list['ClaimEvidenceLink']] = relationship(back_populates='statement')

    __table_args__ = (Index('ix_statements_candidate_published', 'candidate_id', 'published_at'),)


class IssueFrame(TimestampMixin, Base):
    __tablename__ = 'issue_frames'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    frame_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    comparison_question: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_candidate_source_classes: Mapped[list[SourceClass]] = mapped_column(
        ARRAY(Enum(SourceClass, name='source_class', create_type=False)),
        nullable=False,
        default=lambda: [SourceClass.primary],
        server_default='{primary}',
    )
    allowed_verification_source_classes: Mapped[list[SourceClass]] = mapped_column(
        ARRAY(Enum(SourceClass, name='source_class', create_type=False)),
        nullable=False,
        default=lambda: [SourceClass.primary, SourceClass.secondary],
        server_default='{primary,secondary}',
    )
    state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    office: Mapped[str | None] = mapped_column(String(255), nullable=True)
    election_cycle: Mapped[int | None] = mapped_column(nullable=True)
    race_stage: Mapped[RaceStage | None] = mapped_column(Enum(RaceStage, name='race_stage'), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text('true'))

    claims: Mapped[list['Claim']] = relationship(back_populates='issue_frame')

    __table_args__ = (
        Index('ix_issue_frames_scope', 'state', 'office', 'election_cycle', 'race_stage'),
        Index('ix_issue_frames_active', 'is_active'),
        CheckConstraint(
            'cardinality(allowed_candidate_source_classes) >= 1',
            name='ck_issue_frames_candidate_source_classes_nonempty',
        ),
        CheckConstraint(
            'cardinality(allowed_verification_source_classes) >= 1',
            name='ck_issue_frames_verification_source_classes_nonempty',
        ),
    )


class Claim(TimestampMixin, Base):
    __tablename__ = 'claims'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('statements.id', ondelete='CASCADE'))
    issue_frame_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('issue_frames.id', ondelete='SET NULL'),
        nullable=True,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    issue_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False, default='heuristic')
    extraction_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    fact_checkable: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text('true'))
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus, name='claim_status'), default=ClaimStatus.draft)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text('false'))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by_reviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    statement: Mapped['Statement'] = relationship(back_populates='claims')
    issue_frame: Mapped['IssueFrame | None'] = relationship(back_populates='claims')
    sources: Mapped[list['Source']] = relationship(back_populates='claim', cascade='all, delete-orphan')
    evaluations: Mapped[list['ClaimEvaluation']] = relationship(back_populates='claim', cascade='all, delete-orphan')
    evidence_bundle: Mapped['ClaimEvidenceBundle | None'] = relationship(
        back_populates='claim',
        cascade='all, delete-orphan',
        uselist=False,
    )
    proposals: Mapped[list['ClaimProposal']] = relationship(back_populates='claim', cascade='all, delete-orphan')

    __table_args__ = (
        Index('ix_claims_statement_status', 'statement_id', 'status'),
        Index('ix_claims_issue_frame_id', 'issue_frame_id'),
        Index('ix_claims_fact_checkable', 'fact_checkable'),
        Index('ix_claims_fact_checkable_published', 'fact_checkable', 'is_published'),
    )


class Source(TimestampMixin, Base):
    __tablename__ = 'sources'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_class: Mapped[SourceClass] = mapped_column(Enum(SourceClass, name='source_class'))
    source_origin: Mapped[SourceOrigin] = mapped_column(
        Enum(SourceOrigin, name='source_origin'),
        nullable=False,
        default=SourceOrigin.verification,
        server_default=SourceOrigin.verification.value,
    )
    policy_flagged: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text('false'))
    policy_flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)

    claim: Mapped['Claim'] = relationship(back_populates='sources')
    evidence_links: Mapped[list['ClaimEvidenceLink']] = relationship(back_populates='source')

    __table_args__ = (
        UniqueConstraint('claim_id', 'url', name='uq_sources_claim_url'),
        Index('ix_sources_claim_source_class', 'claim_id', 'source_class'),
        Index('ix_sources_claim_source_origin', 'claim_id', 'source_origin'),
        Index('ix_sources_claim_origin_policy_flagged', 'claim_id', 'source_origin', 'policy_flagged'),
    )


class ClaimEvidenceBundle(TimestampMixin, Base):
    __tablename__ = 'claim_evidence_bundles'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('claims.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
    )
    is_curated: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text('false'))

    claim: Mapped['Claim'] = relationship(back_populates='evidence_bundle')
    links: Mapped[list['ClaimEvidenceLink']] = relationship(
        back_populates='bundle',
        cascade='all, delete-orphan',
        order_by='ClaimEvidenceLink.display_order',
    )


class ClaimEvidenceLink(TimestampMixin, Base):
    __tablename__ = 'claim_evidence_links'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bundle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('claim_evidence_bundles.id', ondelete='CASCADE'),
        nullable=False,
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('statements.id', ondelete='SET NULL'),
        nullable=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('sources.id', ondelete='SET NULL'),
        nullable=True,
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    link_type: Mapped[EvidenceLinkType] = mapped_column(Enum(EvidenceLinkType, name='evidence_link_type'), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text('0'))

    bundle: Mapped['ClaimEvidenceBundle'] = relationship(back_populates='links')
    statement: Mapped['Statement | None'] = relationship(back_populates='evidence_links')
    source: Mapped['Source | None'] = relationship(back_populates='evidence_links')

    __table_args__ = (
        UniqueConstraint('bundle_id', 'link_type', 'url', name='uq_claim_evidence_links_bundle_type_url'),
        CheckConstraint(
            '(statement_id IS NOT NULL AND source_id IS NULL) OR (statement_id IS NULL AND source_id IS NOT NULL)',
            name='ck_claim_evidence_links_single_reference',
        ),
        Index('ix_claim_evidence_links_bundle_type_order', 'bundle_id', 'link_type', 'display_order'),
    )


class ClaimEvaluation(TimestampMixin, Base):
    __tablename__ = 'claim_evaluations'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    verdict: Mapped[Verdict] = mapped_column(Enum(Verdict, name='verdict'))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    citation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str] = mapped_column(String(255), nullable=False)

    claim: Mapped['Claim'] = relationship(back_populates='evaluations')

    __table_args__ = (Index('ix_claim_evaluations_claim_created', 'claim_id', 'created_at'),)


class ScoreSnapshot(TimestampMixin, Base):
    __tablename__ = 'score_snapshots'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('candidates.id', ondelete='CASCADE'))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fact_support_rate: Mapped[float] = mapped_column(Float, nullable=False)
    false_claim_rate: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_sufficiency_rate: Mapped[float] = mapped_column(Float, nullable=False)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    include_insufficient_in_denominator: Mapped[bool] = mapped_column(nullable=False, default=False)
    denominator_total: Mapped[int] = mapped_column(nullable=False)

    candidate: Mapped['Candidate'] = relationship(back_populates='score_snapshots')

    __table_args__ = (Index('ix_score_snapshots_candidate_window', 'candidate_id', 'window_start', 'window_end'),)


class AdminJobRun(TimestampMixin, Base):
    __tablename__ = 'admin_job_runs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='queued', server_default='queued')
    requested_by_reviewer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    input_payload: Mapped[str] = mapped_column(Text, nullable=False, default='{}', server_default='{}')
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default='0')
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3, server_default='3')
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index('ix_admin_job_runs_status_created', 'status', 'created_at'),
        Index('ix_admin_job_runs_job_type_created', 'job_type', 'created_at'),
    )


class AdminAuditEvent(TimestampMixin, Base):
    __tablename__ = 'admin_audit_events'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_reviewer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    before_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[str | None] = mapped_column('metadata', Text, nullable=True)

    __table_args__ = (
        Index('ix_admin_audit_events_created', 'created_at'),
        Index('ix_admin_audit_events_action_created', 'action', 'created_at'),
        Index('ix_admin_audit_events_entity_created', 'entity_type', 'entity_id', 'created_at'),
        Index('ix_admin_audit_events_actor_created', 'actor_reviewer_id', 'created_at'),
    )


class ClaimProposal(TimestampMixin, Base):
    __tablename__ = 'claim_proposals'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'), nullable=False)
    proposal_type: Mapped[ProposalType] = mapped_column(Enum(ProposalType, name='proposal_type'), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus, name='proposal_status'),
        nullable=False,
        default=ProposalStatus.proposed,
        server_default=ProposalStatus.proposed.value,
    )
    proposed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposal_payload: Mapped[str] = mapped_column(Text, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped['Claim'] = relationship(back_populates='proposals')

    __table_args__ = (
        Index('ix_claim_proposals_status_type_created', 'status', 'proposal_type', 'created_at'),
        Index('ix_claim_proposals_claim_id', 'claim_id'),
    )
