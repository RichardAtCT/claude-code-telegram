"""Tests for interactive tool-approval (Allow/Deny) feature.

Covers:
- _make_tool_approval_callback sends a prompt and resolves once answered
- Timeout auto-denies (fail closed) and cleans up pending state
- _handle_tool_approval_callback routing (owner-only, double-answer, unknown id)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.orchestrator import MessageOrchestrator, PendingToolApproval
from src.config.settings import Settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path):
    return Settings(
        telegram_bot_token="test:token",
        telegram_bot_username="testbot",
        approved_directory=tmp_path,
        agentic_mode=True,
        interactive_tool_approval=True,
        interactive_tool_approval_tools=["Bash"],
    )


@pytest.fixture
def orchestrator(settings):
    deps: dict = {}
    return MessageOrchestrator(settings, deps)


def _make_bot():
    bot = AsyncMock()
    sent_message = AsyncMock()
    bot.send_message = AsyncMock(return_value=sent_message)
    return bot


# ---------------------------------------------------------------------------
# _make_tool_approval_callback
# ---------------------------------------------------------------------------


class TestMakeToolApprovalCallback:
    async def test_sends_prompt_and_grants_on_allow(self, orchestrator):
        bot = _make_bot()
        request_approval = orchestrator._make_tool_approval_callback(
            user_id=100, chat_id=555, bot=bot, message_thread_id=None
        )

        task = asyncio.ensure_future(request_approval("Bash", {"command": "echo hi"}))
        await asyncio.sleep(0)  # let it register + send the prompt

        bot.send_message.assert_awaited_once()
        assert len(orchestrator._pending_tool_approvals) == 1
        request_id = next(iter(orchestrator._pending_tool_approvals))
        pending = orchestrator._pending_tool_approvals[request_id]
        assert pending.user_id == 100

        pending.future.set_result(True)
        result = await task

        assert result is True
        assert request_id not in orchestrator._pending_tool_approvals

    async def test_denies_on_deny(self, orchestrator):
        bot = _make_bot()
        request_approval = orchestrator._make_tool_approval_callback(
            user_id=100, chat_id=555, bot=bot, message_thread_id=None
        )

        task = asyncio.ensure_future(request_approval("Bash", {"command": "echo hi"}))
        await asyncio.sleep(0)

        request_id = next(iter(orchestrator._pending_tool_approvals))
        orchestrator._pending_tool_approvals[request_id].future.set_result(False)

        assert await task is False

    async def test_timeout_denies_and_cleans_up(self, orchestrator):
        """With no response, wait_for(timeout=0) times out immediately -> deny (default)."""
        orchestrator.settings.interactive_tool_approval_timeout_seconds = 0
        bot = _make_bot()
        request_approval = orchestrator._make_tool_approval_callback(
            user_id=100, chat_id=555, bot=bot, message_thread_id=None
        )

        result = await request_approval("Bash", {"command": "echo hi"})

        assert result is False
        assert orchestrator._pending_tool_approvals == {}
        bot.send_message.return_value.edit_text.assert_awaited_once()
        edit_text_args = bot.send_message.return_value.edit_text.await_args
        assert "denied" in edit_text_args.args[0].lower()

    async def test_timeout_allows_when_configured(self, orchestrator):
        """timeout_action='allow' makes an unanswered request resolve to True."""
        orchestrator.settings.interactive_tool_approval_timeout_seconds = 0
        orchestrator.settings.interactive_tool_approval_timeout_action = "allow"
        bot = _make_bot()
        request_approval = orchestrator._make_tool_approval_callback(
            user_id=100, chat_id=555, bot=bot, message_thread_id=None
        )

        result = await request_approval("Bash", {"command": "echo hi"})

        assert result is True
        assert orchestrator._pending_tool_approvals == {}
        edit_text_args = bot.send_message.return_value.edit_text.await_args
        assert "auto-allowed" in edit_text_args.args[0].lower()


# ---------------------------------------------------------------------------
# _handle_tool_approval_callback
# ---------------------------------------------------------------------------


class TestHandleToolApprovalCallback:
    def _query(self, data, user_id):
        query = AsyncMock()
        query.data = data
        query.from_user = MagicMock()
        query.from_user.id = user_id
        query.message = AsyncMock()
        query.message.text_html = "⚠️ Claude wants to run <b>Bash</b>"
        return query

    async def test_owner_can_allow(self, orchestrator):
        future: "asyncio.Future[bool]" = asyncio.get_event_loop().create_future()
        orchestrator._pending_tool_approvals["abc123"] = PendingToolApproval(
            user_id=100, future=future
        )

        query = self._query("tapv:allow:abc123", 100)
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.bot_data = {}

        await orchestrator._handle_tool_approval_callback(update, context)

        assert future.result() is True
        query.answer.assert_awaited_once_with("Allowed", show_alert=False)

    async def test_owner_can_deny(self, orchestrator):
        future: "asyncio.Future[bool]" = asyncio.get_event_loop().create_future()
        orchestrator._pending_tool_approvals["abc123"] = PendingToolApproval(
            user_id=100, future=future
        )

        query = self._query("tapv:deny:abc123", 100)
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.bot_data = {}

        await orchestrator._handle_tool_approval_callback(update, context)

        assert future.result() is False
        query.answer.assert_awaited_once_with("Denied", show_alert=False)

    async def test_non_owner_blocked(self, orchestrator):
        future: "asyncio.Future[bool]" = asyncio.get_event_loop().create_future()
        orchestrator._pending_tool_approvals["abc123"] = PendingToolApproval(
            user_id=100, future=future
        )

        query = self._query("tapv:allow:abc123", 999)
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.bot_data = {}

        await orchestrator._handle_tool_approval_callback(update, context)

        assert not future.done()
        query.answer.assert_awaited_once_with(
            "Only the requesting user can respond.", show_alert=True
        )

    async def test_unknown_request_id(self, orchestrator):
        query = self._query("tapv:allow:does-not-exist", 100)
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.bot_data = {}

        await orchestrator._handle_tool_approval_callback(update, context)

        query.answer.assert_awaited_once_with("Already handled.", show_alert=False)

    async def test_double_answer_is_noop(self, orchestrator):
        future: "asyncio.Future[bool]" = asyncio.get_event_loop().create_future()
        future.set_result(True)
        orchestrator._pending_tool_approvals["abc123"] = PendingToolApproval(
            user_id=100, future=future
        )

        query = self._query("tapv:deny:abc123", 100)
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()
        context.bot_data = {}

        await orchestrator._handle_tool_approval_callback(update, context)

        # First result stands -- not overwritten by the second (late) click
        assert future.result() is True
        query.answer.assert_awaited_once_with("Already handled.", show_alert=False)
