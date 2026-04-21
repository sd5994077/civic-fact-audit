"""Add reviewer users table for authenticated human review.

Revision ID: 20260421_03
Revises: 20260421_02
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260421_03'
down_revision = '20260421_02'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'reviewer_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=512), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_reviewer_users_email'),
    )


def downgrade() -> None:
    op.drop_table('reviewer_users')
