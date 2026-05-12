"""add unified claim proposals workflow

Revision ID: 20260511_02
Revises: 20260511_01
Create Date: 2026-05-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260511_02'
down_revision: Union[str, None] = '20260511_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    proposal_type = postgresql.ENUM(
        'issue_frame_mapping',
        'candidate_source_capture',
        'verification_source_suggestion',
        'draft_verdict',
        name='proposal_type',
        create_type=False,
    )
    proposal_status = postgresql.ENUM(
        'proposed',
        'approved',
        'rejected',
        'applied',
        name='proposal_status',
        create_type=False,
    )
    proposal_type.create(op.get_bind(), checkfirst=True)
    proposal_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'claim_proposals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.UUID(), nullable=False),
        sa.Column('proposal_type', proposal_type, nullable=False),
        sa.Column('status', proposal_status, nullable=False, server_default='proposed'),
        sa.Column('proposed_by', sa.String(length=255), nullable=False),
        sa.Column('reviewed_by', sa.String(length=255), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('proposal_payload', sa.Text(), nullable=False),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_claim_proposals_status_type_created', 'claim_proposals', ['status', 'proposal_type', 'created_at'], unique=False)
    op.create_index('ix_claim_proposals_claim_id', 'claim_proposals', ['claim_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_claim_proposals_claim_id', table_name='claim_proposals')
    op.drop_index('ix_claim_proposals_status_type_created', table_name='claim_proposals')
    op.drop_table('claim_proposals')
    postgresql.ENUM(name='proposal_status', create_type=False).drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='proposal_type', create_type=False).drop(op.get_bind(), checkfirst=True)
