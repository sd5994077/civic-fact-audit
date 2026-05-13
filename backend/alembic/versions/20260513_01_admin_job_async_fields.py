"""add async fields to admin job runs

Revision ID: 20260513_01
Revises: 20260512_02
Create Date: 2026-05-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '20260513_01'
down_revision: Union[str, None] = '20260512_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('admin_job_runs', sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('admin_job_runs', sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('admin_job_runs', sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('admin_job_runs', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('admin_job_runs', sa.Column('last_error_code', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('admin_job_runs', 'last_error_code')
    op.drop_column('admin_job_runs', 'lease_expires_at')
    op.drop_column('admin_job_runs', 'next_attempt_at')
    op.drop_column('admin_job_runs', 'max_attempts')
    op.drop_column('admin_job_runs', 'attempt_count')
