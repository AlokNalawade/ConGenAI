"""update_ix_one_active_job_include_dispatching

Revision ID: 5a33285fa474
Revises: c5a1a628620f
Create Date: 2026-09-13 20:41:02.124447

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a33285fa474'
down_revision: Union[str, Sequence[str], None] = 'c5a1a628620f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('ix_one_active_job_per_content', table_name='pipeline_jobs')
    op.create_index(
        'ix_one_active_job_per_content',
        'pipeline_jobs',
        ['content_id'],
        unique=True,
        postgresql_where="status IN ('queued', 'dispatching', 'running', 'resuming')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_one_active_job_per_content', table_name='pipeline_jobs')
    op.create_index(
        'ix_one_active_job_per_content',
        'pipeline_jobs',
        ['content_id'],
        unique=True,
        postgresql_where="status IN ('queued', 'running', 'resuming')"
    )
