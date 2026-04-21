"""add candidate race context

Revision ID: 20260421_01
Revises: 20260420_01
Create Date: 2026-04-21 09:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260421_01'
down_revision: Union[str, None] = '20260420_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

race_stage = postgresql.ENUM(
    'primary',
    'primary_runoff',
    'general',
    'special',
    name='race_stage',
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    race_stage.create(bind, checkfirst=True)

    op.add_column('candidates', sa.Column('election_cycle', sa.Integer(), nullable=True))
    op.add_column('candidates', sa.Column('race_stage', race_stage, nullable=True))
    op.create_index(
        'ix_candidates_race_context',
        'candidates',
        ['state', 'office', 'election_cycle', 'race_stage'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_candidates_race_context', table_name='candidates')
    op.drop_column('candidates', 'race_stage')
    op.drop_column('candidates', 'election_cycle')

    bind = op.get_bind()
    race_stage.drop(bind, checkfirst=True)
