"""Pytest configuration and fixtures."""

import os

import pytest

from src.config.settings import Settings

# Strip every env var Pydantic Settings would read, before any test imports
# Settings(). Otherwise host-machine .env values silently override explicit
# kwargs and tests pass on clean CI but fail locally.
for _field in Settings.model_fields:
    os.environ.pop(_field.upper(), None)


@pytest.fixture
def sample_user_id():
    """Sample Telegram user ID for testing."""
    return 123456789


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "telegram_bot_token": "test_token",
        "telegram_bot_username": "test_bot",
        "approved_directory": "/tmp/test_projects",
        "allowed_users": [123456789],
    }
