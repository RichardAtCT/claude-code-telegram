"""Tests for concurrent scheduled event handling."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.bus import EventBus
from src.events.handlers import AgentHandler
from src.events.types import ScheduledEvent, WebhookEvent


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mock_claude() -> AsyncMock:
    mock = AsyncMock()
    mock.run_command = AsyncMock()
    return mock


@pytest.fixture
def agent_handler(event_bus: EventBus, mock_claude: AsyncMock) -> AgentHandler:
    return AgentHandler(
        event_bus=event_bus,
        claude_integration=mock_claude,
        default_working_directory=Path("/tmp/test"),
        default_user_id=42,
    )


class TestConcurrentScheduledHandling:
    """Tests for background dispatch of scheduled jobs."""

    async def test_handle_scheduled_returns_immediately(
        self, agent_handler: AgentHandler, mock_claude: AsyncMock
    ) -> None:
        """Scheduled jobs should dispatch to the background and return fast."""

        async def slow_run_command(**_: object) -> MagicMock:
            await asyncio.sleep(10)
            response = MagicMock()
            response.content = "done"
            return response

        mock_claude.run_command.side_effect = slow_run_command
        event = ScheduledEvent(
            job_name="standup",
            prompt="Generate daily standup",
            target_chat_ids=[100],
        )

        await asyncio.wait_for(agent_handler.handle_scheduled(event), timeout=1.0)

        for task in list(getattr(agent_handler, "_background_tasks", set())):
            task.cancel()
        if getattr(agent_handler, "_background_tasks", None):
            await asyncio.gather(
                *agent_handler._background_tasks, return_exceptions=True
            )

    def test_scheduled_semaphore_limits_concurrency(
        self, agent_handler: AgentHandler
    ) -> None:
        """Scheduled jobs are capped to two concurrent Claude executions."""
        assert agent_handler._scheduled_semaphore._value == 2

    async def test_scheduled_task_errors_are_logged_not_raised(
        self, agent_handler: AgentHandler, mock_claude: AsyncMock
    ) -> None:
        """Background scheduled task failures should be logged, not propagated."""

        async def boom(**_: object) -> MagicMock:
            raise RuntimeError("SDK error")

        mock_claude.run_command.side_effect = boom
        event = ScheduledEvent(
            job_name="standup",
            prompt="Generate daily standup",
            target_chat_ids=[100],
        )

        with patch("src.events.handlers.logger.exception") as mock_log:
            await agent_handler.handle_scheduled(event)
            tasks = list(agent_handler._background_tasks)
            assert tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)

        mock_log.assert_called()

    async def test_webhook_handler_still_blocks(
        self, agent_handler: AgentHandler, mock_claude: AsyncMock
    ) -> None:
        """Webhook handling should still await Claude directly."""
        release = asyncio.Event()
        started = asyncio.Event()

        async def blocked_run_command(**_: object) -> MagicMock:
            started.set()
            await release.wait()
            response = MagicMock()
            response.content = "done"
            return response

        mock_claude.run_command.side_effect = blocked_run_command
        event = WebhookEvent(
            provider="github",
            event_type_name="push",
            payload={"ref": "refs/heads/main"},
            delivery_id="del-1",
        )

        task = asyncio.create_task(agent_handler.handle_webhook(event))
        await started.wait()
        await asyncio.sleep(0)

        assert not task.done()

        release.set()
        await asyncio.wait_for(task, timeout=1.0)
        mock_claude.run_command.assert_awaited_once()
