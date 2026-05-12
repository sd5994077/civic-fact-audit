"""add source policy flag fields

Revision ID: 20260511_03
Revises: 20260511_02
Create Date: 2026-05-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260511_03'
down_revision: Union[str, None] = '20260511_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sources', sa.Column('policy_flagged', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('sources', sa.Column('policy_flag_reason', sa.Text(), nullable=True))
    op.add_column('sources', sa.Column('policy_flagged_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        'ix_sources_claim_origin_policy_flagged',
        'sources',
        ['claim_id', 'source_origin', 'policy_flagged'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_sources_claim_origin_policy_flagged', table_name='sources')
    op.drop_column('sources', 'policy_flagged_at')
    op.drop_column('sources', 'policy_flag_reason')
    op.drop_column('sources', 'policy_flagged')
