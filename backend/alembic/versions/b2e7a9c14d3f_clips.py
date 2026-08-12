"""clips (feed windows)

Revision ID: b2e7a9c14d3f
Revises: 94c5b1e5439b
Create Date: 2026-07-25 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2e7a9c14d3f'
down_revision: Union[str, None] = '94c5b1e5439b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('clips',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('lesson_id', sa.String(length=64), nullable=False),
    sa.Column('start_idx', sa.Integer(), nullable=False),
    sa.Column('end_idx', sa.Integer(), nullable=False),
    sa.Column('start_ms', sa.Integer(), nullable=False),
    sa.Column('end_ms', sa.Integer(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('difficulty', sa.String(length=8), nullable=False),
    sa.Column('text_en', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_clips_lesson_id_lessons'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clips')),
    sa.UniqueConstraint('lesson_id', 'start_idx', 'end_idx', name=op.f('uq_clips_lesson_id'))
    )
    with op.batch_alter_table('clips', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clips_difficulty'), ['difficulty'], unique=False)
        batch_op.create_index(batch_op.f('ix_clips_lesson_id'), ['lesson_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('clips', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clips_lesson_id'))
        batch_op.drop_index(batch_op.f('ix_clips_difficulty'))

    op.drop_table('clips')
