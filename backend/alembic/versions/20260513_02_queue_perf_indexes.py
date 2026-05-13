"""add queue performance indexes

Revision ID: 20260513_02
Revises: 20260513_01
Create Date: 2026-05-13

Indexes added:
- candidates(state, office, election_cycle, race_stage) — queue queries all join + filter
  on these four candidate columns with no composite index previously.
- claims(fact_checkable) — every queue query filters WHERE fact_checkable = true.
- claims(fact_checkable, is_published) — publish queue additionally filters on
  is_published; composite covers both patterns.
"""

from typing import Sequence, Union

from alembic import op

revision: str = '20260513_02'
down_revision: Union[str, None] = '20260513_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_candidates_race_context',
        'candidates',
        ['state', 'office', 'election_cycle', 'race_stage'],
    )
    op.create_index(
        'ix_claims_fact_checkable',
        'claims',
        ['fact_checkable'],
    )
    op.create_index(
        'ix_claims_fact_checkable_published',
        'claims',
        ['fact_checkable', 'is_published'],
    )


def downgrade() -> None:
    op.drop_index('ix_claims_fact_checkable_published', table_name='claims')
    op.drop_index('ix_claims_fact_checkable', table_name='claims')
    op.drop_index('ix_candidates_race_context', table_name='candidates')
