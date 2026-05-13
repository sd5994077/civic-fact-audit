"""add GIN full-text search index on claims.claim_text

Revision ID: 20260513_03
Revises: 20260513_02
Create Date: 2026-05-13

Index added:
- GIN index on to_tsvector('english', claim_text) — supports fast full-text
  search via plainto_tsquery on the GET /v1/claims/search endpoint.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260513_03'
down_revision: Union[str, None] = '20260513_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_claims_fulltext',
        'claims',
        [sa.text("to_tsvector('english', claim_text)")],
        postgresql_using='gin',
    )


def downgrade() -> None:
    op.drop_index('ix_claims_fulltext', table_name='claims')
