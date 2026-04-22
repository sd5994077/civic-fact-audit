"""add source origin metadata

Revision ID: 20260421_05
Revises: 20260421_04
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260421_05'
down_revision = '20260421_04'
branch_labels = None
depends_on = None


source_origin = postgresql.ENUM('candidate', 'verification', name='source_origin', create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    source_origin.create(bind, checkfirst=True)
    op.add_column(
        'sources',
        sa.Column(
            'source_origin',
            source_origin,
            nullable=False,
            server_default='verification',
        ),
    )
    op.create_index('ix_sources_claim_source_origin', 'sources', ['claim_id', 'source_origin'], unique=False)
    op.alter_column('sources', 'source_origin', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_sources_claim_source_origin', table_name='sources')
    op.drop_column('sources', 'source_origin')
    bind = op.get_bind()
    source_origin.drop(bind, checkfirst=True)
