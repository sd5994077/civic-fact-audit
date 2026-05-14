"""add reviewer_notifications table for notification workflow

Revision ID: 20260514_01
Revises: 20260513_04
Create Date: 2026-05-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260514_01'
down_revision: Union[str, None] = '20260513_04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reviewer_notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('claims.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('reviewer_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recipient_email', sa.String(255), nullable=False),
        sa.Column('transport', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_reviewer_notifications_reviewer_id', 'reviewer_notifications', ['reviewer_id'])
    op.create_index('ix_reviewer_notifications_claim_id', 'reviewer_notifications', ['claim_id'])
    op.create_index(
        'ix_reviewer_notifications_event_dedup',
        'reviewer_notifications',
        ['event_type', 'claim_id', 'reviewer_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_reviewer_notifications_event_dedup', table_name='reviewer_notifications')
    op.drop_index('ix_reviewer_notifications_claim_id', table_name='reviewer_notifications')
    op.drop_index('ix_reviewer_notifications_reviewer_id', table_name='reviewer_notifications')
    op.drop_table('reviewer_notifications')
