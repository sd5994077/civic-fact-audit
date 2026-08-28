"""sources: add fetch_status column

Revision ID: 20260614_01
Revises: 20260613_01
Create Date: 2026-06-14

Changes:
- sources.fetch_status (varchar 32, default 'unknown') — URL probe result at attach time.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260614_01'
down_revision: Union[str, None] = '20260613_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sources',
        sa.Column('fetch_status', sa.String(32), nullable=False, server_default='unknown'),
    )


def downgrade() -> None:
    op.drop_column('sources', 'fetch_status')
