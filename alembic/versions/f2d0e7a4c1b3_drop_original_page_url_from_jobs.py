"""Drop original page url from download jobs

Revision ID: f2d0e7a4c1b3
Revises: 2d4f81ac9d77
Create Date: 2026-06-02 18:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2d0e7a4c1b3'
down_revision: Union[str, Sequence[str], None] = '2d4f81ac9d77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  bind = op.get_bind()
  inspector = sa.inspect(bind)
  columns = {column['name'] for column in inspector.get_columns('download_jobs')}
  if 'original_page_url' in columns:
    op.drop_column('download_jobs', 'original_page_url')


def downgrade() -> None:
  bind = op.get_bind()
  inspector = sa.inspect(bind)
  columns = {column['name'] for column in inspector.get_columns('download_jobs')}
  if 'original_page_url' not in columns:
    op.add_column('download_jobs', sa.Column('original_page_url', sa.Text(), nullable=True))
