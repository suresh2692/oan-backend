"""
Prompt Management SQLAlchemy Models

Defines database models for prompt storage, versioning, and usage tracking.
"""

from sqlalchemy import (
    Column, Integer, String, TEXT, TIMESTAMP, ForeignKey,
    CheckConstraint, UniqueConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class Prompt(Base):
    """Versioned prompt templates with language and variant support."""
    __tablename__ = "prompts"

    prompt_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    lang = Column(String(10), nullable=False, default="en")
    variant = Column(String(50), default="default")
    status = Column(String(20), nullable=False, default="draft")
    content = Column(TEXT, nullable=False)
    content_type = Column(String(20), default="text")  # 'text' or 'json'
    description = Column(TEXT)
    template_vars = Column(JSONB, default=[])
    token_count = Column(Integer)
    meta_data = Column(JSONB, default={})
    created_by = Column(String(100), default="system")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    activated_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        UniqueConstraint("name", "version", "lang", "variant", name="uq_prompt_name_version_lang_variant"),
        CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_prompt_status"),
        Index("idx_prompt_name", "name"),
        Index("idx_prompt_status", "status"),
        Index("idx_prompt_name_lang", "name", "lang"),
        # Partial unique index: exactly one active version per name+lang+variant
        Index(
            "uq_prompt_active",
            "name", "lang", "variant",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


class PromptUsageLog(Base):
    """Tracks which prompt version was served for observability."""
    __tablename__ = "prompt_usage_log"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    prompt_id = Column(Integer, ForeignKey("prompts.prompt_id", ondelete="SET NULL"))
    prompt_name = Column(String(100))
    prompt_version = Column(Integer)
    variant = Column(String(50))
    session_id = Column(String(100))
    model_name = Column(String(100))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_usage_prompt_name", "prompt_name"),
        Index("idx_usage_session", "session_id"),
        Index("idx_usage_created", created_at.desc()),
    )
