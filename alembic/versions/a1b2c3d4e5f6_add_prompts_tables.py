"""add prompts tables

Revision ID: a1b2c3d4e5f6
Revises: bf13d07dbb2d
Create Date: 2026-03-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'bf13d07dbb2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create prompts and prompt_usage_log tables."""

    op.create_table(
        'prompts',
        sa.Column('prompt_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('lang', sa.String(10), nullable=False, server_default='en'),
        sa.Column('variant', sa.String(50), server_default='default'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('content', sa.TEXT(), nullable=False),
        sa.Column('content_type', sa.String(20), server_default='text'),
        sa.Column('description', sa.TEXT()),
        sa.Column('template_vars', postgresql.JSONB(), server_default='[]'),
        sa.Column('token_count', sa.Integer()),
        sa.Column('meta_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_by', sa.String(100), server_default='system'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('activated_at', sa.TIMESTAMP(timezone=True)),
        sa.PrimaryKeyConstraint('prompt_id'),
        sa.UniqueConstraint('name', 'version', 'lang', 'variant', name='uq_prompt_name_version_lang_variant'),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name='ck_prompt_status'),
    )

    op.create_index('idx_prompt_name', 'prompts', ['name'])
    op.create_index('idx_prompt_status', 'prompts', ['status'])
    op.create_index('idx_prompt_name_lang', 'prompts', ['name', 'lang'])

    # Partial unique index: exactly one active version per name+lang+variant
    op.create_index(
        'uq_prompt_active',
        'prompts',
        ['name', 'lang', 'variant'],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        'prompt_usage_log',
        sa.Column('log_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('prompt_id', sa.Integer(), sa.ForeignKey('prompts.prompt_id', ondelete='SET NULL')),
        sa.Column('prompt_name', sa.String(100)),
        sa.Column('prompt_version', sa.Integer()),
        sa.Column('variant', sa.String(50)),
        sa.Column('session_id', sa.String(100)),
        sa.Column('model_name', sa.String(100)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('log_id'),
    )

    op.create_index('idx_usage_prompt_name', 'prompt_usage_log', ['prompt_name'])
    op.create_index('idx_usage_session', 'prompt_usage_log', ['session_id'])
    op.create_index('idx_usage_created', 'prompt_usage_log', [sa.text('created_at DESC')])


def downgrade() -> None:
    """Drop prompts and prompt_usage_log tables."""
    op.drop_table('prompt_usage_log')
    op.drop_table('prompts')
