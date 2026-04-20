"""initial mvp schema

Revision ID: 20260420_01
Revises:
Create Date: 2026-04-20 10:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260420_01'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

statement_source_type = postgresql.ENUM(
    'speech',
    'interview',
    'social',
    'debate',
    'press_release',
    name='statement_source_type',
    create_type=False,
)
claim_status = postgresql.ENUM('draft', 'reviewed', 'published', name='claim_status', create_type=False)
source_class = postgresql.ENUM('primary', 'secondary', name='source_class', create_type=False)
verdict = postgresql.ENUM('supported', 'mixed', 'unsupported', 'insufficient', name='verdict', create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    statement_source_type.create(bind, checkfirst=True)
    claim_status.create(bind, checkfirst=True)
    source_class.create(bind, checkfirst=True)
    verdict.create(bind, checkfirst=True)

    op.create_table(
        'candidates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('party', sa.String(length=128), nullable=True),
        sa.Column('office', sa.String(length=255), nullable=True),
        sa.Column('state', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'statements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_type', statement_source_type, nullable=False),
        sa.Column('source_url', sa.String(length=1024), nullable=False),
        sa.Column('statement_text', sa.Text(), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_statements_candidate_published', 'statements', ['candidate_id', 'published_at'], unique=False)

    op.create_table(
        'claims',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('statement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_text', sa.Text(), nullable=False),
        sa.Column('issue_tag', sa.String(length=128), nullable=True),
        sa.Column('extraction_confidence', sa.Float(), nullable=False),
        sa.Column('extraction_method', sa.String(length=64), nullable=False),
        sa.Column('extraction_metadata', sa.Text(), nullable=True),
        sa.Column('status', claim_status, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['statement_id'], ['statements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_claims_statement_status', 'claims', ['statement_id', 'status'], unique=False)

    op.create_table(
        'sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String(length=1024), nullable=False),
        sa.Column('source_class', source_class, nullable=False),
        sa.Column('publisher', sa.String(length=255), nullable=True),
        sa.Column('quality_score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('claim_id', 'url', name='uq_sources_claim_url'),
    )
    op.create_index('ix_sources_claim_source_class', 'sources', ['claim_id', 'source_class'], unique=False)

    op.create_table(
        'claim_evaluations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('verdict', verdict, nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('citation_notes', sa.Text(), nullable=True),
        sa.Column('reviewer_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_claim_evaluations_claim_created', 'claim_evaluations', ['claim_id', 'created_at'], unique=False)

    op.create_table(
        'score_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fact_support_rate', sa.Float(), nullable=False),
        sa.Column('false_claim_rate', sa.Float(), nullable=False),
        sa.Column('evidence_sufficiency_rate', sa.Float(), nullable=False),
        sa.Column('composite_score', sa.Float(), nullable=True),
        sa.Column('formula_version', sa.String(length=64), nullable=False),
        sa.Column('include_insufficient_in_denominator', sa.Boolean(), nullable=False),
        sa.Column('denominator_total', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_score_snapshots_candidate_window', 'score_snapshots', ['candidate_id', 'window_start', 'window_end'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_score_snapshots_candidate_window', table_name='score_snapshots')
    op.drop_table('score_snapshots')

    op.drop_index('ix_claim_evaluations_claim_created', table_name='claim_evaluations')
    op.drop_table('claim_evaluations')

    op.drop_index('ix_sources_claim_source_class', table_name='sources')
    op.drop_table('sources')

    op.drop_index('ix_claims_statement_status', table_name='claims')
    op.drop_table('claims')

    op.drop_index('ix_statements_candidate_published', table_name='statements')
    op.drop_table('statements')

    op.drop_table('candidates')

    bind = op.get_bind()
    verdict.drop(bind, checkfirst=True)
    source_class.drop(bind, checkfirst=True)
    claim_status.drop(bind, checkfirst=True)
    statement_source_type.drop(bind, checkfirst=True)
