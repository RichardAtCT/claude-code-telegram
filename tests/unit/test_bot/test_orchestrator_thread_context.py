"""Focused tests for orchestrator project-thread context isolation."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.orchestrator import MessageOrchestrator
from src.config import create_test_config


@pytest.fixture
def group_thread_settings(tmp_path: Path):
    project_root = tmp_path / "project_a"
    project_root.mkdir()
    (project_root / "topic101").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: project_a\n"
        "    name: Project A\n"
        "    path: project_a\n",
        encoding="utf-8",
    )

    return create_test_config(
        approved_directory=str(tmp_path),
        agentic_mode=True,
        enable_project_threads=True,
        project_threads_mode="group",
        project_threads_chat_id=-1001234567890,
        projects_config_path=str(config_file),
    )


@pytest.fixture
def disabled_thread_settings(tmp_path: Path):
    return create_test_config(
        approved_directory=str(tmp_path),
        agentic_mode=True,
        enable_project_threads=False,
    )


@pytest.fixture
def deps():
    return {
        "claude_integration": MagicMock(),
        "storage": MagicMock(),
        "security_validator": MagicMock(),
        "rate_limiter": MagicMock(),
        "audit_logger": MagicMock(),
    }


@pytest.fixture
def project(group_thread_settings):
    return SimpleNamespace(
        slug="project_a",
        name="Project A",
        absolute_path=group_thread_settings.approved_directory / "project_a",
    )


def _manager_for(project):
    manager = MagicMock()
    manager.resolve_project = AsyncMock(return_value=project)
    manager.guidance_message.return_value = "Use project thread"
    return manager


def _context(initial_user_data=None):
    context = MagicMock()
    context.bot_data = {}
    context.user_data = initial_user_data or {}
    return context


def _forum_update(thread_id: int | None):
    message = MagicMock()
    message.message_thread_id = thread_id
    message.direct_messages_topic = None
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_chat.id = -1001234567890
    update.effective_chat.is_forum = True
    update.effective_message = message
    update.message = message
    update.callback_query = None
    return update


def _private_update_without_thread():
    message = MagicMock()
    message.message_thread_id = None
    message.direct_messages_topic = None
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_chat.id = 12345
    update.effective_chat.is_forum = False
    update.effective_chat.type = "private"
    update.effective_message = message
    update.message = message
    update.callback_query = None
    return update


def _direct_message_topic_update(topic_id: int):
    message = MagicMock()
    message.message_thread_id = None
    message.direct_messages_topic = SimpleNamespace(topic_id=topic_id)
    message.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_chat.id = 12345
    update.effective_chat.is_forum = False
    update.effective_chat.type = "private"
    update.effective_message = message
    update.message = message
    update.callback_query = None
    return update


async def test_topics_keep_current_directory_and_session_isolated(
    group_thread_settings, deps, project
):
    """Topic 202 in the same chat must not inherit topic 101 state."""
    orchestrator = MessageOrchestrator(group_thread_settings, deps)
    manager = _manager_for(project)
    deps["project_threads_manager"] = manager
    context = _context()
    topic_101_dir = project.absolute_path / "topic101"

    async def topic_101_handler(update, context):
        assert context.user_data["current_directory"] == project.absolute_path
        assert context.user_data["claude_session_id"] is None
        context.user_data["current_directory"] = topic_101_dir
        context.user_data["claude_session_id"] = "topic-101-session"

    await orchestrator._inject_deps(topic_101_handler)(
        _forum_update(101),
        context,
    )

    async def topic_202_handler(update, context):
        assert context.user_data["current_directory"] == project.absolute_path
        assert context.user_data["claude_session_id"] is None
        context.user_data["claude_session_id"] = "topic-202-session"

    await orchestrator._inject_deps(topic_202_handler)(
        _forum_update(202),
        context,
    )

    thread_state = context.user_data["thread_state"]
    assert thread_state["-1001234567890:101"]["current_directory"] == str(topic_101_dir)
    assert thread_state["-1001234567890:101"]["claude_session_id"] == (
        "topic-101-session"
    )
    assert thread_state["-1001234567890:202"]["current_directory"] == str(
        project.absolute_path
    )
    assert thread_state["-1001234567890:202"]["claude_session_id"] == (
        "topic-202-session"
    )


async def test_general_forum_topic_without_message_thread_id_uses_thread_one(
    group_thread_settings, deps, project
):
    """Telegram omits message_thread_id for General; wrapper must route it as 1."""
    orchestrator = MessageOrchestrator(group_thread_settings, deps)
    manager = _manager_for(project)
    deps["project_threads_manager"] = manager
    context = _context()

    async def handler(update, context):
        assert context.user_data["_thread_context"]["message_thread_id"] == 1
        context.user_data["claude_session_id"] = "general-session"

    await orchestrator._inject_deps(handler)(_forum_update(None), context)

    manager.resolve_project.assert_awaited_once_with(-1001234567890, 1)
    assert (
        context.user_data["thread_state"]["-1001234567890:1"]["claude_session_id"]
        == "general-session"
    )


async def test_disabled_project_threads_still_isolate_forum_topic_state(
    disabled_thread_settings, deps
):
    """ENABLE_PROJECT_THREADS=false scopes sessions by forum topic without manager."""
    orchestrator = MessageOrchestrator(disabled_thread_settings, deps)
    manager = MagicMock()
    manager.resolve_project = AsyncMock()
    deps["project_threads_manager"] = manager
    context = _context()
    topic_101_dir = disabled_thread_settings.approved_directory / "topic101"
    topic_101_dir.mkdir()

    async def topic_101_handler(update, context):
        assert context.user_data["current_directory"] == (
            disabled_thread_settings.approved_directory
        )
        assert context.user_data["claude_session_id"] is None
        context.user_data["current_directory"] = topic_101_dir
        context.user_data["claude_session_id"] = "topic-101-session"

    await orchestrator._inject_deps(topic_101_handler)(_forum_update(101), context)

    async def topic_202_handler(update, context):
        assert context.user_data["current_directory"] == (
            disabled_thread_settings.approved_directory
        )
        assert context.user_data["claude_session_id"] is None
        context.user_data["claude_session_id"] = "topic-202-session"

    await orchestrator._inject_deps(topic_202_handler)(_forum_update(202), context)

    thread_state = context.user_data["thread_state"]
    manager.resolve_project.assert_not_called()
    assert thread_state["-1001234567890:101"]["current_directory"] == str(topic_101_dir)
    assert thread_state["-1001234567890:101"]["claude_session_id"] == (
        "topic-101-session"
    )
    assert thread_state["-1001234567890:202"]["current_directory"] == str(
        disabled_thread_settings.approved_directory
    )
    assert thread_state["-1001234567890:202"]["claude_session_id"] == (
        "topic-202-session"
    )


async def test_disabled_project_threads_new_command_is_topic_local(
    disabled_thread_settings, deps
):
    """/new with generic topic scoping must not leak force_new_session."""
    orchestrator = MessageOrchestrator(disabled_thread_settings, deps)
    context = _context(
        {
            "thread_state": {
                "-1001234567890:101": {
                    "current_directory": str(
                        disabled_thread_settings.approved_directory
                    ),
                    "claude_session_id": "topic-101-old",
                },
                "-1001234567890:202": {
                    "current_directory": str(
                        disabled_thread_settings.approved_directory
                    ),
                    "claude_session_id": "topic-202-old",
                },
            }
        }
    )

    await orchestrator._inject_deps(orchestrator.agentic_new)(
        _forum_update(101),
        context,
    )

    assert (
        context.user_data["thread_state"]["-1001234567890:101"]["claude_session_id"]
        is None
    )
    assert (
        context.user_data["thread_state"]["-1001234567890:101"]["force_new_session"]
        is True
    )
    assert (
        context.user_data["thread_state"]["-1001234567890:101"]["session_started"]
        is True
    )

    async def topic_202_handler(update, context):
        assert context.user_data["claude_session_id"] == "topic-202-old"
        assert context.user_data.get("force_new_session") is not True
        assert context.user_data.get("session_started") is not True

    await orchestrator._inject_deps(topic_202_handler)(_forum_update(202), context)

    assert (
        "force_new_session"
        not in context.user_data["thread_state"]["-1001234567890:202"]
    )
    assert (
        "session_started" not in context.user_data["thread_state"]["-1001234567890:202"]
    )


async def test_private_chat_without_thread_keeps_unscoped_behavior(
    disabled_thread_settings, deps
):
    """Plain private chats do not create generic thread context."""
    orchestrator = MessageOrchestrator(disabled_thread_settings, deps)
    context = _context()

    async def handler(update, context):
        context.user_data["claude_session_id"] = "private-session"

    await orchestrator._inject_deps(handler)(_private_update_without_thread(), context)

    assert "_thread_context" not in context.user_data
    assert "thread_state" not in context.user_data


async def test_direct_message_topic_uses_generic_thread_state(
    disabled_thread_settings, deps
):
    """Direct-message topics with topic_id get the same generic isolation."""
    orchestrator = MessageOrchestrator(disabled_thread_settings, deps)
    context = _context()

    async def handler(update, context):
        assert context.user_data["_thread_context"]["state_key"] == "12345:909"
        context.user_data["claude_session_id"] = "dm-topic-session"

    await orchestrator._inject_deps(handler)(
        _direct_message_topic_update(909),
        context,
    )

    assert context.user_data["thread_state"]["12345:909"]["claude_session_id"] == (
        "dm-topic-session"
    )


async def test_agentic_new_session_flags_are_topic_local(
    group_thread_settings, deps, project
):
    """/new state is persisted only for the current forum topic."""
    orchestrator = MessageOrchestrator(group_thread_settings, deps)
    manager = _manager_for(project)
    deps["project_threads_manager"] = manager
    context = _context(
        {
            "thread_state": {
                "-1001234567890:101": {
                    "current_directory": str(project.absolute_path),
                    "claude_session_id": "topic-101-old",
                },
                "-1001234567890:202": {
                    "current_directory": str(project.absolute_path),
                    "claude_session_id": "topic-202-old",
                },
            }
        }
    )

    await orchestrator._inject_deps(orchestrator.agentic_new)(
        _forum_update(101),
        context,
    )

    assert (
        context.user_data["thread_state"]["-1001234567890:101"]["claude_session_id"]
        is None
    )
    assert (
        context.user_data["thread_state"]["-1001234567890:101"]["force_new_session"]
        is True
    )
    assert (
        context.user_data["thread_state"]["-1001234567890:101"]["session_started"]
        is True
    )

    async def topic_202_handler(update, context):
        assert context.user_data["claude_session_id"] == "topic-202-old"
        assert context.user_data.get("force_new_session") is not True
        assert context.user_data.get("session_started") is not True

    await orchestrator._inject_deps(topic_202_handler)(
        _forum_update(202),
        context,
    )

    assert (
        "force_new_session"
        not in context.user_data["thread_state"]["-1001234567890:202"]
    )
    assert (
        "session_started" not in context.user_data["thread_state"]["-1001234567890:202"]
    )
