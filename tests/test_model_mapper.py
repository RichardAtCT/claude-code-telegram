"""Tests for model name mapper."""

from src.claude.model_mapper import (
    get_all_aliases,
    get_all_full_names,
    get_display_name,
    is_valid_model_alias,
    resolve_model_name,
)


class TestResolveModelName:
    """Test model name resolution."""

    def test_resolve_cc_aliases(self):
        """Test cc-* aliases (common for enterprise)."""
        assert resolve_model_name("cc-opus") == "claude-opus-4-6"
        assert resolve_model_name("cc-sonnet") == "claude-sonnet-4-6"
        assert resolve_model_name("cc-haiku") == "claude-haiku-4-5-20251001"

    def test_resolve_short_aliases(self):
        """Test short aliases (opus, sonnet, haiku)."""
        assert resolve_model_name("opus") == "claude-opus-4-6"
        assert resolve_model_name("sonnet") == "claude-sonnet-4-6"
        assert resolve_model_name("haiku") == "claude-haiku-4-5-20251001"

    def test_resolve_versioned_aliases(self):
        """Test version-specific aliases."""
        assert resolve_model_name("opus-4.6") == "claude-opus-4-6"
        assert resolve_model_name("sonnet-4-6") == "claude-sonnet-4-6"
        assert resolve_model_name("haiku-4.5") == "claude-haiku-4-5-20251001"

    def test_full_name_passthrough(self):
        """Test that full names pass through unchanged."""
        assert resolve_model_name("claude-opus-4-6") == "claude-opus-4-6"
        assert resolve_model_name("claude-sonnet-4-6") == "claude-sonnet-4-6"

    def test_custom_model_passthrough(self):
        """Test that unknown models pass through unchanged."""
        assert resolve_model_name("custom-model-xyz") == "custom-model-xyz"
        assert resolve_model_name("my-enterprise-model") == "my-enterprise-model"

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        assert resolve_model_name("CC-OPUS") == "claude-opus-4-6"
        assert resolve_model_name("Sonnet") == "claude-sonnet-4-6"
        assert resolve_model_name("HAIKU") == "claude-haiku-4-5-20251001"

    def test_whitespace_trimming(self):
        """Test whitespace is trimmed."""
        assert resolve_model_name("  cc-opus  ") == "claude-opus-4-6"
        assert resolve_model_name("\topus\n") == "claude-opus-4-6"

    def test_none_input(self):
        """Test None input returns None."""
        assert resolve_model_name(None) is None


class TestGetDisplayName:
    """Test display name generation."""

    def test_display_name_from_full_name(self):
        """Test display names from full model names."""
        assert get_display_name("claude-opus-4-6") == "Opus 4.6"
        assert get_display_name("claude-sonnet-4-6") == "Sonnet 4.6"
        assert get_display_name("claude-haiku-4-5-20251001") == "Haiku 4.5"

    def test_display_name_from_alias(self):
        """Test display names from aliases."""
        assert get_display_name("cc-opus") == "Opus 4.6"
        assert get_display_name("sonnet") == "Sonnet 4.6"
        assert get_display_name("haiku") == "Haiku 4.5"

    def test_display_name_unknown_model(self):
        """Test unknown models return themselves."""
        assert get_display_name("custom-model") == "custom-model"
        assert get_display_name("unknown") == "unknown"

    def test_display_name_none(self):
        """Test None returns 'default'."""
        assert get_display_name(None) == "default"

    def test_display_name_empty(self):
        """Test empty string returns 'default'."""
        assert get_display_name("") == "default"


class TestIsValidModelAlias:
    """Test alias validation."""

    def test_known_aliases(self):
        """Test known aliases are valid."""
        assert is_valid_model_alias("cc-opus") is True
        assert is_valid_model_alias("sonnet") is True
        assert is_valid_model_alias("haiku-4.5") is True

    def test_full_names_not_aliases(self):
        """Test full names are not considered aliases."""
        assert is_valid_model_alias("claude-opus-4-6") is False
        assert is_valid_model_alias("claude-sonnet-4-6") is False

    def test_unknown_names(self):
        """Test unknown names are not aliases."""
        assert is_valid_model_alias("custom-model") is False
        assert is_valid_model_alias("unknown") is False

    def test_case_insensitive(self):
        """Test case-insensitive validation."""
        assert is_valid_model_alias("CC-OPUS") is True
        assert is_valid_model_alias("Sonnet") is True


class TestGetAllAliases:
    """Test getting all aliases."""

    def test_returns_list(self):
        """Test returns a list."""
        aliases = get_all_aliases()
        assert isinstance(aliases, list)

    def test_contains_known_aliases(self):
        """Test list contains expected aliases."""
        aliases = get_all_aliases()
        assert "cc-opus" in aliases
        assert "sonnet" in aliases
        assert "haiku" in aliases

    def test_sorted(self):
        """Test list is sorted."""
        aliases = get_all_aliases()
        assert aliases == sorted(aliases)


class TestGetAllFullNames:
    """Test getting all full names."""

    def test_returns_list(self):
        """Test returns a list."""
        full_names = get_all_full_names()
        assert isinstance(full_names, list)

    def test_contains_known_models(self):
        """Test list contains expected models."""
        full_names = get_all_full_names()
        assert "claude-opus-4-6" in full_names
        assert "claude-sonnet-4-6" in full_names
        assert "claude-haiku-4-5-20251001" in full_names

    def test_deduplicated(self):
        """Test list has no duplicates."""
        full_names = get_all_full_names()
        assert len(full_names) == len(set(full_names))

    def test_sorted(self):
        """Test list is sorted."""
        full_names = get_all_full_names()
        assert full_names == sorted(full_names)


class TestEndToEndScenarios:
    """Test real-world usage scenarios."""

    def test_enterprise_proxy_scenario(self):
        """Test enterprise proxy with custom model names."""
        # Enterprise might use "cc-opus" internally
        resolved = resolve_model_name("cc-opus")
        assert resolved == "claude-opus-4-6"

        # Display shows friendly name
        display = get_display_name("cc-opus")
        assert display == "Opus 4.6"

    def test_user_types_short_name(self):
        """Test user typing short model name."""
        # User types: /model opus
        resolved = resolve_model_name("opus")
        assert resolved == "claude-opus-4-6"

        # User types: /model haiku
        resolved = resolve_model_name("haiku")
        assert resolved == "claude-haiku-4-5-20251001"

    def test_user_has_custom_model(self):
        """Test custom enterprise model passes through."""
        # Enterprise has custom model "my-fine-tuned-claude"
        resolved = resolve_model_name("my-fine-tuned-claude")
        assert resolved == "my-fine-tuned-claude"

        display = get_display_name("my-fine-tuned-claude")
        assert display == "my-fine-tuned-claude"

    def test_legacy_model_support(self):
        """Test legacy model names work."""
        resolved = resolve_model_name("sonnet-3.5")
        assert resolved == "claude-3-5-sonnet-20241022"

        display = get_display_name("sonnet-3.5")
        assert display == "Sonnet 3.5"
