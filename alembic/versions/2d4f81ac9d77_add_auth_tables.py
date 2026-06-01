"""Add auth tables

Revision ID: 2d4f81ac9d77
Revises: 5e8bb6e1f2d1
Create Date: 2026-06-01 03:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d4f81ac9d77'
down_revision: Union[str, Sequence[str], None] = '5e8bb6e1f2d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'users',
    sa.Column('uid', sa.String(length=16), nullable=False),
    sa.Column('login', sa.String(length=128), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('uid'),
    sa.UniqueConstraint('login'),
  )
  op.create_table(
    'revoked_tokens',
    sa.Column('uid', sa.String(length=16), nullable=False),
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('token_type', sa.String(length=16), nullable=False),
    sa.Column('user_uid', sa.String(length=16), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('uid'),
    sa.UniqueConstraint('jti'),
  )


def downgrade() -> None:
  op.drop_table('revoked_tokens')
  op.drop_table('users')
