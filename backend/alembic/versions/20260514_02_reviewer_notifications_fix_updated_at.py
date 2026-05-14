"""add missing updated_at to reviewer_notifications

Revision ID: 20260514_02
Revises: 20260514_01
Create Date: 2026-05-14

Fixes omission of updated_at column that TimestampMixin expects.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260514_02'
down_revision: Union[str, None] = '20260514_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'reviewer_notifications',
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_column('reviewer_notifications', 'updated_at')
