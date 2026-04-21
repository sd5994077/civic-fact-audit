"""Add typed fact_checkable field to claims.

Revision ID: 20260421_02
Revises: 20260421_01
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


revision = '20260421_02'
down_revision = '20260421_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'claims',
        sa.Column('fact_checkable', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    op.alter_column('claims', 'fact_checkable', server_default=None)


def downgrade() -> None:
    op.drop_column('claims', 'fact_checkable')
