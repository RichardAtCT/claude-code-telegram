"""Pytest configuration and fixtures."""

import os

import pytest

# Strip env vars that Settings reads, before any test imports the module.
# Without this, host-machine .env values leak into Settings() and silently
# override the explicit kwargs each test passes — making tests fail locally
# but pass on a clean CI runner.
_SETTINGS_ENV_PREFIXES = ("CLAUDE_", "TELEGRAM_", "ANTHROPIC_", "WEBHOOK_", "GITHUB_")
_SETTINGS_ENV_VARS = {
    "DISABLE_SECURITY_PATTERNS",
    "DISABLE_TOOL_VALIDATION",
    "AGENTIC_MODE",
    "ENABLE_API_SERVER",
    "API_SERVER_HOST",
    "API_SERVER_PORT",
    "ENABLE_SCHEDULER",
    "ENABLE_MCP",
    "ENABLE_VOICE_MESSAGES",
    "VOICE_PROVIDER",
    "MISTRAL_API_KEY",
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "ALLOWED_USERS",
    "NOTIFICATION_CHAT_IDS",
    "REPLY_QUOTE",
    "VERBOSE_LEVEL",
    "ENABLE_STREAM_DRAFTS",
    "DEBUG",
    "DEVELOPMENT_MODE",
    "ENABLE_PROJECT_THREADS",
    "PROJECT_THREADS_MODE",
    "PROJECT_THREADS_CHAT_ID",
    "PROJECTS_CONFIG_PATH",
}
for _key in list(os.environ):
    if _key in _SETTINGS_ENV_VARS or any(
        _key.startswith(p) for p in _SETTINGS_ENV_PREFIXES
    ):
        del os.environ[_key]


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
