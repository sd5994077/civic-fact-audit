"""add issue frame source policy fields

Revision ID: 20260421_06
Revises: 20260421_05
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260421_06'
down_revision: Union[str, None] = '20260421_05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

source_class = postgresql.ENUM(
    'primary',
    'secondary',
    name='source_class',
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    source_class.create(bind, checkfirst=True)

    op.add_column(
        'issue_frames',
        sa.Column(
            'allowed_candidate_source_classes',
            postgresql.ARRAY(source_class),
            nullable=False,
            server_default=sa.text("'{primary}'"),
        ),
    )
    op.add_column(
        'issue_frames',
        sa.Column(
            'allowed_verification_source_classes',
            postgresql.ARRAY(source_class),
            nullable=False,
            server_default=sa.text("'{primary,secondary}'"),
        ),
    )
    op.create_check_constraint(
        'ck_issue_frames_candidate_source_classes_nonempty',
        'issue_frames',
        'cardinality(allowed_candidate_source_classes) >= 1',
    )
    op.create_check_constraint(
        'ck_issue_frames_verification_source_classes_nonempty',
        'issue_frames',
        'cardinality(allowed_verification_source_classes) >= 1',
    )


def downgrade() -> None:
    op.drop_constraint('ck_issue_frames_verification_source_classes_nonempty', 'issue_frames', type_='check')
    op.drop_constraint('ck_issue_frames_candidate_source_classes_nonempty', 'issue_frames', type_='check')
    op.drop_column('issue_frames', 'allowed_verification_source_classes')
    op.drop_column('issue_frames', 'allowed_candidate_source_classes')
