"""Add source user-agent to download jobs

Revision ID: 5e8bb6e1f2d1
Revises: 806e5901953c
Create Date: 2026-06-01 02:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e8bb6e1f2d1'
down_revision: Union[str, Sequence[str], None] = '806e5901953c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('download_jobs', sa.Column('source_user_agent', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('download_jobs', 'source_user_agent')

