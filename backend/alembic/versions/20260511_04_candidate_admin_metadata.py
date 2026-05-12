"""add candidate admin metadata fields

Revision ID: 20260511_04
Revises: 20260511_03
Create Date: 2026-05-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260511_04'
down_revision: Union[str, None] = '20260511_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('candidates', sa.Column('roster_status', sa.String(length=64), nullable=True))
    op.add_column('candidates', sa.Column('roster_source_url', sa.String(length=1024), nullable=True))
    op.add_column('candidates', sa.Column('roster_checked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('candidates', sa.Column('roster_notes', sa.Text(), nullable=True))
    op.create_index('ix_candidates_is_active', 'candidates', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_candidates_is_active', table_name='candidates')
    op.drop_column('candidates', 'roster_notes')
    op.drop_column('candidates', 'roster_checked_at')
    op.drop_column('candidates', 'roster_source_url')
    op.drop_column('candidates', 'roster_status')
    op.drop_column('candidates', 'is_active')
