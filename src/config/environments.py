"""Environment-specific configuration overrides."""

from typing import Any, Dict


class DevelopmentConfig:
    """Development environment overrides."""

    debug: bool = True
    development_mode: bool = True
    log_level: str = "DEBUG"
    rate_limit_requests: int = 100  # More lenient for testing
    claude_timeout_seconds: int = 900  # Longer timeout for debugging
    enable_telemetry: bool = False

    @classmethod
    def as_dict(cls) -> Dict[str, Any]:
        """Return config as dictionary."""
        return {
            key: value
            for key, value in cls.__dict__.items()
            if not key.startswith("_")
            and not callable(value)
            and not isinstance(value, classmethod)
        }


class TestingConfig:
    """Testing environment configuration."""

    debug: bool = True
    development_mode: bool = True
    database_url: str = "sqlite:///:memory:"
    approved_directory: str = "/tmp/test_projects"
    enable_telemetry: bool = False
    claude_timeout_seconds: int = 30  # Faster timeout for tests
    rate_limit_requests: int = 1000  # No rate limiting in tests
    session_timeout_hours: int = 1  # Short session timeout for testing

    @classmethod
    def as_dict(cls) -> Dict[str, Any]:
        """Return config as dictionary."""
        return {
            key: value
            for key, value in cls.__dict__.items()
            if not key.startswith("_")
            and not callable(value)
            and not isinstance(value, classmethod)
        }


class ProductionConfig:
    """Production environment configuration."""

    debug: bool = False
    development_mode: bool = False
    log_level: str = "INFO"
    enable_telemetry: bool = True
    # Use stricter defaults for production
    claude_max_cost_per_user: float = 5.0  # Lower cost limit
    rate_limit_requests: int = 5  # Stricter rate limiting
    session_timeout_hours: int = 12  # Shorter session timeout

    @classmethod
    def as_dict(cls) -> Dict[str, Any]:
        """Return config as dictionary."""
        return {
            key: value
            for key, value in cls.__dict__.items()
            if not key.startswith("_")
            and not callable(value)
            and not isinstance(value, classmethod)
        }
