"""Tests for project-thread manager."""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import RetryAfter, TelegramError

import src.projects.thread_manager as thread_manager_module
from src.projects import (
    PrivateTopicsUnavailableError,
    ProjectThreadManager,
    load_project_registry,
)
from src.storage.database import DatabaseManager
from src.storage.repositories import ProjectThreadRepository


@pytest.fixture
async def db_manager():
    """Create test database manager."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        manager = DatabaseManager(f"sqlite:///{db_path}")
        await manager.initialize()
        yield manager
        await manager.close()


def _write_registry(tmp_path: Path, approved: Path, projects: str):
    for project in projects.split(","):
        (approved / project.strip()).mkdir(parents=True, exist_ok=True)

    lines = ["projects:"]
    for project in projects.split(","):
        project = project.strip()
        lines.extend(
            [
                f"  - slug: {project}",
                f"    name: {project.title()}",
                f"    path: {project}",
            ]
        )

    config_file = tmp_path / "projects.yaml"
    config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config_file


async def test_sync_topics_idempotent(tmp_path: Path, db_manager) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()

    config_file = _write_registry(tmp_path, approved, "app1")
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)

    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(
        return_value=SimpleNamespace(message_thread_id=101)
    )
    bot.send_message = AsyncMock()
    bot.reopen_forum_topic = AsyncMock()
    bot.close_forum_topic = AsyncMock()
    bot.edit_forum_topic = AsyncMock()

    first = await manager.sync_topics(bot, chat_id=-1001234567890)
    second = await manager.sync_topics(bot, chat_id=-1001234567890)

    assert first.created == 1
    assert first.reused == 0
    assert second.created == 0
    assert second.reused == 1


async def test_resolve_project_by_mapping(tmp_path: Path, db_manager) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()

    config_file = _write_registry(tmp_path, approved, "app1")
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    await repo.upsert_mapping(
        project_slug="app1",
        chat_id=-1001234567890,
        message_thread_id=555,
        topic_name="App1",
        is_active=True,
    )

    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)
    project = await manager.resolve_project(-1001234567890, 555)

    assert project is not None
    assert project.slug == "app1"


async def test_sync_deactivates_stale_projects(tmp_path: Path, db_manager) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()

    initial_file = _write_registry(tmp_path, approved, "app1,app2")
    initial_registry = load_project_registry(initial_file, approved)

    repo = ProjectThreadRepository(db_manager)
    manager = ProjectThreadManager(
        initial_registry,
        repo,
        sync_action_interval_seconds=0.0,
    )

    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(
        side_effect=[
            SimpleNamespace(message_thread_id=101),
            SimpleNamespace(message_thread_id=102),
        ]
    )
    bot.send_message = AsyncMock()
    bot.reopen_forum_topic = AsyncMock()
    bot.close_forum_topic = AsyncMock()
    bot.edit_forum_topic = AsyncMock()

    await manager.sync_topics(bot, chat_id=-1001234567890)

    reduced_file = tmp_path / "projects_reduced.yaml"
    reduced_file.write_text(
        "projects:\n" "  - slug: app1\n" "    name: App1\n" "    path: app1\n",
        encoding="utf-8",
    )
    reduced_registry = load_project_registry(reduced_file, approved)
    reduced_manager = ProjectThreadManager(
        reduced_registry,
        repo,
        sync_action_interval_seconds=0.0,
    )

    result = await reduced_manager.sync_topics(bot, chat_id=-1001234567890)
    mappings = await repo.list_by_chat(-1001234567890, active_only=False)

    app2 = [m for m in mappings if m.project_slug == "app2"]
    assert result.deactivated == 1
    assert result.closed == 1
    assert app2
    assert app2[0].is_active is False
    bot.close_forum_topic.assert_called_once_with(
        chat_id=-1001234567890,
        message_thread_id=102,
    )


async def test_sync_private_topics_unavailable_raises(
    tmp_path: Path, db_manager
) -> None:
    """Private topics unavailable should raise dedicated error."""
    approved = tmp_path / "projects"
    approved.mkdir()

    config_file = _write_registry(tmp_path, approved, "app1")
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)

    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(
        side_effect=TelegramError("Bad Request: topics are not enabled in the chat")
    )

    with pytest.raises(PrivateTopicsUnavailableError):
        await manager.sync_topics(bot, chat_id=123456)


async def test_sync_renames_existing_topic_and_updates_mapping(
    tmp_path: Path, db_manager
) -> None:
    """When project name changes, manager renames topic and stores new name."""
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app1").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n" "  - slug: app1\n" "    name: Pretty Name\n" "    path: app1\n",
        encoding="utf-8",
    )
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    await repo.upsert_mapping(
        project_slug="app1",
        chat_id=42,
        message_thread_id=1001,
        topic_name="Old Name",
        is_active=True,
    )

    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock()
    bot.reopen_forum_topic = AsyncMock()
    bot.edit_forum_topic = AsyncMock()

    result = await manager.sync_topics(bot, chat_id=42)
    mapping = await repo.get_by_chat_project(42, "app1")

    assert result.reused == 1
    assert result.renamed == 1
    assert result.failed == 0
    assert mapping is not None
    assert mapping.topic_name == "Pretty Name"


async def test_sync_rename_failure_keeps_old_mapping_for_retry(
    tmp_path: Path, db_manager
) -> None:
    """Failed rename should not overwrite stored topic name."""
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app1").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n" "  - slug: app1\n" "    name: Pretty Name\n" "    path: app1\n",
        encoding="utf-8",
    )
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    await repo.upsert_mapping(
        project_slug="app1",
        chat_id=42,
        message_thread_id=1001,
        topic_name="Old Name",
        is_active=True,
    )

    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock()
    bot.reopen_forum_topic = AsyncMock()
    bot.edit_forum_topic = AsyncMock(side_effect=TelegramError("rename failed"))

    result = await manager.sync_topics(bot, chat_id=42)
    mapping = await repo.get_by_chat_project(42, "app1")

    assert result.reused == 1
    assert result.renamed == 0
    assert result.failed == 1
    assert mapping is not None
    assert mapping.topic_name == "Old Name"


async def test_sync_reused_mapping_skips_rename_when_name_matches(
    tmp_path: Path, db_manager
) -> None:
    """When DB name already matches, sync should not call topic rename."""
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app1").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n" "  - slug: app1\n" "    name: Pretty Name\n" "    path: app1\n",
        encoding="utf-8",
    )
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    await repo.upsert_mapping(
        project_slug="app1",
        chat_id=42,
        message_thread_id=1001,
        topic_name="Pretty Name",
        is_active=True,
    )

    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)
    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock()
    bot.reopen_forum_topic = AsyncMock()
    bot.edit_forum_topic = AsyncMock()

    result = await manager.sync_topics(bot, chat_id=42)

    assert result.reused == 1
    bot.edit_forum_topic.assert_not_called()


async def test_sync_create_sends_bootstrap_message(tmp_path: Path, db_manager) -> None:
    """Creating a new topic posts an initial message in that topic."""
    approved = tmp_path / "projects"
    approved.mkdir()

    config_file = _write_registry(tmp_path, approved, "app1")
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)

    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(
        return_value=SimpleNamespace(message_thread_id=101)
    )
    bot.send_message = AsyncMock()
    bot.edit_forum_topic = AsyncMock()

    result = await manager.sync_topics(bot, chat_id=42)

    assert result.created == 1
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 42
    assert kwargs["message_thread_id"] == 101


async def test_sync_recreates_active_mapping_when_topic_unusable(
    tmp_path: Path, db_manager
) -> None:
    """Active mapping with unusable topic is recreated and remapped."""
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app1").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n" "  - slug: app1\n" "    name: App One\n" "    path: app1\n",
        encoding="utf-8",
    )
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    await repo.upsert_mapping(
        project_slug="app1",
        chat_id=42,
        message_thread_id=1001,
        topic_name="App One",
        is_active=True,
    )

    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)
    bot = AsyncMock()
    bot.reopen_forum_topic = AsyncMock(
        side_effect=TelegramError("Bad Request: topic deleted")
    )
    bot.create_forum_topic = AsyncMock(
        return_value=SimpleNamespace(message_thread_id=2002)
    )
    bot.send_message = AsyncMock()

    result = await manager.sync_topics(bot, chat_id=42)
    mapping = await repo.get_by_chat_project(42, "app1")

    assert result.created == 1
    assert result.reused == 0
    assert mapping is not None
    assert mapping.message_thread_id == 2002


async def test_sync_reopen_inactive_mapping(tmp_path: Path, db_manager) -> None:
    """Inactive mapping is reopened and reactivated when project returns."""
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app1").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n" "  - slug: app1\n" "    name: App One\n" "    path: app1\n",
        encoding="utf-8",
    )
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    await repo.upsert_mapping(
        project_slug="app1",
        chat_id=42,
        message_thread_id=1001,
        topic_name="App One",
        is_active=False,
    )

    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)
    bot = AsyncMock()
    bot.reopen_forum_topic = AsyncMock()
    bot.edit_forum_topic = AsyncMock()

    result = await manager.sync_topics(bot, chat_id=42)
    mapping = await repo.get_by_chat_project(42, "app1")

    assert result.reopened == 1
    assert result.reused == 1
    assert mapping is not None
    assert mapping.is_active is True


async def test_sync_reopen_unusable_inactive_mapping_recreates(
    tmp_path: Path, db_manager
) -> None:
    """Inactive mapping with dead topic is recreated."""
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app1").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n" "  - slug: app1\n" "    name: App One\n" "    path: app1\n",
        encoding="utf-8",
    )
    registry = load_project_registry(config_file, approved)

    repo = ProjectThreadRepository(db_manager)
    await repo.upsert_mapping(
        project_slug="app1",
        chat_id=42,
        message_thread_id=1001,
        topic_name="App One",
        is_active=False,
    )

    manager = ProjectThreadManager(registry, repo, sync_action_interval_seconds=0.0)
    bot = AsyncMock()
    bot.reopen_forum_topic = AsyncMock(
        side_effect=TelegramError("Bad Request: message thread not found")
    )
    bot.create_forum_topic = AsyncMock(
        return_value=SimpleNamespace(message_thread_id=3003)
    )
    bot.send_message = AsyncMock()

    result = await manager.sync_topics(bot, chat_id=42)
    mapping = await repo.get_by_chat_project(42, "app1")

    assert result.created == 1
    assert result.reopened == 0
    assert mapping is not None
    assert mapping.is_active is True
    assert mapping.message_thread_id == 3003


async def test_sync_topics_applies_pacing_between_api_calls(
    tmp_path: Path, db_manager, monkeypatch
) -> None:
    """Sync API calls should be spaced by configured interval."""
    approved = tmp_path / "projects"
    approved.mkdir()

    config_file = _write_registry(tmp_path, approved, "app1")
    registry = load_project_registry(config_file, approved)
    repo = ProjectThreadRepository(db_manager)
    manager = ProjectThreadManager(
        registry,
        repo,
        sync_action_interval_seconds=0.5,
    )

    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(
        return_value=SimpleNamespace(message_thread_id=123)
    )
    bot.send_message = AsyncMock()

    sleep_mock = AsyncMock()
    monkeypatch.setattr(thread_manager_module.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(thread_manager_module, "monotonic", lambda: 0.0)

    result = await manager.sync_topics(bot, chat_id=42)

    assert result.created == 1
    sleep_mock.assert_awaited_once_with(0.5)


async def test_sync_topics_does_not_retry_retry_after(
    tmp_path: Path, db_manager, monkeypatch
) -> None:
    """RetryAfter should not be retried by thread manager (AIORateLimiter owns retries)."""
    approved = tmp_path / "projects"
    approved.mkdir()

    config_file = _write_registry(tmp_path, approved, "app1")
    registry = load_project_registry(config_file, approved)
    repo = ProjectThreadRepository(db_manager)
    manager = ProjectThreadManager(
        registry,
        repo,
        sync_action_interval_seconds=0.0,
    )

    bot = AsyncMock()
    bot.create_forum_topic = AsyncMock(side_effect=RetryAfter(1))
    bot.send_message = AsyncMock()

    sleep_mock = AsyncMock()
    monkeypatch.setattr(thread_manager_module.asyncio, "sleep", sleep_mock)

    result = await manager.sync_topics(bot, chat_id=42)

    assert result.created == 0
    assert result.failed == 1
    assert bot.create_forum_topic.await_count == 1
    sleep_mock.assert_not_awaited()
