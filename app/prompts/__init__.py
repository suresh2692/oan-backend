"""
Prompt Management Package

Provides centralized prompt storage, versioning, and retrieval
backed by PostgreSQL + Redis caching with filesystem fallback.
"""

from app.prompts.registry import PromptRegistry

# Singleton instance
_registry: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    """Get or create the PromptRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry


# Convenience alias
prompt_registry = get_prompt_registry()
