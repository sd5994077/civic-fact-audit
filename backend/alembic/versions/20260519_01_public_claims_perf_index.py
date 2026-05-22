"""add public claims listing performance index

Revision ID: 20260519_01
Revises: 20260514_02
Create Date: 2026-05-19

Adds:
- claims(is_published, published_at) to support public API list reads ordered by
  published_at while filtering published rows.
"""

from typing import Sequence, Union

from alembic import op

revision: str = '20260519_01'
down_revision: Union[str, None] = '20260514_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_claims_is_published_published_at',
        'claims',
        ['is_published', 'published_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_claims_is_published_published_at', table_name='claims')

