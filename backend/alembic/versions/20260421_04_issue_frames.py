"""add issue frames and claim mapping

Revision ID: 20260421_04
Revises: 20260421_03
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260421_04'
down_revision: Union[str, None] = '20260421_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

race_stage = postgresql.ENUM(
    'primary',
    'primary_runoff',
    'general',
    'special',
    name='race_stage',
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    race_stage.create(bind, checkfirst=True)

    op.create_table(
        'issue_frames',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('frame_key', sa.String(length=128), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('comparison_question', sa.Text(), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=True),
        sa.Column('office', sa.String(length=255), nullable=True),
        sa.Column('election_cycle', sa.Integer(), nullable=True),
        sa.Column('race_stage', race_stage, nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('frame_key', name='uq_issue_frames_frame_key'),
    )
    op.create_index('ix_issue_frames_scope', 'issue_frames', ['state', 'office', 'election_cycle', 'race_stage'], unique=False)
    op.create_index('ix_issue_frames_active', 'issue_frames', ['is_active'], unique=False)

    op.add_column('claims', sa.Column('issue_frame_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_claims_issue_frame_id', 'claims', ['issue_frame_id'], unique=False)
    op.create_foreign_key(
        'fk_claims_issue_frame_id',
        'claims',
        'issue_frames',
        ['issue_frame_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_claims_issue_frame_id', 'claims', type_='foreignkey')
    op.drop_index('ix_claims_issue_frame_id', table_name='claims')
    op.drop_column('claims', 'issue_frame_id')

    op.drop_index('ix_issue_frames_active', table_name='issue_frames')
    op.drop_index('ix_issue_frames_scope', table_name='issue_frames')
    op.drop_table('issue_frames')

