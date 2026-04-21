import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import ClaimStatus, RaceStage, SourceClass, StatementSourceType, Verdict


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

    statements: Mapped[list['Statement']] = relationship(back_populates='candidate', cascade='all, delete-orphan')
    score_snapshots: Mapped[list['ScoreSnapshot']] = relationship(back_populates='candidate', cascade='all, delete-orphan')


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

    __table_args__ = (Index('ix_statements_candidate_published', 'candidate_id', 'published_at'),)


class IssueFrame(TimestampMixin, Base):
    __tablename__ = 'issue_frames'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    frame_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    comparison_question: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    office: Mapped[str | None] = mapped_column(String(255), nullable=True)
    election_cycle: Mapped[int | None] = mapped_column(nullable=True)
    race_stage: Mapped[RaceStage | None] = mapped_column(Enum(RaceStage, name='race_stage'), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text('true'))

    claims: Mapped[list['Claim']] = relationship(back_populates='issue_frame')

    __table_args__ = (
        Index('ix_issue_frames_scope', 'state', 'office', 'election_cycle', 'race_stage'),
        Index('ix_issue_frames_active', 'is_active'),
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

    statement: Mapped['Statement'] = relationship(back_populates='claims')
    issue_frame: Mapped['IssueFrame | None'] = relationship(back_populates='claims')
    sources: Mapped[list['Source']] = relationship(back_populates='claim', cascade='all, delete-orphan')
    evaluations: Mapped[list['ClaimEvaluation']] = relationship(back_populates='claim', cascade='all, delete-orphan')

    __table_args__ = (
        Index('ix_claims_statement_status', 'statement_id', 'status'),
        Index('ix_claims_issue_frame_id', 'issue_frame_id'),
    )


class Source(TimestampMixin, Base):
    __tablename__ = 'sources'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('claims.id', ondelete='CASCADE'))
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_class: Mapped[SourceClass] = mapped_column(Enum(SourceClass, name='source_class'))
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)

    claim: Mapped['Claim'] = relationship(back_populates='sources')

    __table_args__ = (
        UniqueConstraint('claim_id', 'url', name='uq_sources_claim_url'),
        Index('ix_sources_claim_source_class', 'claim_id', 'source_class'),
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
