"""dictionary_entries (word card definition cache)

Revision ID: d5c4b81f60a7
Revises: c3f1a8b62e9d
Create Date: 2026-07-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5c4b81f60a7'
down_revision: Union[str, None] = 'c3f1a8b62e9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('dictionary_entries',
    sa.Column('lemma', sa.String(length=64), nullable=False),
    sa.Column('phonetic', sa.String(length=64), nullable=True),
    sa.Column('audio_url', sa.String(length=512), nullable=True),
    sa.Column('gloss_zh', sa.Text(), nullable=True),
    sa.Column('senses', sa.Text(), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('lemma', name=op.f('pk_dictionary_entries'))
    )


def downgrade() -> None:
    op.drop_table('dictionary_entries')
