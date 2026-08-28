"""add source content_excerpt and AI draft audit trail

Revision ID: 20260613_01
Revises: 20260519_01
Create Date: 2026-06-13

Adds:
- sources.content_excerpt (text, nullable) — reviewer-provided key quote used as
  AI context fallback when live fetch returns empty (paywalled / JS-rendered pages).
- claim_evaluations.ai_draft_used (bool, default false) — whether an AI draft was
  applied before the reviewer submitted this evaluation.
- claim_evaluations.ai_draft_model (varchar 128, nullable) — which model generated
  the draft (e.g. gpt-4o-mini, claude-sonnet-4-6).
- claim_evaluations.ai_draft_suggested_verdict (varchar 64, nullable) — what verdict
  the AI suggested, for comparison against the reviewer's actual choice.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260613_01'
down_revision: Union[str, None] = '20260519_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sources', sa.Column('content_excerpt', sa.Text(), nullable=True))

    op.add_column('claim_evaluations', sa.Column('ai_draft_used', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('claim_evaluations', sa.Column('ai_draft_model', sa.String(128), nullable=True))
    op.add_column('claim_evaluations', sa.Column('ai_draft_suggested_verdict', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('sources', 'content_excerpt')
    op.drop_column('claim_evaluations', 'ai_draft_used')
    op.drop_column('claim_evaluations', 'ai_draft_model')
    op.drop_column('claim_evaluations', 'ai_draft_suggested_verdict')
