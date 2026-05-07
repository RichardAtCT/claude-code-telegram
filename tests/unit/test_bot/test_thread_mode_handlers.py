"""Tests for thread mode handler constraints."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.handlers import callback, command, message
from src.config import create_test_config


@pytest.fixture
def thread_settings(tmp_path: Path):
    approved = tmp_path / "projects"
    approved.mkdir()
    project_root = approved / "project_a"
    project_root.mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: project_a\n"
        "    name: Project A\n"
        "    path: project_a\n",
        encoding="utf-8",
    )

    settings = create_test_config(
        approved_directory=str(approved),
        enable_project_threads=True,
        project_threads_mode="private",
        projects_config_path=str(config_file),
    )
    return settings, project_root


async def test_command_cd_stays_within_project_root(thread_settings):
    """/cd .. at project root remains pinned to project root in thread mode."""
    settings, project_root = thread_settings

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = [".."]
    context.bot_data = {
        "settings": settings,
        "security_validator": None,
        "audit_logger": None,
        "claude_integration": AsyncMock(
            _find_resumable_session=AsyncMock(return_value=None)
        ),
    }
    context.user_data = {
        "current_directory": project_root,
        "_thread_context": {"project_root": str(project_root)},
    }

    await command.change_directory(update, context)

    assert context.user_data["current_directory"] == project_root
    assert context.user_data["claude_session_id"] is None
    context.bot_data["claude_integration"]._find_resumable_session.assert_not_called()


async def test_classic_text_forces_new_session_for_new_thread_context(thread_settings):
    """Classic text handler must not auto-resume a global session in a new topic."""
    settings, project_root = thread_settings

    progress_msg = AsyncMock()
    claude_integration = AsyncMock()
    claude_integration.run_command = AsyncMock(
        return_value=SimpleNamespace(session_id="classic-topic-session", content="ok")
    )

    update = MagicMock()
    update.effective_user.id = 1
    update.message.text = "remember banana"
    update.message.message_id = 10
    update.message.chat.send_action = AsyncMock()
    update.message.reply_text = AsyncMock(return_value=progress_msg)

    context = MagicMock()
    context.bot_data = {
        "settings": settings,
        "rate_limiter": None,
        "audit_logger": None,
        "storage": None,
        "claude_integration": claude_integration,
    }
    context.user_data = {
        "current_directory": project_root,
        "_thread_context": {"project_root": str(project_root)},
        "claude_session_id": None,
    }

    await message.handle_text_message(update, context)

    assert claude_integration.run_command.call_args.kwargs["force_new"] is True
    assert context.user_data["claude_session_id"] == "classic-topic-session"


async def test_classic_thread_force_new_helper_covers_non_text_entrypoints(
    thread_settings,
):
    """Document/photo/voice handlers share the same thread auto-resume guard."""
    _, project_root = thread_settings
    context = MagicMock()
    context.user_data = {
        "current_directory": project_root,
        "_thread_context": {"project_root": str(project_root)},
        "claude_session_id": None,
    }

    assert message._should_force_new_claude_session(context, None) is True


async def test_callback_cd_stays_within_project_root(thread_settings):
    """cd callback keeps navigation constrained to thread project root."""
    settings, project_root = thread_settings

    query = MagicMock()
    query.from_user.id = 1
    query.edit_message_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {
        "settings": settings,
        "security_validator": None,
        "audit_logger": None,
        "claude_integration": AsyncMock(
            _find_resumable_session=AsyncMock(return_value=None)
        ),
    }
    context.user_data = {
        "current_directory": project_root,
        "_thread_context": {"project_root": str(project_root)},
    }

    await callback.handle_cd_callback(query, "..", context)

    assert context.user_data["current_directory"] == project_root
    assert context.user_data["claude_session_id"] is None
    context.bot_data["claude_integration"]._find_resumable_session.assert_not_called()
    query.edit_message_text.assert_called_once()


async def test_continue_command_does_not_global_resume_in_thread_context(
    thread_settings,
):
    """Classic /continue should not continue a global session from a new topic."""
    settings, project_root = thread_settings
    claude_integration = AsyncMock()
    claude_integration.continue_session = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock(return_value=AsyncMock())

    context = MagicMock()
    context.args = []
    context.bot_data = {
        "settings": settings,
        "audit_logger": None,
        "claude_integration": claude_integration,
    }
    context.user_data = {
        "current_directory": project_root,
        "_thread_context": {"project_root": str(project_root)},
        "claude_session_id": None,
    }

    await command.continue_session(update, context)

    claude_integration.continue_session.assert_not_called()


async def test_continue_callback_does_not_global_resume_in_thread_context(
    thread_settings,
):
    """Classic continue callback should stay topic-local."""
    settings, project_root = thread_settings
    claude_integration = AsyncMock()
    claude_integration.continue_session = AsyncMock()

    query = MagicMock()
    query.from_user.id = 1
    query.edit_message_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"settings": settings, "claude_integration": claude_integration}
    context.user_data = {
        "current_directory": project_root,
        "_thread_context": {"project_root": str(project_root)},
        "claude_session_id": None,
    }

    await callback._handle_continue_action(query, context)

    claude_integration.continue_session.assert_not_called()


async def test_quick_action_forces_new_session_for_new_thread_context(thread_settings):
    """Quick actions must not auto-resume a global session in a new topic."""
    settings, project_root = thread_settings
    claude_integration = AsyncMock()
    claude_integration.run_command = AsyncMock(
        return_value=SimpleNamespace(session_id="quick-topic-session", content="ok")
    )
    quick_actions = SimpleNamespace(
        actions={"qa": SimpleNamespace(icon="⚡", name="QA", prompt="run qa")}
    )

    query = MagicMock()
    query.from_user.id = 1
    query.edit_message_text = AsyncMock()
    query.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {
        "settings": settings,
        "quick_actions": quick_actions,
        "claude_integration": claude_integration,
    }
    context.user_data = {
        "current_directory": project_root,
        "_thread_context": {"project_root": str(project_root)},
        "claude_session_id": None,
    }

    await callback.handle_quick_action_callback(query, "qa", context)

    assert claude_integration.run_command.call_args.kwargs["force_new"] is True
    assert context.user_data["claude_session_id"] == "quick-topic-session"


async def test_start_private_mode_triggers_auto_sync(thread_settings):
    """Private mode /start auto-syncs project topics for current private chat."""
    settings, _ = thread_settings

    manager = AsyncMock()
    manager.sync_topics = AsyncMock(
        return_value=MagicMock(
            created=1,
            reused=1,
            renamed=0,
            reopened=0,
            closed=0,
            failed=0,
            deactivated=0,
        )
    )

    update = MagicMock()
    update.effective_user.id = 1
    update.effective_user.first_name = "User"
    update.effective_chat.type = "private"
    update.effective_chat.id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot = AsyncMock()
    context.bot_data = {
        "settings": settings,
        "audit_logger": None,
        "project_threads_manager": manager,
    }
    context.user_data = {}

    await command.start_command(update, context)

    manager.sync_topics.assert_called_once()
    kwargs = manager.sync_topics.call_args.kwargs
    assert kwargs["chat_id"] == 42


async def test_sync_threads_private_mode_rejects_non_private_chat(thread_settings):
    """sync_threads in private mode must run in private chat."""
    settings, _ = thread_settings

    manager = AsyncMock()
    manager.sync_topics = AsyncMock()

    status_msg = AsyncMock()
    status_msg.edit_text = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 1
    update.effective_chat.type = "group"
    update.effective_chat.id = -1001
    update.message.reply_text = AsyncMock(return_value=status_msg)

    context = MagicMock()
    context.bot = AsyncMock()
    context.bot_data = {
        "settings": settings,
        "audit_logger": None,
        "project_threads_manager": manager,
    }
    context.user_data = {}

    await command.sync_threads(update, context)

    manager.sync_topics.assert_not_called()
    status_msg.edit_text.assert_called_once()


async def test_sync_threads_reloads_registry_from_yaml(thread_settings, monkeypatch):
    """sync_threads should reload YAML registry at runtime before syncing."""
    settings, _ = thread_settings

    manager = AsyncMock()
    manager.sync_topics = AsyncMock(
        return_value=MagicMock(
            created=0,
            reused=2,
            renamed=0,
            reopened=0,
            closed=0,
            deactivated=0,
            failed=0,
        )
    )

    new_registry = MagicMock()
    load_mock = MagicMock(return_value=new_registry)
    monkeypatch.setattr(command, "load_project_registry", load_mock)

    status_msg = AsyncMock()
    status_msg.edit_text = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 1
    update.effective_chat.type = "private"
    update.effective_chat.id = 42
    update.message.reply_text = AsyncMock(return_value=status_msg)

    context = MagicMock()
    context.bot = AsyncMock()
    context.bot_data = {
        "settings": settings,
        "audit_logger": None,
        "project_threads_manager": manager,
        "project_registry": MagicMock(),
    }
    context.user_data = {}

    await command.sync_threads(update, context)

    load_mock.assert_called_once_with(
        config_path=settings.projects_config_path,
        approved_directory=settings.approved_directory,
    )
    assert manager.registry is new_registry
    assert context.bot_data["project_registry"] is new_registry
    manager.sync_topics.assert_called_once()


async def test_sync_threads_group_mode_rejects_non_target_chat(tmp_path: Path):
    """sync_threads in group mode must be called from configured target chat."""
    approved = tmp_path / "projects"
    approved.mkdir()
    project_root = approved / "project_a"
    project_root.mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: project_a\n"
        "    name: Project A\n"
        "    path: project_a\n",
        encoding="utf-8",
    )

    settings = create_test_config(
        approved_directory=str(approved),
        enable_project_threads=True,
        project_threads_mode="group",
        project_threads_chat_id=-10012345,
        projects_config_path=str(config_file),
    )

    manager = AsyncMock()
    manager.sync_topics = AsyncMock()

    status_msg = AsyncMock()
    status_msg.edit_text = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 1
    update.effective_chat.id = -10099999
    update.message.reply_text = AsyncMock(return_value=status_msg)

    context = MagicMock()
    context.bot = AsyncMock()
    context.bot_data = {
        "settings": settings,
        "audit_logger": None,
        "project_threads_manager": manager,
    }
    context.user_data = {}

    await command.sync_threads(update, context)

    manager.sync_topics.assert_not_called()
    status_msg.edit_text.assert_called_once()
