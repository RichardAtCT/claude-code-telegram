"""Model name mapper for proxy/enterprise endpoints.

Maps short aliases (cc-opus, sonnet, etc.) to full Anthropic model names.
Useful when using ANTHROPIC_BASE_URL with custom model naming schemes.

References:
- Claude 4.6 models: https://docs.anthropic.com/en/docs/about-claude/models
- Claude 4.5 models: https://docs.anthropic.com/en/docs/about-claude/models
"""

from typing import Optional

import structlog

logger = structlog.get_logger()

# Official Anthropic model names (as of 2026-03-10)
# Source: https://docs.anthropic.com/en/docs/about-claude/models
MODEL_ALIASES = {
    # Claude 4.6 series (latest)
    "opus": "claude-opus-4-6",
    "cc-opus": "claude-opus-4-6",
    "opus-4.6": "claude-opus-4-6",
    "opus-4-6": "claude-opus-4-6",
    "claude-opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "cc-sonnet": "claude-sonnet-4-6",
    "sonnet-4.6": "claude-sonnet-4-6",
    "sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    # Claude 4.5 series (with date versions)
    "haiku": "claude-haiku-4-5-20251001",
    "cc-haiku": "claude-haiku-4-5-20251001",
    "haiku-4.5": "claude-haiku-4-5-20251001",
    "haiku-4-5": "claude-haiku-4-5-20251001",
    "claude-haiku": "claude-haiku-4-5-20251001",
    # Legacy short names
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    # Claude 3.7 series (if still supported)
    "opus-3.7": "claude-opus-3-7-20250219",
    "opus-3-7": "claude-opus-3-7-20250219",
    # Claude 3.5 series (legacy)
    "sonnet-3.5": "claude-3-5-sonnet-20241022",
    "sonnet-3-5": "claude-3-5-sonnet-20241022",
    "sonnet-20241022": "claude-3-5-sonnet-20241022",
    "haiku-3.5": "claude-3-5-haiku-20241022",
    "haiku-3-5": "claude-3-5-haiku-20241022",
    "haiku-20241022": "claude-3-5-haiku-20241022",
    # Legacy Claude 3 series
    "opus-3": "claude-3-opus-20240229",
    "sonnet-3": "claude-3-sonnet-20240229",
    "haiku-3": "claude-3-haiku-20240307",
}

# Reverse mapping: full name → shortest alias
MODEL_DISPLAY_NAMES = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-haiku-4-5": "Haiku 4.5",  # Legacy alias
    "claude-opus-3-7-20250219": "Opus 3.7",
    "claude-3-5-sonnet-20241022": "Sonnet 3.5",
    "claude-3-5-haiku-20241022": "Haiku 3.5",
    "claude-3-opus-20240229": "Opus 3",
    "claude-3-sonnet-20240229": "Sonnet 3",
    "claude-3-haiku-20240307": "Haiku 3",
}


def resolve_model_name(model_input: Optional[str]) -> Optional[str]:
    """Resolve model alias to full Anthropic model name.

    Args:
        model_input: Short alias (e.g., "cc-opus", "sonnet") or full name

    Returns:
        Full Anthropic model name (e.g., "claude-opus-4-6") or None if input is None

    Examples:
        >>> resolve_model_name("cc-opus")
        'claude-opus-4-6'
        >>> resolve_model_name("sonnet")
        'claude-sonnet-4-6'
        >>> resolve_model_name("claude-opus-4-6")  # Already full name
        'claude-opus-4-6'
        >>> resolve_model_name(None)
        None
    """
    if model_input is None:
        return None

    # Normalize input
    normalized = model_input.strip().lower()

    # Check if it's a known alias
    if normalized in MODEL_ALIASES:
        resolved = MODEL_ALIASES[normalized]
        logger.debug(
            "Resolved model alias",
            input=model_input,
            resolved=resolved,
        )
        return resolved

    # Already a full name or custom model name, return as-is
    logger.debug(
        "Model name passed through (not an alias)",
        input=model_input,
    )
    return model_input


def get_display_name(model_name: Optional[str]) -> str:
    """Get user-friendly display name for a model.

    Args:
        model_name: Full model name or alias

    Returns:
        Short display name (e.g., "Opus 4.6") or original name if unknown

    Examples:
        >>> get_display_name("claude-opus-4-6")
        'Opus 4.6'
        >>> get_display_name("cc-sonnet")
        'Sonnet 4.6'
        >>> get_display_name("custom-model-xyz")
        'custom-model-xyz'
    """
    if not model_name:
        return "default"

    # Resolve alias first
    resolved = resolve_model_name(model_name)
    if not resolved:
        return "default"

    # Look up display name
    display = MODEL_DISPLAY_NAMES.get(resolved)
    if display:
        return display

    # Unknown model, return as-is
    return resolved


def is_valid_model_alias(model_input: str) -> bool:
    """Check if input is a known model alias.

    Args:
        model_input: Model name or alias to check

    Returns:
        True if it's a known alias, False otherwise

    Examples:
        >>> is_valid_model_alias("cc-opus")
        True
        >>> is_valid_model_alias("claude-opus-4-6")
        False  # Full name, not an alias
        >>> is_valid_model_alias("unknown-model")
        False
    """
    return model_input.strip().lower() in MODEL_ALIASES


def get_all_aliases() -> list[str]:
    """Get list of all known model aliases.

    Returns:
        List of alias strings

    Examples:
        >>> aliases = get_all_aliases()
        >>> "cc-opus" in aliases
        True
    """
    return sorted(MODEL_ALIASES.keys())


def get_all_full_names() -> list[str]:
    """Get list of all known full model names.

    Returns:
        List of full Anthropic model names, deduplicated and sorted

    Examples:
        >>> full_names = get_all_full_names()
        >>> "claude-opus-4-6" in full_names
        True
    """
    unique_names = sorted(set(MODEL_ALIASES.values()))
    return unique_names
