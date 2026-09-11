"""Tests for application startup in src.main."""

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.config import create_test_config
from src.exceptions import ConfigurationError
from src.main import create_application


def _config_without_auth_providers(tmp_path: Path):
    """Config that reaches storage init and then fails auth validation."""
    return create_test_config(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        approved_directory=str(tmp_path),
        allowed_users=[],
        enable_token_auth=False,
        development_mode=False,
    )


async def test_create_application_closes_storage_on_configuration_error(tmp_path):
    """Storage must be closed when component creation fails."""
    config = _config_without_auth_providers(tmp_path)
    storage = AsyncMock()

    with patch("src.main.Storage", return_value=storage):
        with pytest.raises(ConfigurationError):
            await create_application(config)

    storage.initialize.assert_awaited_once()
    storage.close.assert_awaited_once()


async def test_create_application_leaves_no_live_database_threads(tmp_path):
    """Regression: a startup failure must not leave the pool's threads running.

    aiosqlite connections are non-daemon threads, so any left alive block
    interpreter shutdown. sys.exit() then hangs in wait_for_thread_shutdown()
    and the process never exits, which reads as "healthy" to a supervisor.
    """
    config = _config_without_auth_providers(tmp_path)
    before = {thread.ident for thread in threading.enumerate()}

    with pytest.raises(ConfigurationError):
        await create_application(config)

    # close() signals the worker threads rather than joining them, so give
    # them a moment to actually finish.
    leaked = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        leaked = [
            thread
            for thread in threading.enumerate()
            if thread.ident not in before and thread.is_alive() and not thread.daemon
        ]
        if not leaked:
            break
        await asyncio.sleep(0.05)

    assert not leaked, f"non-daemon threads still alive after failure: {leaked}"
