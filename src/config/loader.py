"""Configuration loading with environment detection."""

import os
from pathlib import Path
from typing import Any, Optional

import structlog
from dotenv import load_dotenv

from src.exceptions import ConfigurationError, InvalidConfigError

from .environments import DevelopmentConfig, ProductionConfig, TestingConfig
from .settings import Settings

logger = structlog.get_logger()


def load_config(
    env: Optional[str] = None, config_file: Optional[Path] = None
) -> Settings:
    """Load configuration based on environment.

    Args:
        env: Environment name (development, testing, production)
        config_file: Optional path to configuration file

    Returns:
        Configured Settings instance

    Raises:
        ConfigurationError: If configuration is invalid
    """
    # Load .env file explicitly
    env_file = config_file or Path(".env")
    if env_file.exists():
        logger.info("Loading .env file", path=str(env_file))
        load_dotenv(env_file)
    else:
        logger.warning("No .env file found", path=str(env_file))

    # Determine environment
    env = env or os.getenv("ENVIRONMENT", "development")
    logger.info("Loading configuration", environment=env)

    try:
        # Debug: Log key environment variables before Settings creation
        logger.debug(
            "Environment variables check",
            telegram_bot_token_set=bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME"),
            approved_directory=os.getenv("APPROVED_DIRECTORY"),
            debug_mode=os.getenv("DEBUG"),
        )

        # Load base settings from environment variables
        # pydantic-settings will automatically read from environment variables
        settings = Settings()  # type: ignore[call-arg]

        # Apply environment-specific overrides
        settings = _apply_environment_overrides(settings, env)

        # Validate configuration
        _validate_config(settings)

        logger.info(
            "Configuration loaded successfully",
            environment=env,
            debug=settings.debug,
            approved_directory=str(settings.approved_directory),
            features_enabled=_get_enabled_features_summary(settings),
        )

        return settings

    except Exception as e:
        logger.error("Failed to load configuration", error=str(e), environment=env)
        raise ConfigurationError(f"Configuration loading failed: {e}") from e


def _apply_environment_overrides(settings: Settings, env: Optional[str]) -> Settings:
    """Apply environment-specific configuration overrides."""
    overrides = {}

    if env == "development":
        overrides = DevelopmentConfig.as_dict()
    elif env == "testing":
        overrides = TestingConfig.as_dict()
    elif env == "production":
        overrides = ProductionConfig.as_dict()
    else:
        logger.warning("Unknown environment, using default settings", environment=env)

    # Apply overrides
    for key, value in overrides.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
            logger.debug(
                "Applied environment override", key=key, value=value, environment=env
            )

    return settings


def _validate_config(settings: Settings) -> None:
    """Perform additional runtime validation."""
    # Check file system permissions
    try:
        if not os.access(settings.approved_directory, os.R_OK | os.X_OK):
            raise InvalidConfigError(
                f"Cannot access approved directory: {settings.approved_directory}"
            )
    except OSError as e:
        raise InvalidConfigError(f"Error accessing approved directory: {e}") from e

    # Validate feature dependencies
    if settings.enable_mcp and not settings.mcp_config_path:
        raise InvalidConfigError("MCP enabled but no config path provided")

    if settings.enable_token_auth and not settings.auth_token_secret:
        raise InvalidConfigError("Token auth enabled but no secret provided")

    if settings.enable_project_threads:
        if (
            settings.project_threads_mode == "group"
            and settings.project_threads_chat_id is None
        ):
            raise InvalidConfigError(
                "Project thread mode is 'group' but no project_threads_chat_id provided"
            )
        if not settings.projects_config_path:
            raise InvalidConfigError(
                "Project thread mode enabled but no projects_config_path provided"
            )
        if not settings.projects_config_path.exists():
            raise InvalidConfigError(
                f"Projects config not found: {settings.projects_config_path}"
            )

    # Validate database path for SQLite
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_path
        if db_path:
            # Ensure parent directory exists
            db_path.parent.mkdir(parents=True, exist_ok=True)

    # Validate rate limiting settings
    if settings.rate_limit_requests <= 0:
        raise InvalidConfigError("rate_limit_requests must be positive")

    if settings.rate_limit_window <= 0:
        raise InvalidConfigError("rate_limit_window must be positive")

    if settings.claude_timeout_seconds <= 0:
        raise InvalidConfigError("claude_timeout_seconds must be positive")

    # Validate cost limits
    if settings.claude_max_cost_per_user <= 0:
        raise InvalidConfigError("claude_max_cost_per_user must be positive")

    if settings.claude_max_cost_per_request <= 0:
        raise InvalidConfigError("claude_max_cost_per_request must be positive")


def _get_enabled_features_summary(settings: Settings) -> list[str]:
    """Get a summary of enabled features for logging."""
    features = []
    if settings.enable_mcp:
        features.append("mcp")
    if settings.enable_git_integration:
        features.append("git")
    if settings.enable_file_uploads:
        features.append("file_uploads")
    if settings.enable_quick_actions:
        features.append("quick_actions")
    if settings.enable_token_auth:
        features.append("token_auth")
    if settings.webhook_url:
        features.append("webhook")
    return features


def create_test_config(**overrides: Any) -> Settings:
    """Create configuration for testing with optional overrides.

    Args:
        **overrides: Configuration values to override

    Returns:
        Settings instance configured for testing
    """
    # Start with testing defaults
    test_values = TestingConfig.as_dict()

    # Add required fields for testing
    test_values.update(
        {
            "telegram_bot_token": "test_token_123",
            "telegram_bot_username": "test_bot",
            "approved_directory": "/tmp/test_projects",
        }
    )

    # Apply any overrides
    test_values.update(overrides)

    # Ensure test directory exists
    test_dir = Path(test_values["approved_directory"])
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create settings with test values
    settings = Settings(**test_values)

    return settings
