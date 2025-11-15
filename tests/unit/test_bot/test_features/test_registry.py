"""Tests for feature registry."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.bot.features.registry import FeatureRegistry
from src.config import Settings
from src.security.validators import SecurityValidator
from src.storage.facade import Storage


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def config(temp_dir):
    """Create test configuration."""
    return Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(temp_dir),
        allowed_users=[123456789],
        enable_file_uploads=True,
        enable_git_integration=True,
        enable_quick_actions=True,
    )


@pytest.fixture
def config_minimal(temp_dir):
    """Create minimal configuration with features disabled."""
    return Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(temp_dir),
        allowed_users=[123456789],
        enable_file_uploads=False,
        enable_git_integration=False,
        enable_quick_actions=False,
    )


@pytest.fixture
def storage():
    """Create mock storage."""
    storage = Mock(spec=Storage)
    return storage


@pytest.fixture
def security_validator(temp_dir):
    """Create security validator."""
    return SecurityValidator(temp_dir)


@pytest.fixture
def registry(config, storage, security_validator):
    """Create feature registry instance."""
    return FeatureRegistry(config, storage, security_validator)


class TestFeatureRegistryInitialization:
    """Test FeatureRegistry initialization."""

    def test_initialization(self, registry, config, storage, security_validator):
        """Test registry is properly initialized."""
        assert registry.config == config
        assert registry.storage == storage
        assert registry.security == security_validator
        assert isinstance(registry.features, dict)

    def test_features_initialized(self, registry):
        """Test that features are initialized."""
        # Core features that should always be enabled
        assert "image_handler" in registry.features
        assert "conversation" in registry.features
        assert "session_export" in registry.features

    def test_optional_features_enabled(self, registry, config):
        """Test optional features are enabled when configured."""
        # These depend on config flags being True
        if config.enable_file_uploads:
            assert "file_handler" in registry.features

        if config.enable_git_integration:
            assert "git" in registry.features

        if config.enable_quick_actions:
            assert "quick_actions" in registry.features

    def test_features_disabled_when_configured(self, config_minimal, storage, security_validator):
        """Test features are not initialized when disabled."""
        registry = FeatureRegistry(config_minimal, storage, security_validator)

        # Optional features should not be present
        assert "file_handler" not in registry.features
        assert "git" not in registry.features
        assert "quick_actions" not in registry.features

        # Core features should still be present
        assert "image_handler" in registry.features
        assert "conversation" in registry.features
        assert "session_export" in registry.features


class TestGetFeature:
    """Test get_feature method."""

    def test_get_existing_feature(self, registry):
        """Test getting an existing feature."""
        feature = registry.get_feature("image_handler")
        assert feature is not None

    def test_get_nonexistent_feature(self, registry):
        """Test getting a non-existent feature."""
        feature = registry.get_feature("nonexistent")
        assert feature is None

    def test_get_feature_returns_correct_type(self, registry):
        """Test that get_feature returns the correct feature instance."""
        image_handler = registry.get_feature("image_handler")
        # Check it has expected attributes
        assert hasattr(image_handler, "process_image")
        assert hasattr(image_handler, "supports_format")


class TestIsEnabled:
    """Test is_enabled method."""

    def test_is_enabled_for_active_feature(self, registry):
        """Test is_enabled returns True for active features."""
        assert registry.is_enabled("image_handler") is True
        assert registry.is_enabled("conversation") is True
        assert registry.is_enabled("session_export") is True

    def test_is_enabled_for_inactive_feature(self, registry):
        """Test is_enabled returns False for inactive features."""
        assert registry.is_enabled("nonexistent_feature") is False

    def test_is_enabled_for_disabled_feature(self, config_minimal, storage, security_validator):
        """Test is_enabled for features disabled by config."""
        registry = FeatureRegistry(config_minimal, storage, security_validator)
        assert registry.is_enabled("file_handler") is False
        assert registry.is_enabled("git") is False
        assert registry.is_enabled("quick_actions") is False


class TestGetFileHandler:
    """Test get_file_handler method."""

    def test_get_file_handler_when_enabled(self, config, storage, security_validator):
        """Test getting file handler when enabled."""
        registry = FeatureRegistry(config, storage, security_validator)
        file_handler = registry.get_file_handler()

        if config.enable_file_uploads:
            assert file_handler is not None
        else:
            assert file_handler is None

    def test_get_file_handler_when_disabled(self, config_minimal, storage, security_validator):
        """Test getting file handler when disabled."""
        registry = FeatureRegistry(config_minimal, storage, security_validator)
        file_handler = registry.get_file_handler()
        assert file_handler is None


class TestGetGitIntegration:
    """Test get_git_integration method."""

    def test_get_git_integration_when_enabled(self, config, storage, security_validator):
        """Test getting git integration when enabled."""
        registry = FeatureRegistry(config, storage, security_validator)
        git = registry.get_git_integration()

        if config.enable_git_integration:
            assert git is not None
        else:
            assert git is None

    def test_get_git_integration_when_disabled(self, config_minimal, storage, security_validator):
        """Test getting git integration when disabled."""
        registry = FeatureRegistry(config_minimal, storage, security_validator)
        git = registry.get_git_integration()
        assert git is None


class TestGetQuickActions:
    """Test get_quick_actions method."""

    def test_get_quick_actions_when_enabled(self, config, storage, security_validator):
        """Test getting quick actions when enabled."""
        registry = FeatureRegistry(config, storage, security_validator)
        quick_actions = registry.get_quick_actions()

        if config.enable_quick_actions:
            assert quick_actions is not None
        else:
            assert quick_actions is None

    def test_get_quick_actions_when_disabled(self, config_minimal, storage, security_validator):
        """Test getting quick actions when disabled."""
        registry = FeatureRegistry(config_minimal, storage, security_validator)
        quick_actions = registry.get_quick_actions()
        assert quick_actions is None


class TestGetSessionExport:
    """Test get_session_export method."""

    def test_get_session_export(self, registry):
        """Test getting session export (always enabled)."""
        session_export = registry.get_session_export()
        assert session_export is not None

    def test_session_export_has_storage(self, registry, storage):
        """Test session export is initialized with storage."""
        session_export = registry.get_session_export()
        # Session export should have been initialized with storage
        assert session_export is not None


class TestGetImageHandler:
    """Test get_image_handler method."""

    def test_get_image_handler(self, registry):
        """Test getting image handler (always enabled)."""
        image_handler = registry.get_image_handler()
        assert image_handler is not None

    def test_image_handler_functionality(self, registry):
        """Test image handler has required methods."""
        image_handler = registry.get_image_handler()
        assert hasattr(image_handler, "process_image")
        assert hasattr(image_handler, "validate_image")
        assert hasattr(image_handler, "supports_format")


class TestGetConversationEnhancer:
    """Test get_conversation_enhancer method."""

    def test_get_conversation_enhancer(self, registry):
        """Test getting conversation enhancer (always enabled)."""
        conversation = registry.get_conversation_enhancer()
        assert conversation is not None

    def test_conversation_enhancer_functionality(self, registry):
        """Test conversation enhancer has required methods."""
        conversation = registry.get_conversation_enhancer()
        assert hasattr(conversation, "update_context")
        assert hasattr(conversation, "generate_follow_up_suggestions")
        assert hasattr(conversation, "create_follow_up_keyboard")


class TestGetEnabledFeatures:
    """Test get_enabled_features method."""

    def test_get_enabled_features(self, registry):
        """Test getting all enabled features."""
        features = registry.get_enabled_features()
        assert isinstance(features, dict)
        assert len(features) >= 3  # At least core features

    def test_get_enabled_features_returns_copy(self, registry):
        """Test that get_enabled_features returns a copy."""
        features1 = registry.get_enabled_features()
        features2 = registry.get_enabled_features()

        # Should be equal but not the same object
        assert features1 == features2
        assert features1 is not features2

    def test_get_enabled_features_modification_safe(self, registry):
        """Test that modifying returned dict doesn't affect registry."""
        features = registry.get_enabled_features()
        original_len = len(features)

        # Modify the returned dict
        features["new_feature"] = "test"

        # Registry should be unchanged
        assert len(registry.get_enabled_features()) == original_len


class TestShutdown:
    """Test shutdown method."""

    def test_shutdown_clears_features(self, registry):
        """Test that shutdown clears features."""
        # Verify features exist
        assert len(registry.features) > 0

        registry.shutdown()

        # Features should be cleared
        assert len(registry.features) == 0

    def test_shutdown_clears_conversation_contexts(self, registry):
        """Test that shutdown clears conversation contexts."""
        conversation = registry.get_conversation_enhancer()

        # Add some test context
        if conversation:
            conversation.get_or_create_context(123456)
            conversation.get_or_create_context(789012)
            assert len(conversation.conversation_contexts) > 0

        registry.shutdown()

        # Contexts should be cleared
        if conversation:
            assert len(conversation.conversation_contexts) == 0

    def test_shutdown_idempotent(self, registry):
        """Test that shutdown can be called multiple times."""
        registry.shutdown()
        registry.shutdown()  # Should not raise error

        assert len(registry.features) == 0


class TestFeatureInitializationErrors:
    """Test error handling during feature initialization."""

    @patch("src.bot.features.registry.FileHandler")
    def test_file_handler_initialization_error(
        self, mock_file_handler, config, storage, security_validator
    ):
        """Test handling of file handler initialization error."""
        mock_file_handler.side_effect = Exception("Initialization failed")

        # Should not raise, just log the error
        registry = FeatureRegistry(config, storage, security_validator)

        # File handler should not be in features
        assert "file_handler" not in registry.features

        # Other features should still be initialized
        assert "image_handler" in registry.features

    @patch("src.bot.features.registry.GitIntegration")
    def test_git_integration_initialization_error(
        self, mock_git, config, storage, security_validator
    ):
        """Test handling of git integration initialization error."""
        mock_git.side_effect = Exception("Git init failed")

        registry = FeatureRegistry(config, storage, security_validator)

        # Git should not be in features
        assert "git" not in registry.features

        # Other features should still be initialized
        assert "image_handler" in registry.features

    @patch("src.bot.features.registry.ImageHandler")
    def test_image_handler_initialization_error(
        self, mock_image_handler, config, storage, security_validator
    ):
        """Test handling of image handler initialization error."""
        mock_image_handler.side_effect = Exception("Image handler init failed")

        registry = FeatureRegistry(config, storage, security_validator)

        # Image handler should not be in features
        assert "image_handler" not in registry.features

        # Other features should still be initialized
        assert "conversation" in registry.features


class TestFeatureGetterMethods:
    """Test all feature getter methods."""

    def test_all_getters_return_none_after_shutdown(self, registry):
        """Test that all getters return None after shutdown."""
        registry.shutdown()

        assert registry.get_file_handler() is None
        assert registry.get_git_integration() is None
        assert registry.get_quick_actions() is None
        assert registry.get_session_export() is None
        assert registry.get_image_handler() is None
        assert registry.get_conversation_enhancer() is None

    def test_getters_use_get_feature(self, registry):
        """Test that specific getters use the get_feature method."""
        # Verify getters return same instances as get_feature
        assert registry.get_file_handler() == registry.get_feature("file_handler")
        assert registry.get_git_integration() == registry.get_feature("git")
        assert registry.get_quick_actions() == registry.get_feature("quick_actions")
        assert registry.get_session_export() == registry.get_feature("session_export")
        assert registry.get_image_handler() == registry.get_feature("image_handler")
        assert registry.get_conversation_enhancer() == registry.get_feature("conversation")
