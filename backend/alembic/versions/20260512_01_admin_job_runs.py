"""add admin job runs table

Revision ID: 20260512_01
Revises: 20260511_04
Create Date: 2026-05-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260512_01'
down_revision: Union[str, None] = '20260511_04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_job_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_type', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='queued'),
        sa.Column('requested_by_reviewer_id', sa.String(length=255), nullable=False),
        sa.Column('input_payload', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_job_runs_status_created', 'admin_job_runs', ['status', 'created_at'], unique=False)
    op.create_index('ix_admin_job_runs_job_type_created', 'admin_job_runs', ['job_type', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_admin_job_runs_job_type_created', table_name='admin_job_runs')
    op.drop_index('ix_admin_job_runs_status_created', table_name='admin_job_runs')
    op.drop_table('admin_job_runs')
