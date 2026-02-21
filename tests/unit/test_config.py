"""Test configuration loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings, create_test_config, load_config
from src.config.features import FeatureFlags
from src.exceptions import ConfigurationError


def test_settings_validation_required_fields(monkeypatch):
    """Test that missing required fields raise validation errors."""
    # Clear any environment variables that might provide defaults
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
    monkeypatch.delenv("APPROVED_DIRECTORY", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    errors = exc_info.value.errors()
    required_fields = {error["loc"][0] for error in errors}
    assert "telegram_bot_token" in required_fields
    assert "telegram_bot_username" in required_fields


def test_settings_with_valid_data(tmp_path):
    """Test settings creation with valid data."""
    test_dir = tmp_path / "projects"
    test_dir.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
    )

    assert settings.telegram_token_str == "test_token"
    assert settings.telegram_bot_username == "test_bot"
    assert settings.approved_directory == test_dir


def test_allowed_users_parsing():
    """Test parsing of comma-separated user IDs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=tmp_dir,
            allowed_users="123,456,789",
        )

        assert settings.allowed_users == [123, 456, 789]


def test_allowed_users_parsing_with_spaces():
    """Test parsing with spaces around user IDs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        settings = Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=tmp_dir,
            allowed_users="123, 456 , 789",
        )

        assert settings.allowed_users == [123, 456, 789]


def test_security_relaxation_settings_defaults_and_overrides():
    """Security relaxation settings should default to False and be configurable."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        defaults = Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=tmp_dir,
        )
        assert defaults.disable_security_patterns is False
        assert defaults.disable_tool_validation is False

        overridden = Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=tmp_dir,
            disable_security_patterns=True,
            disable_tool_validation=True,
        )
        assert overridden.disable_security_patterns is True
        assert overridden.disable_tool_validation is True


def test_approved_directory_validation_nonexistent():
    """Test validation fails for non-existent directory."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory="/nonexistent/directory",
        )

    assert "does not exist" in str(exc_info.value)


def test_approved_directory_validation_not_directory(tmp_path):
    """Test validation fails when path is not a directory."""
    test_file = tmp_path / "not_a_dir.txt"
    test_file.write_text("test")

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(test_file),
        )

    assert "not a directory" in str(exc_info.value)


def test_approved_directories_string_parsing(tmp_path):
    """Test parsing of comma-separated approved_directories_str."""
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    dir1.mkdir()
    dir2.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(dir1),
        approved_directories_str=f"{dir1},{dir2}",
    )

    assert len(settings.approved_directories) == 2
    assert dir1.resolve() in settings.approved_directories
    assert dir2.resolve() in settings.approved_directories


def test_approved_directories_without_single_directory(tmp_path):
    """Test approved_directories without approved_directory."""
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    dir1.mkdir()
    dir2.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directories_str=f"{dir1},{dir2}",
        _env_file=None,
    )

    assert settings.approved_directories == [dir1.resolve(), dir2.resolve()]
    assert settings.approved_directory == dir1.resolve()


def test_approved_directories_string_with_spaces(tmp_path):
    """Test parsing with spaces around directories."""
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    dir1.mkdir()
    dir2.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(dir1),
        approved_directories_str=f" {dir1} , {dir2} ",
    )

    assert len(settings.approved_directories) == 2
    assert dir1.resolve() in settings.approved_directories
    assert dir2.resolve() in settings.approved_directories


def test_approved_directories_loaded_from_env_alias(monkeypatch, tmp_path):
    """Test APPROVED_DIRECTORIES env var maps to approved_directories_str."""
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    dir1.mkdir()
    dir2.mkdir()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "test_bot")
    monkeypatch.setenv("APPROVED_DIRECTORY", str(dir1))
    monkeypatch.setenv("APPROVED_DIRECTORIES", f"{dir1},{dir2}")

    settings = Settings(_env_file=None)

    assert settings.approved_directories_str == f"{dir1},{dir2}"
    assert settings.approved_directories == [dir1.resolve(), dir2.resolve()]


def test_approved_directories_fallback_to_single(tmp_path):
    """Test that approved_directories falls back to approved_directory."""
    test_dir = tmp_path / "projects"
    test_dir.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
    )

    assert settings.approved_directories == [test_dir.resolve()]


def test_approved_directories_empty_string_fallback(tmp_path):
    """Test that empty approved_directories_str falls back to approved_directory."""
    test_dir = tmp_path / "projects"
    test_dir.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
        approved_directories_str="",
    )

    assert settings.approved_directories == [test_dir.resolve()]

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=None,
            approved_directories_str="",
            _env_file=None,
        )

    assert "Either APPROVED_DIRECTORY or APPROVED_DIRECTORIES must be set" in str(
        exc_info.value
    )


def test_approved_directories_whitespace_only_fallback(tmp_path):
    """Test that whitespace-only approved_directories_str falls back."""
    test_dir = tmp_path / "projects"
    test_dir.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
        approved_directories_str="   ,  ,  ",
    )

    assert settings.approved_directories == [test_dir.resolve()]


def test_approved_directories_nonexistent_directory(tmp_path):
    """Test validation fails for non-existent directory in list."""
    dir1 = tmp_path / "dir1"
    dir1.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(dir1),
            approved_directories_str=f"{dir1},/nonexistent/directory",
        )

    assert "does not exist" in str(exc_info.value)


def test_approved_directories_file_not_directory(tmp_path):
    """Test validation fails when path is a file, not directory."""
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    file1 = tmp_path / "file.txt"
    file1.write_text("test")

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(dir1),
            approved_directories_str=f"{dir1},{file1}",
        )

    assert "not a directory" in str(exc_info.value)


def test_format_relative_path_single_root(tmp_path):
    """With a single root, format_relative_path returns plain relative path."""
    root = tmp_path / "projects"
    root.mkdir()
    child = root / "myapp"
    child.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(root),
    )

    assert settings.format_relative_path(child) == "myapp"
    assert settings.format_relative_path(root) == "."


def test_format_relative_path_multiple_roots(tmp_path):
    """With multiple roots, format_relative_path prefixes with root name."""
    root1 = tmp_path / "work"
    root2 = tmp_path / "personal"
    root1.mkdir()
    root2.mkdir()
    child1 = root1 / "repo"
    child2 = root2 / "blog"
    child1.mkdir()
    child2.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(root1),
        approved_directories_str=f"{root1},{root2}",
    )

    assert settings.format_relative_path(child1) == "work/repo"
    assert settings.format_relative_path(child2) == "personal/blog"
    # Path that equals a root shows just the root name
    assert settings.format_relative_path(root1) == "work"
    assert settings.format_relative_path(root2) == "personal"


def test_get_approved_root_for_path_exact_root(tmp_path):
    """get_approved_root_for_path returns root when path equals the root itself."""
    root = tmp_path / "projects"
    root.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(root),
    )

    assert settings.get_approved_root_for_path(root) == root.resolve()


def test_get_approved_root_for_path_child(tmp_path):
    """get_approved_root_for_path returns correct root for a nested path."""
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()
    child = root2 / "deep" / "dir"
    child.mkdir(parents=True)

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(root1),
        approved_directories_str=f"{root1},{root2}",
    )

    assert settings.get_approved_root_for_path(child) == root2.resolve()


def test_get_approved_root_for_path_outside(tmp_path):
    """get_approved_root_for_path returns None when path is outside all roots."""
    root = tmp_path / "projects"
    root.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(root),
    )

    assert settings.get_approved_root_for_path(outside) is None


def test_auth_token_validation():
    """Test auth token secret validation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Should fail when token auth enabled but no secret
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                telegram_bot_token="test_token",
                telegram_bot_username="test_bot",
                approved_directory=tmp_dir,
                enable_token_auth=True,
            )

        assert "auth_token_secret required" in str(exc_info.value)

        # Should succeed when both enabled and secret provided
        settings = Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=tmp_dir,
            enable_token_auth=True,
            auth_token_secret="secret123",
        )

        assert settings.enable_token_auth is True
        assert settings.auth_secret_str == "secret123"


def test_mcp_config_validation(tmp_path, monkeypatch):
    """Test MCP configuration validation."""
    test_dir = tmp_path / "projects"
    test_dir.mkdir()

    # Clear any MCP-related environment variables
    monkeypatch.delenv("ENABLE_MCP", raising=False)
    monkeypatch.delenv("MCP_CONFIG_PATH", raising=False)

    # Should fail when MCP enabled but no config path
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(test_dir),
            enable_mcp=True,
            mcp_config_path=None,
        )

    assert "mcp_config_path required" in str(exc_info.value)

    # Should fail when config file doesn't exist
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(test_dir),
            enable_mcp=True,
            mcp_config_path="/nonexistent/config.json",
        )

    assert "does not exist" in str(exc_info.value)

    # Should fail when config file is not valid JSON
    bad_json_file = tmp_path / "bad.json"
    bad_json_file.write_text("not json at all")

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(test_dir),
            enable_mcp=True,
            mcp_config_path=str(bad_json_file),
        )

    assert "not valid JSON" in str(exc_info.value)

    # Should fail when config file is missing mcpServers key
    no_servers_file = tmp_path / "no_servers.json"
    no_servers_file.write_text('{"test": true}')

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(test_dir),
            enable_mcp=True,
            mcp_config_path=str(no_servers_file),
        )

    assert "mcpServers" in str(exc_info.value)

    # Should fail when mcpServers is empty
    empty_servers_file = tmp_path / "empty_servers.json"
    empty_servers_file.write_text('{"mcpServers": {}}')

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(test_dir),
            enable_mcp=True,
            mcp_config_path=str(empty_servers_file),
        )

    assert "at least one server" in str(exc_info.value)

    # Should succeed with valid MCP config
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(
        '{"mcpServers": {"my-server": '
        '{"command": "npx", "args": ["-y", "my-mcp-server"]}}}'
    )

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
        enable_mcp=True,
        mcp_config_path=str(config_file),
    )

    assert settings.enable_mcp is True
    assert settings.mcp_config_path == config_file


def test_log_level_validation():
    """Test log level validation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Should fail with invalid log level
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                telegram_bot_token="test_token",
                telegram_bot_username="test_bot",
                approved_directory=tmp_dir,
                log_level="INVALID",
            )

        assert "must be one of" in str(exc_info.value)

        # Should succeed with valid log level
        settings = Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=tmp_dir,
            log_level="debug",  # Should be converted to uppercase
        )

        assert settings.log_level == "DEBUG"


def test_project_threads_validation_requires_chat_id_in_group_mode(tmp_path):
    """Group thread mode requires project_threads_chat_id."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()
    app_dir = project_dir / "app"
    app_dir.mkdir()
    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n  - slug: app\n    name: App\n    path: app\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(project_dir),
            enable_project_threads=True,
            project_threads_mode="group",
            projects_config_path=str(config_file),
        )

    assert "project_threads_chat_id required" in str(exc_info.value)


def test_project_threads_validation_requires_projects_config(tmp_path):
    """Thread mode requires projects_config_path."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(project_dir),
            enable_project_threads=True,
            project_threads_chat_id=-1001234567890,
            projects_config_path=None,
        )

    assert "projects_config_path required" in str(exc_info.value)


def test_project_threads_validation_blank_projects_config_path_fails(tmp_path):
    """Blank projects_config_path should be treated as missing."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(project_dir),
            enable_project_threads=True,
            project_threads_mode="private",
            projects_config_path="",
        )

    assert "projects_config_path required" in str(exc_info.value)


def test_project_threads_validation_private_mode_no_chat_id(tmp_path):
    """Private thread mode does not require project_threads_chat_id."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()
    app_dir = project_dir / "app"
    app_dir.mkdir()
    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n  - slug: app\n    name: App\n    path: app\n",
        encoding="utf-8",
    )

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(project_dir),
        enable_project_threads=True,
        project_threads_mode="private",
        projects_config_path=str(config_file),
    )

    assert settings.project_threads_mode == "private"
    assert settings.project_threads_chat_id is None


def test_project_threads_validation_private_mode_empty_chat_id(tmp_path):
    """Private mode accepts blank project_threads_chat_id from env/.env."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()
    app_dir = project_dir / "app"
    app_dir.mkdir()
    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n  - slug: app\n    name: App\n    path: app\n",
        encoding="utf-8",
    )

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(project_dir),
        enable_project_threads=True,
        project_threads_mode="private",
        project_threads_chat_id="",
        projects_config_path=str(config_file),
    )

    assert settings.project_threads_mode == "private"
    assert settings.project_threads_chat_id is None


def test_project_threads_validation_group_mode_empty_chat_id_fails(tmp_path):
    """Group mode rejects blank project_threads_chat_id."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()
    app_dir = project_dir / "app"
    app_dir.mkdir()
    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n  - slug: app\n    name: App\n    path: app\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(project_dir),
            enable_project_threads=True,
            project_threads_mode="group",
            project_threads_chat_id="",
            projects_config_path=str(config_file),
        )

    assert "project_threads_chat_id required" in str(exc_info.value)


def test_project_threads_sync_action_interval_validation(tmp_path):
    """Thread sync action interval should accept non-negative values only."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(project_dir),
        project_threads_sync_action_interval_seconds=0,
    )
    assert settings.project_threads_sync_action_interval_seconds == 0

    settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(project_dir),
        project_threads_sync_action_interval_seconds="1.1",
    )
    assert settings.project_threads_sync_action_interval_seconds == pytest.approx(1.1)

    with pytest.raises(ValidationError):
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(project_dir),
            project_threads_sync_action_interval_seconds=-0.1,
        )


def test_project_threads_validation_invalid_mode(tmp_path):
    """Invalid project thread mode should fail validation."""
    project_dir = tmp_path / "projects"
    project_dir.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            telegram_bot_token="test_token",
            telegram_bot_username="test_bot",
            approved_directory=str(project_dir),
            enable_project_threads=True,
            project_threads_mode="invalid",
        )

    assert "project_threads_mode must be one of" in str(exc_info.value)


def test_computed_properties(tmp_path):
    """Test computed properties."""
    test_dir = tmp_path / "projects"
    test_dir.mkdir()

    # Test production mode detection
    dev_settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
        debug=True,
    )
    assert dev_settings.is_production is False

    prod_settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
        debug=False,
        development_mode=False,
    )
    assert prod_settings.is_production is True

    # Test database path extraction
    sqlite_settings = Settings(
        telegram_bot_token="test_token",
        telegram_bot_username="test_bot",
        approved_directory=str(test_dir),
        database_url="sqlite:///data/bot.db",
    )
    assert sqlite_settings.database_path == Path("data/bot.db").resolve()


def test_feature_flags():
    """Test feature flag system."""
    # Create test MCP config file with valid structure before creating settings
    mcp_config = (
        '{"mcpServers": {"test-server": {"command": "echo", "args": ["hello"]}}}'
    )
    Path("/tmp/test_mcp.json").write_text(mcp_config)

    settings = create_test_config(
        enable_mcp=True,
        mcp_config_path="/tmp/test_mcp.json",
        enable_git_integration=True,
        enable_file_uploads=False,
        enable_token_auth=True,
        auth_token_secret="secret",
    )

    features = FeatureFlags(settings)

    assert features.mcp_enabled is True
    assert features.git_enabled is True
    assert features.file_uploads_enabled is False
    assert features.token_auth_enabled is True

    enabled_features = features.get_enabled_features()
    assert "mcp" in enabled_features
    assert "git" in enabled_features
    assert "file_uploads" not in enabled_features
    assert "token_auth" in enabled_features

    # Test generic feature check
    assert features.is_feature_enabled("git") is True
    assert features.is_feature_enabled("nonexistent") is False

    # Cleanup test file
    Path("/tmp/test_mcp.json").unlink(missing_ok=True)


def test_environment_loading():
    """Test environment-specific configuration loading."""
    # Test development environment
    with tempfile.TemporaryDirectory() as tmp_dir:
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_BOT_USERNAME"] = "test_bot"
        os.environ["APPROVED_DIRECTORY"] = tmp_dir

        try:
            config = load_config(env="development")
            assert config.debug is True
            assert config.development_mode is True
            assert config.log_level == "DEBUG"

            config = load_config(env="production")
            assert config.debug is False
            assert config.development_mode is False
            assert config.log_level == "INFO"

        finally:
            # Clean up environment
            for key in [
                "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_BOT_USERNAME",
                "APPROVED_DIRECTORY",
            ]:
                os.environ.pop(key, None)


def test_create_test_config():
    """Test test configuration creation."""
    config = create_test_config()

    assert config.telegram_token_str == "test_token_123"
    assert config.telegram_bot_username == "test_bot"
    assert str(config.approved_directory).endswith("test_projects")
    assert config.debug is True
    assert config.database_url == "sqlite:///:memory:"

    # Test with overrides
    config = create_test_config(
        log_level="ERROR",
        claude_max_turns=5,
    )

    assert config.log_level == "ERROR"
    assert config.claude_max_turns == 5


def test_configuration_error_handling():
    """Test configuration error handling."""
    # Test with invalid directory permissions (simulate by using a file)
    with tempfile.NamedTemporaryFile() as tmp_file:
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_BOT_USERNAME"] = "test_bot"
        os.environ["APPROVED_DIRECTORY"] = tmp_file.name  # File instead of directory

        try:
            with pytest.raises(ConfigurationError):
                load_config()
        finally:
            for key in [
                "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_BOT_USERNAME",
                "APPROVED_DIRECTORY",
            ]:
                os.environ.pop(key, None)
