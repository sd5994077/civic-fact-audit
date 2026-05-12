"""add admin audit events table

Revision ID: 20260512_02
Revises: 20260512_01
Create Date: 2026-05-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260512_02'
down_revision: Union[str, None] = '20260512_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actor_reviewer_id', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('entity_type', sa.String(length=128), nullable=False),
        sa.Column('entity_id', sa.String(length=255), nullable=False),
        sa.Column('before_payload', sa.Text(), nullable=True),
        sa.Column('after_payload', sa.Text(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_audit_events_created', 'admin_audit_events', ['created_at'], unique=False)
    op.create_index('ix_admin_audit_events_action_created', 'admin_audit_events', ['action', 'created_at'], unique=False)
    op.create_index(
        'ix_admin_audit_events_entity_created',
        'admin_audit_events',
        ['entity_type', 'entity_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_admin_audit_events_actor_created',
        'admin_audit_events',
        ['actor_reviewer_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_admin_audit_events_actor_created', table_name='admin_audit_events')
    op.drop_index('ix_admin_audit_events_entity_created', table_name='admin_audit_events')
    op.drop_index('ix_admin_audit_events_action_created', table_name='admin_audit_events')
    op.drop_index('ix_admin_audit_events_created', table_name='admin_audit_events')
    op.drop_table('admin_audit_events')
