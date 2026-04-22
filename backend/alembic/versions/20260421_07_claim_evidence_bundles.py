"""add claim evidence bundle model

Revision ID: 20260421_07
Revises: 20260421_06
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260421_07'
down_revision: Union[str, None] = '20260421_06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

evidence_link_type = postgresql.ENUM(
    'stance',
    'verification',
    name='evidence_link_type',
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    evidence_link_type.create(bind, checkfirst=True)

    op.create_table(
        'claim_evidence_bundles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_curated', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('claim_id', name='uq_claim_evidence_bundles_claim_id'),
    )

    op.create_table(
        'claim_evidence_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('bundle_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('statement_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('url', sa.String(length=1024), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('link_type', evidence_link_type, nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            '(statement_id IS NOT NULL AND source_id IS NULL) OR (statement_id IS NULL AND source_id IS NOT NULL)',
            name='ck_claim_evidence_links_single_reference',
        ),
        sa.ForeignKeyConstraint(['bundle_id'], ['claim_evidence_bundles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['statement_id'], ['statements.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bundle_id', 'link_type', 'url', name='uq_claim_evidence_links_bundle_type_url'),
    )

    op.create_index(
        'ix_claim_evidence_links_bundle_type_order',
        'claim_evidence_links',
        ['bundle_id', 'link_type', 'display_order'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_claim_evidence_links_bundle_type_order', table_name='claim_evidence_links')
    op.drop_table('claim_evidence_links')
    op.drop_table('claim_evidence_bundles')
