"""add claim_ai_drafts table for persistent AI draft history

Revision ID: 20260710_01
Revises: 20260614_01
Create Date: 2026-07-10

Adds:
- claim_ai_drafts table — persists every AI review-draft generation
  (model, suggested verdict/confidence, rationale, citation notes, and
  JSON-serialized subclaims/source_assessments/warnings/missing_evidence)
  so reviewers can see draft history and diff the latest draft against
  their submitted evaluation. Reuses the existing `verdict` enum type.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260710_01'
down_revision: Union[str, None] = '20260614_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    verdict = postgresql.ENUM(
        'supported', 'mixed', 'unsupported', 'insufficient',
        name='verdict',
        create_type=False,
    )

    op.create_table(
        'claim_ai_drafts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.UUID(), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('suggested_verdict', verdict, nullable=False),
        sa.Column('suggested_confidence', sa.Float(), nullable=False),
        sa.Column('model_confidence', sa.Float(), nullable=False),
        sa.Column('evidence_sufficiency', sa.Float(), nullable=False),
        sa.Column('green_lane_ready', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('citation_notes', sa.Text(), nullable=False),
        sa.Column('subclaims_payload', sa.Text(), nullable=True),
        sa.Column('source_assessments_payload', sa.Text(), nullable=True),
        sa.Column('warnings_payload', sa.Text(), nullable=True),
        sa.Column('missing_evidence_payload', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_claim_ai_drafts_claim_created', 'claim_ai_drafts', ['claim_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_claim_ai_drafts_claim_created', table_name='claim_ai_drafts')
    op.drop_table('claim_ai_drafts')
