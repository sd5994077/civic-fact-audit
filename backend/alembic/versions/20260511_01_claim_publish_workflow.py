"""add claim publish workflow columns

Revision ID: 20260511_01
Revises: 20260421_07
Create Date: 2026-05-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260511_01'
down_revision: Union[str, None] = '20260421_07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('claims', sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('claims', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('claims', sa.Column('published_by_reviewer_id', sa.String(length=255), nullable=True))
    op.create_index('ix_claims_is_published', 'claims', ['is_published'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_claims_is_published', table_name='claims')
    op.drop_column('claims', 'published_by_reviewer_id')
    op.drop_column('claims', 'published_at')
    op.drop_column('claims', 'is_published')
