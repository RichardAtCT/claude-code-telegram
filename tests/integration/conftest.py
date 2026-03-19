"""Shared fixtures for integration tests."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.settings import Settings
from src.events.bus import EventBus
from src.storage.database import DatabaseManager


@pytest.fixture
async def in_memory_db():
    """Create a DatabaseManager backed by a temporary SQLite file.

    Uses a temp-file rather than ``:memory:`` so the connection pool
    (multiple connections) all see the same database.
    Runs migrations automatically before yielding.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "integration_test.db"
        manager = DatabaseManager(f"sqlite:///{db_path}")
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Return a Settings object with safe test values.

    ``approved_directory`` points to a real temp directory so the
    validator passes.
    """
    return Settings(
        telegram_bot_token="test_token_123456:ABC",
        telegram_bot_username="test_bot",
        approved_directory=str(tmp_path),
        allowed_users=[111, 222, 333],
        database_url="sqlite:///test.db",
        debug=True,
        development_mode=True,
        enable_api_server=True,
        github_webhook_secret="gh_test_secret",
        gitlab_webhook_secret="gl_test_secret",
        bitbucket_webhook_secret="bb_test_secret",
        webhook_api_secret="generic_test_secret",
        rate_limit_requests=10,
        rate_limit_window=60,
        rate_limit_burst=5,
        claude_max_cost_per_user=10.0,
    )


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock Telegram Bot instance."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.get_me = AsyncMock(return_value=MagicMock(username="test_bot"))
    return bot


@pytest.fixture
def event_bus() -> EventBus:
    """Return a fresh EventBus instance."""
    return EventBus()
