"""Telegram forum topic synchronization and project resolution."""

from dataclasses import dataclass
from typing import Optional

import structlog
from telegram import Bot
from telegram.error import TelegramError

from ..storage.models import ProjectThreadModel
from ..storage.repositories import ProjectThreadRepository
from .registry import ProjectDefinition, ProjectRegistry

logger = structlog.get_logger()


class PrivateTopicsUnavailableError(RuntimeError):
    """Raised when private chat topics are unavailable/disabled."""


@dataclass
class TopicSyncResult:
    """Summary of a synchronization run."""

    created: int = 0
    reused: int = 0
    renamed: int = 0
    failed: int = 0
    deactivated: int = 0


class ProjectThreadManager:
    """Maintains mapping between projects and Telegram forum topics."""

    def __init__(
        self,
        registry: ProjectRegistry,
        repository: ProjectThreadRepository,
    ) -> None:
        self.registry = registry
        self.repository = repository

    async def sync_topics(self, bot: Bot, chat_id: int) -> TopicSyncResult:
        """Create/reconcile topics for all enabled projects."""
        result = TopicSyncResult()

        enabled = self.registry.list_enabled()
        active_slugs = [project.slug for project in enabled]

        for project in enabled:
            try:
                existing = await self.repository.get_by_chat_project(
                    chat_id,
                    project.slug,
                )

                if existing:
                    result.reused += 1
                    topic_name = existing.topic_name
                    if existing.topic_name != project.name:
                        renamed = await self._rename_topic_if_possible(
                            bot=bot,
                            mapping=existing,
                            target_name=project.name,
                        )
                        if renamed:
                            result.renamed += 1
                            topic_name = project.name
                        else:
                            result.failed += 1

                    await self.repository.upsert_mapping(
                        project_slug=project.slug,
                        chat_id=chat_id,
                        message_thread_id=existing.message_thread_id,
                        topic_name=topic_name,
                        is_active=True,
                    )
                    continue

                topic = await bot.create_forum_topic(
                    chat_id=chat_id,
                    name=project.name,
                )

                await self.repository.upsert_mapping(
                    project_slug=project.slug,
                    chat_id=chat_id,
                    message_thread_id=topic.message_thread_id,
                    topic_name=project.name,
                    is_active=True,
                )
                await self._send_topic_bootstrap_message(
                    bot=bot,
                    chat_id=chat_id,
                    message_thread_id=topic.message_thread_id,
                    project_name=project.name,
                )
                result.created += 1

            except TelegramError as e:
                if self._is_private_topics_unavailable_error(e):
                    raise PrivateTopicsUnavailableError(
                        "Private chat topics are not enabled for this bot chat."
                    ) from e
                result.failed += 1
                logger.error(
                    "Failed to sync project topic",
                    project_slug=project.slug,
                    chat_id=chat_id,
                    error=str(e),
                )
            except Exception as e:
                result.failed += 1
                logger.error(
                    "Failed to sync project topic",
                    project_slug=project.slug,
                    chat_id=chat_id,
                    error=str(e),
                )

        result.deactivated = await self.repository.deactivate_missing_projects(
            chat_id=chat_id,
            active_project_slugs=active_slugs,
        )

        return result

    async def resolve_project(
        self, chat_id: int, message_thread_id: int
    ) -> Optional[ProjectDefinition]:
        """Resolve mapped project for chat+thread."""
        mapping = await self.repository.get_by_chat_thread(chat_id, message_thread_id)
        if not mapping:
            return None

        project = self.registry.get_by_slug(mapping.project_slug)
        if not project or not project.enabled:
            return None

        return project

    @staticmethod
    def guidance_message(mode: str = "group") -> str:
        """Guidance text for strict routing rejections."""
        context_label = (
            "mapped project topic in this private chat"
            if mode == "private"
            else "mapped project forum topic"
        )
        return (
            "🚫 <b>Project Thread Required</b>\n\n"
            "This bot is configured for strict project threads.\n"
            f"Please send commands in a {context_label}.\n\n"
            "If topics are missing or stale, run <code>/sync_threads</code>."
        )

    @staticmethod
    def private_topics_unavailable_message() -> str:
        """User guidance when private chat topics are unavailable."""
        return (
            "❌ <b>Private Topics Unavailable</b>\n\n"
            "This bot requires topics in private chat, but topics are not available.\n\n"
            "Enable topics for this bot chat in Telegram, then run "
            "<code>/sync_threads</code>."
        )

    @staticmethod
    def _is_private_topics_unavailable_error(error: TelegramError) -> bool:
        """Return True for Telegram errors indicating topics are unavailable."""
        text = str(error).lower()
        markers = [
            "topics are not enabled",
            "topic_closed",
            "topic deleted",
            "forum topics are disabled",
            "direct messages topic",
            "chat is not a forum",
        ]
        return any(marker in text for marker in markers)

    async def _rename_topic_if_possible(
        self,
        bot: Bot,
        mapping: ProjectThreadModel,
        target_name: str,
    ) -> bool:
        """Rename an existing forum topic (best effort)."""
        try:
            await bot.edit_forum_topic(
                chat_id=mapping.chat_id,
                message_thread_id=mapping.message_thread_id,
                name=target_name,
            )
            return True
        except TelegramError as e:
            logger.warning(
                "Could not rename topic",
                chat_id=mapping.chat_id,
                message_thread_id=mapping.message_thread_id,
                target_name=target_name,
                error=str(e),
            )
            return False

    async def _send_topic_bootstrap_message(
        self,
        bot: Bot,
        chat_id: int,
        message_thread_id: int,
        project_name: str,
    ) -> None:
        """Post a short message so newly created topics are visible in clients."""
        try:
            await bot.send_message(
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                text=(
                    f"🧵 <b>{project_name}</b>\n\n"
                    "This project topic is ready. Send messages here to work on this project."
                ),
                parse_mode="HTML",
            )
        except TelegramError as e:
            logger.warning(
                "Could not send topic bootstrap message",
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                project_name=project_name,
                error=str(e),
            )
