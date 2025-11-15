"""Test configuration loading."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config.loader import (
    _apply_environment_overrides,
    _get_enabled_features_summary,
    _validate_config,
    create_test_config,
    load_config,
)
from src.exceptions import ConfigurationError, InvalidConfigError


class TestLoadConfig:
    """Test load_config function."""

    def test_load_config_development(self, tmp_path):
        """Test loading development configuration."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test_token\n"
            "TELEGRAM_BOT_USERNAME=test_bot\n"
            f"APPROVED_DIRECTORY={tmp_path}\n"
        )

        config = load_config(env="development", config_file=env_file)

        assert config.debug is True
        assert config.development_mode is True
        assert config.telegram_bot_token.get_secret_value() == "test_token"
        assert config.telegram_bot_username == "test_bot"

    def test_load_config_testing(self, tmp_path):
        """Test loading testing configuration."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test_token\n"
            "TELEGRAM_BOT_USERNAME=test_bot\n"
            f"APPROVED_DIRECTORY={tmp_path}\n"
        )

        config = load_config(env="testing", config_file=env_file)

        assert config.debug is True
        assert config.development_mode is True
        assert config.database_url == "sqlite:///:memory:"

    def test_load_config_production(self, tmp_path):
        """Test loading production configuration."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test_token\n"
            "TELEGRAM_BOT_USERNAME=test_bot\n"
            f"APPROVED_DIRECTORY={tmp_path}\n"
        )

        config = load_config(env="production", config_file=env_file)

        assert config.debug is False
        assert config.development_mode is False
        assert config.enable_telemetry is True

    def test_load_config_no_env_file(self, tmp_path):
        """Test loading config when .env file doesn't exist."""
        non_existent = tmp_path / "nonexistent.env"

        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "test_token",
                "TELEGRAM_BOT_USERNAME": "test_bot",
                "APPROVED_DIRECTORY": str(tmp_path),
            },
        ):
            config = load_config(env="testing", config_file=non_existent)
            assert config.telegram_bot_token.get_secret_value() == "test_token"

    def test_load_config_unknown_environment(self, tmp_path):
        """Test loading config with unknown environment."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test_token\n"
            "TELEGRAM_BOT_USERNAME=test_bot\n"
            f"APPROVED_DIRECTORY={tmp_path}\n"
        )

        # Should load without error, using default settings
        config = load_config(env="unknown", config_file=env_file)
        assert config.telegram_bot_token.get_secret_value() == "test_token"

    def test_load_config_from_environment_variable(self, tmp_path):
        """Test loading config from ENVIRONMENT variable."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test_token\n"
            "TELEGRAM_BOT_USERNAME=test_bot\n"
            f"APPROVED_DIRECTORY={tmp_path}\n"
            "ENVIRONMENT=production\n"
        )

        config = load_config(config_file=env_file)
        assert config.debug is False  # production default

    def test_load_config_validation_error_rate_limit(self, tmp_path):
        """Test configuration loading with validation error."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TELEGRAM_BOT_TOKEN=test_token\n"
            "TELEGRAM_BOT_USERNAME=test_bot\n"
            f"APPROVED_DIRECTORY={tmp_path}\n"
            "RATE_LIMIT_REQUESTS=-1\n"  # Invalid: must be positive
        )

        with pytest.raises(ConfigurationError, match="Configuration loading failed"):
            load_config(env="testing", config_file=env_file)


class TestApplyEnvironmentOverrides:
    """Test _apply_environment_overrides function."""

    def test_apply_development_overrides(self, tmp_path):
        """Test applying development environment overrides."""
        config = create_test_config(approved_directory=str(tmp_path))
        config = _apply_environment_overrides(config, "development")

        assert config.debug is True
        assert config.development_mode is True
        assert config.log_level == "DEBUG"

    def test_apply_testing_overrides(self, tmp_path):
        """Test applying testing environment overrides."""
        config = create_test_config(approved_directory=str(tmp_path))
        config = _apply_environment_overrides(config, "testing")

        assert config.debug is True
        assert config.database_url == "sqlite:///:memory:"

    def test_apply_production_overrides(self, tmp_path):
        """Test applying production environment overrides."""
        config = create_test_config(approved_directory=str(tmp_path))
        config = _apply_environment_overrides(config, "production")

        assert config.debug is False
        assert config.development_mode is False
        assert config.enable_telemetry is True

    def test_apply_unknown_environment(self, tmp_path):
        """Test applying overrides with unknown environment."""
        config = create_test_config(approved_directory=str(tmp_path))
        original_debug = config.debug

        config = _apply_environment_overrides(config, "unknown_env")

        # Should keep original values
        assert config.debug == original_debug


class TestValidateConfig:
    """Test _validate_config function."""

    def test_validate_config_success(self, tmp_path):
        """Test successful configuration validation."""
        config = create_test_config(approved_directory=str(tmp_path))
        _validate_config(config)  # Should not raise

    def test_validate_config_non_readable_directory(self, tmp_path):
        """Test validation with non-readable directory."""
        # Skip this test on systems where we can't set restrictive permissions
        # (e.g., when running as root in Docker)
        import os
        if os.geteuid() == 0:
            pytest.skip("Cannot test permission restrictions as root")

        # Create directory first so Settings validation passes
        readable = tmp_path / "testdir"
        readable.mkdir()

        config = create_test_config(approved_directory=str(readable))

        # Make non-readable after config creation
        readable.chmod(0o000)

        try:
            with pytest.raises(InvalidConfigError, match="Cannot access approved directory"):
                _validate_config(config)
        finally:
            readable.chmod(0o755)

    def test_validate_config_mcp_enabled(self, tmp_path):
        """Test validation with MCP enabled and valid config path."""
        # Create MCP config file
        mcp_config = tmp_path / "mcp.json"
        mcp_config.write_text('{"servers": {}}')

        config = create_test_config(
            approved_directory=str(tmp_path),
            enable_mcp=True,
            mcp_config_path=str(mcp_config)
        )

        # Should not raise
        _validate_config(config)

    def test_validate_config_token_auth_enabled(self, tmp_path):
        """Test validation with token auth enabled and secret provided."""
        config = create_test_config(
            approved_directory=str(tmp_path),
            enable_token_auth=True,
            auth_token_secret="test_secret",
        )

        # Should not raise
        _validate_config(config)

    def test_validate_config_negative_rate_limit_requests(self, tmp_path):
        """Test validation with negative rate limit requests."""
        config = create_test_config(
            approved_directory=str(tmp_path), rate_limit_requests=0
        )

        with pytest.raises(InvalidConfigError, match="rate_limit_requests must be positive"):
            _validate_config(config)

    def test_validate_config_negative_rate_limit_window(self, tmp_path):
        """Test validation with negative rate limit window."""
        config = create_test_config(
            approved_directory=str(tmp_path), rate_limit_window=0
        )

        with pytest.raises(InvalidConfigError, match="rate_limit_window must be positive"):
            _validate_config(config)

    def test_validate_config_negative_timeout(self, tmp_path):
        """Test validation with negative timeout."""
        config = create_test_config(
            approved_directory=str(tmp_path), claude_timeout_seconds=-1
        )

        with pytest.raises(InvalidConfigError, match="claude_timeout_seconds must be positive"):
            _validate_config(config)

    def test_validate_config_negative_cost_limit(self, tmp_path):
        """Test validation with negative cost limit."""
        config = create_test_config(
            approved_directory=str(tmp_path), claude_max_cost_per_user=-1
        )

        with pytest.raises(InvalidConfigError, match="claude_max_cost_per_user must be positive"):
            _validate_config(config)

    def test_validate_config_sqlite_creates_parent_directory(self, tmp_path):
        """Test that SQLite database parent directory is created."""
        db_path = tmp_path / "data" / "db" / "test.db"
        config = create_test_config(
            approved_directory=str(tmp_path),
            database_url=f"sqlite:///{db_path}",
        )

        _validate_config(config)

        # Parent directory should be created
        assert db_path.parent.exists()


class TestGetEnabledFeaturesSummary:
    """Test _get_enabled_features_summary function."""

    def test_get_enabled_features_all_disabled(self, tmp_path):
        """Test getting features summary when all disabled."""
        config = create_test_config(
            approved_directory=str(tmp_path),
            enable_mcp=False,
            enable_git_integration=False,
            enable_file_uploads=False,
            enable_quick_actions=False,
            enable_token_auth=False,
            webhook_url=None,
        )

        features = _get_enabled_features_summary(config)
        assert features == []

    def test_get_enabled_features_all_enabled(self, tmp_path):
        """Test getting features summary when all enabled."""
        # Create MCP config file
        mcp_config = tmp_path / "mcp.json"
        mcp_config.write_text('{"servers": {}}')

        config = create_test_config(
            approved_directory=str(tmp_path),
            enable_mcp=True,
            mcp_config_path=str(mcp_config),
            enable_git_integration=True,
            enable_file_uploads=True,
            enable_quick_actions=True,
            enable_token_auth=True,
            auth_token_secret="secret",
            webhook_url="https://example.com/webhook",
        )

        features = _get_enabled_features_summary(config)
        assert "mcp" in features
        assert "git" in features
        assert "file_uploads" in features
        assert "quick_actions" in features
        assert "token_auth" in features
        assert "webhook" in features

    def test_get_enabled_features_partial(self, tmp_path):
        """Test getting features summary with some enabled."""
        config = create_test_config(
            approved_directory=str(tmp_path),
            enable_git_integration=True,
            enable_quick_actions=True,
        )

        features = _get_enabled_features_summary(config)
        assert "git" in features
        assert "quick_actions" in features
        assert "mcp" not in features


class TestCreateTestConfig:
    """Test create_test_config function."""

    def test_create_test_config_defaults(self):
        """Test creating test config with defaults."""
        config = create_test_config()

        assert config.telegram_bot_token.get_secret_value() == "test_token_123"
        assert config.telegram_bot_username == "test_bot"
        assert config.debug is True
        assert Path(config.approved_directory).exists()

    def test_create_test_config_with_overrides(self, tmp_path):
        """Test creating test config with overrides."""
        config = create_test_config(
            telegram_bot_token="custom_token",
            telegram_bot_username="custom_bot",
            approved_directory=str(tmp_path),
        )

        assert config.telegram_bot_token.get_secret_value() == "custom_token"
        assert config.telegram_bot_username == "custom_bot"
        assert str(config.approved_directory) == str(tmp_path)

    def test_create_test_config_creates_directory(self, tmp_path):
        """Test that test config creates approved directory."""
        test_dir = tmp_path / "test_projects"
        config = create_test_config(approved_directory=str(test_dir))

        assert test_dir.exists()
        assert config.approved_directory == test_dir
