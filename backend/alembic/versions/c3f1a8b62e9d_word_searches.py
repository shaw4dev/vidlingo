"""word_searches (backfill quota cache)

Revision ID: c3f1a8b62e9d
Revises: b2e7a9c14d3f
Create Date: 2026-07-25 00:00:01.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f1a8b62e9d'
down_revision: Union[str, None] = 'b2e7a9c14d3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('word_searches',
    sa.Column('lemma', sa.String(length=64), nullable=False),
    sa.Column('searched_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('ingested_count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('lemma', name=op.f('pk_word_searches'))
    )


def downgrade() -> None:
    op.drop_table('word_searches')
