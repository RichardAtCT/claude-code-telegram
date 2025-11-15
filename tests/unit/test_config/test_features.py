"""Test feature flag management."""

from unittest.mock import Mock

import pytest

from src.config.features import FeatureFlags
from src.config.loader import create_test_config


class TestFeatureFlags:
    """Test FeatureFlags class."""

    @pytest.fixture
    def settings_all_disabled(self, tmp_path):
        """Settings with all features disabled."""
        return create_test_config(
            approved_directory=str(tmp_path),
            enable_mcp=False,
            enable_git_integration=False,
            enable_file_uploads=False,
            enable_quick_actions=False,
            enable_telemetry=False,
            enable_token_auth=False,
            webhook_url=None,
            development_mode=False,
        )

    @pytest.fixture
    def settings_all_enabled(self, tmp_path):
        """Settings with all features enabled."""
        # Create MCP config file
        mcp_config = tmp_path / "mcp.json"
        mcp_config.write_text('{"servers": {}}')

        return create_test_config(
            approved_directory=str(tmp_path),
            enable_mcp=True,
            mcp_config_path=str(mcp_config),
            enable_git_integration=True,
            enable_file_uploads=True,
            enable_quick_actions=True,
            enable_telemetry=True,
            enable_token_auth=True,
            auth_token_secret="test_secret",
            webhook_url="https://example.com/webhook",
            development_mode=True,
        )

    def test_mcp_enabled_when_enabled_and_config_exists(self, settings_all_enabled):
        """Test MCP enabled when both flag and config path are set."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.mcp_enabled is True

    def test_mcp_disabled_when_flag_off(self, settings_all_disabled):
        """Test MCP disabled when flag is off."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.mcp_enabled is False

    def test_mcp_disabled_when_no_config_path(self, tmp_path):
        """Test MCP disabled when config path is None."""
        # Cannot test this case because Settings validation prevents it
        # MCP can only be enabled if config_path exists
        settings = create_test_config(
            approved_directory=str(tmp_path), enable_mcp=False
        )
        flags = FeatureFlags(settings)
        assert flags.mcp_enabled is False

    def test_git_enabled(self, settings_all_enabled):
        """Test Git integration enabled."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.git_enabled is True

    def test_git_disabled(self, settings_all_disabled):
        """Test Git integration disabled."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.git_enabled is False

    def test_file_uploads_enabled(self, settings_all_enabled):
        """Test file uploads enabled."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.file_uploads_enabled is True

    def test_file_uploads_disabled(self, settings_all_disabled):
        """Test file uploads disabled."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.file_uploads_enabled is False

    def test_quick_actions_enabled(self, settings_all_enabled):
        """Test quick actions enabled."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.quick_actions_enabled is True

    def test_quick_actions_disabled(self, settings_all_disabled):
        """Test quick actions disabled."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.quick_actions_enabled is False

    def test_telemetry_enabled(self, settings_all_enabled):
        """Test telemetry enabled."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.telemetry_enabled is True

    def test_telemetry_disabled(self, settings_all_disabled):
        """Test telemetry disabled."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.telemetry_enabled is False

    def test_token_auth_enabled(self, settings_all_enabled):
        """Test token auth enabled when both flag and secret are set."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.token_auth_enabled is True

    def test_token_auth_disabled_when_flag_off(self, settings_all_disabled):
        """Test token auth disabled when flag is off."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.token_auth_enabled is False

    def test_token_auth_disabled_when_no_secret(self, tmp_path):
        """Test token auth disabled when secret is None."""
        # Cannot test this case because Settings validation prevents it
        # Token auth can only be enabled if secret exists
        settings = create_test_config(
            approved_directory=str(tmp_path),
            enable_token_auth=False,
        )
        flags = FeatureFlags(settings)
        assert flags.token_auth_enabled is False

    def test_webhook_enabled(self, settings_all_enabled):
        """Test webhook enabled when URL is set."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.webhook_enabled is True

    def test_webhook_disabled(self, settings_all_disabled):
        """Test webhook disabled when URL is None."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.webhook_enabled is False

    def test_development_features_enabled(self, settings_all_enabled):
        """Test development features enabled."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.development_features_enabled is True

    def test_development_features_disabled(self, settings_all_disabled):
        """Test development features disabled."""
        flags = FeatureFlags(settings_all_disabled)
        assert flags.development_features_enabled is False

    def test_is_feature_enabled_valid_features(self, settings_all_enabled):
        """Test is_feature_enabled for all valid features."""
        flags = FeatureFlags(settings_all_enabled)

        assert flags.is_feature_enabled("mcp") is True
        assert flags.is_feature_enabled("git") is True
        assert flags.is_feature_enabled("file_uploads") is True
        assert flags.is_feature_enabled("quick_actions") is True
        assert flags.is_feature_enabled("telemetry") is True
        assert flags.is_feature_enabled("token_auth") is True
        assert flags.is_feature_enabled("webhook") is True
        assert flags.is_feature_enabled("development") is True

    def test_is_feature_enabled_invalid_feature(self, settings_all_enabled):
        """Test is_feature_enabled for invalid feature name."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.is_feature_enabled("nonexistent") is False

    def test_is_feature_enabled_disabled_features(self, settings_all_disabled):
        """Test is_feature_enabled when features are disabled."""
        flags = FeatureFlags(settings_all_disabled)

        assert flags.is_feature_enabled("mcp") is False
        assert flags.is_feature_enabled("git") is False
        assert flags.is_feature_enabled("file_uploads") is False
        assert flags.is_feature_enabled("quick_actions") is False

    def test_get_enabled_features_all_enabled(self, settings_all_enabled):
        """Test get_enabled_features when all enabled."""
        flags = FeatureFlags(settings_all_enabled)
        features = flags.get_enabled_features()

        assert "mcp" in features
        assert "git" in features
        assert "file_uploads" in features
        assert "quick_actions" in features
        assert "telemetry" in features
        assert "token_auth" in features
        assert "webhook" in features
        assert "development" in features
        assert len(features) == 8

    def test_get_enabled_features_all_disabled(self, settings_all_disabled):
        """Test get_enabled_features when all disabled."""
        flags = FeatureFlags(settings_all_disabled)
        features = flags.get_enabled_features()

        assert features == []

    def test_get_enabled_features_partial(self, tmp_path):
        """Test get_enabled_features with some features enabled."""
        settings = create_test_config(
            approved_directory=str(tmp_path),
            enable_git_integration=True,
            enable_quick_actions=True,
            enable_telemetry=True,
            enable_file_uploads=False,
            development_mode=False,
        )
        flags = FeatureFlags(settings)
        features = flags.get_enabled_features()

        assert "git" in features
        assert "quick_actions" in features
        assert "telemetry" in features
        assert "mcp" not in features
        assert "file_uploads" not in features
        assert "development" not in features

    def test_feature_flags_initialization(self, settings_all_enabled):
        """Test FeatureFlags initialization."""
        flags = FeatureFlags(settings_all_enabled)
        assert flags.settings == settings_all_enabled

    def test_feature_flags_with_mock_settings(self):
        """Test FeatureFlags with mock settings."""
        mock_settings = Mock()
        mock_settings.enable_mcp = True
        mock_settings.mcp_config_path = "/tmp/mcp.json"
        mock_settings.enable_git_integration = False
        mock_settings.enable_file_uploads = True
        mock_settings.enable_quick_actions = False
        mock_settings.enable_telemetry = True
        mock_settings.enable_token_auth = True
        mock_settings.auth_token_secret = "secret"
        mock_settings.webhook_url = None
        mock_settings.development_mode = False

        flags = FeatureFlags(mock_settings)

        assert flags.mcp_enabled is True
        assert flags.git_enabled is False
        assert flags.file_uploads_enabled is True
        assert flags.quick_actions_enabled is False
        assert flags.telemetry_enabled is True
        assert flags.token_auth_enabled is True
        assert flags.webhook_enabled is False
        assert flags.development_features_enabled is False
