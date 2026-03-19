"""Message orchestrator — single entry point for all Telegram updates.

Routes messages based on agentic vs classic mode. In agentic mode, provides
a minimal conversational interface (3 commands, no inline keyboards). In
classic mode, delegates to existing full-featured handlers.
"""

import asyncio
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..claude.sdk_integration import StreamUpdate
from ..config.settings import Settings
from ..i18n import SUPPORTED_LANGUAGES, get_user_lang, LANG_NAMES, t
from ..projects import PrivateTopicsUnavailableError
from .utils.draft_streamer import DraftStreamer, generate_draft_id
from .utils.html_format import escape_html
from .utils.image_extractor import (
    ImageAttachment,
    should_send_as_photo,
    validate_image_path,
)
from .utils.progress import ProgressTracker

logger = structlog.get_logger()

# Patterns that look like secrets/credentials in CLI arguments
_SECRET_PATTERNS: List[re.Pattern[str]] = [
    # API keys / tokens (sk-ant-..., sk-..., ghp_..., gho_..., github_pat_..., xoxb-...)
    re.compile(
        r"(sk-ant-api\d*-[A-Za-z0-9_-]{10})[A-Za-z0-9_-]*"
        r"|(sk-[A-Za-z0-9_-]{20})[A-Za-z0-9_-]*"
        r"|(ghp_[A-Za-z0-9]{5})[A-Za-z0-9]*"
        r"|(gho_[A-Za-z0-9]{5})[A-Za-z0-9]*"
        r"|(github_pat_[A-Za-z0-9_]{5})[A-Za-z0-9_]*"
        r"|(xoxb-[A-Za-z0-9]{5})[A-Za-z0-9-]*"
    ),
    # AWS access keys
    re.compile(r"(AKIA[0-9A-Z]{4})[0-9A-Z]{12}"),
    # Generic long hex/base64 tokens after common flags/env patterns
    re.compile(
        r"((?:--token|--secret|--password|--api-key|--apikey|--auth)"
        r"[= ]+)['\"]?[A-Za-z0-9+/_.:-]{8,}['\"]?"
    ),
    # Inline env assignments like KEY=value
    re.compile(
        r"((?:TOKEN|SECRET|PASSWORD|API_KEY|APIKEY|AUTH_TOKEN|PRIVATE_KEY"
        r"|ACCESS_KEY|CLIENT_SECRET|WEBHOOK_SECRET)"
        r"=)['\"]?[^\s'\"]{8,}['\"]?"
    ),
    # Bearer / Basic auth headers
    re.compile(r"(Bearer )[A-Za-z0-9+/_.:-]{8,}" r"|(Basic )[A-Za-z0-9+/=]{8,}"),
    # Connection strings with credentials  user:pass@host
    re.compile(r"://([^:]+:)[^@]{4,}(@)"),
]


def _redact_secrets(text: str) -> str:
    """Replace likely secrets/credentials with redacted placeholders."""
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(
            lambda m: next((g + "***" for g in m.groups() if g is not None), "***"),
            result,
        )
    return result


# Tool name -> friendly emoji mapping for verbose output
_TOOL_ICONS: Dict[str, str] = {
    "Read": "\U0001f4d6",
    "Write": "\u270f\ufe0f",
    "Edit": "\u270f\ufe0f",
    "MultiEdit": "\u270f\ufe0f",
    "Bash": "\U0001f4bb",
    "Glob": "\U0001f50d",
    "Grep": "\U0001f50d",
    "LS": "\U0001f4c2",
    "Task": "\U0001f9e0",
    "TaskOutput": "\U0001f9e0",
    "WebFetch": "\U0001f310",
    "WebSearch": "\U0001f310",
    "NotebookRead": "\U0001f4d3",
    "NotebookEdit": "\U0001f4d3",
    "TodoRead": "\u2611\ufe0f",
    "TodoWrite": "\u2611\ufe0f",
}


def _tool_icon(name: str) -> str:
    """Return emoji for a tool, with a default wrench."""
    return _TOOL_ICONS.get(name, "\U0001f527")


class MessageOrchestrator:
    """Routes messages based on mode. Single entry point for all Telegram updates."""

    def __init__(self, settings: Settings, deps: Dict[str, Any]):
        self.settings = settings
        self.deps = deps

    def _inject_deps(self, handler: Callable) -> Callable:  # type: ignore[type-arg]
        """Wrap handler to inject dependencies into context.bot_data."""

        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            for key, value in self.deps.items():
                context.bot_data[key] = value
            context.bot_data["settings"] = self.settings
            context.user_data.pop("_thread_context", None)

            is_sync_bypass = handler.__name__ == "sync_threads"
            is_start_bypass = handler.__name__ in {"start_command", "agentic_start"}
            message_thread_id = self._extract_message_thread_id(update)
            should_enforce = self.settings.enable_project_threads

            if should_enforce:
                if self.settings.project_threads_mode == "private":
                    should_enforce = not is_sync_bypass and not (
                        is_start_bypass and message_thread_id is None
                    )
                else:
                    should_enforce = not is_sync_bypass

            if should_enforce:
                allowed = await self._apply_thread_routing_context(update, context)
                if not allowed:
                    return

            try:
                await handler(update, context)
            finally:
                if should_enforce:
                    self._persist_thread_state(context)

        return wrapped

    async def _apply_thread_routing_context(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """Enforce strict project-thread routing and load thread-local state."""
        manager = context.bot_data.get("project_threads_manager")
        if manager is None:
            await self._reject_for_thread_mode(
                update,
                "❌ <b>Project Thread Mode Misconfigured</b>\n\n"
                "Thread manager is not initialized.",
            )
            return False

        chat = update.effective_chat
        message = update.effective_message
        if not chat or not message:
            return False

        if self.settings.project_threads_mode == "group":
            if chat.id != self.settings.project_threads_chat_id:
                await self._reject_for_thread_mode(
                    update,
                    manager.guidance_message(mode=self.settings.project_threads_mode),
                )
                return False
        else:
            if getattr(chat, "type", "") != "private":
                await self._reject_for_thread_mode(
                    update,
                    manager.guidance_message(mode=self.settings.project_threads_mode),
                )
                return False

        message_thread_id = self._extract_message_thread_id(update)
        if not message_thread_id:
            await self._reject_for_thread_mode(
                update,
                manager.guidance_message(mode=self.settings.project_threads_mode),
            )
            return False

        project = await manager.resolve_project(chat.id, message_thread_id)
        if not project:
            await self._reject_for_thread_mode(
                update,
                manager.guidance_message(mode=self.settings.project_threads_mode),
            )
            return False

        state_key = f"{chat.id}:{message_thread_id}"
        thread_states = context.user_data.setdefault("thread_state", {})
        state = thread_states.get(state_key, {})

        project_root = project.absolute_path
        current_dir_raw = state.get("current_directory")
        current_dir = (
            Path(current_dir_raw).resolve() if current_dir_raw else project_root
        )
        if not self._is_within(current_dir, project_root) or not current_dir.is_dir():
            current_dir = project_root

        context.user_data["current_directory"] = current_dir
        context.user_data["claude_session_id"] = state.get("claude_session_id")
        context.user_data["_thread_context"] = {
            "chat_id": chat.id,
            "message_thread_id": message_thread_id,
            "state_key": state_key,
            "project_slug": project.slug,
            "project_root": str(project_root),
            "project_name": project.name,
        }
        return True

    def _persist_thread_state(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Persist compatibility keys back into per-thread state."""
        thread_context = context.user_data.get("_thread_context")
        if not thread_context:
            return

        project_root = Path(thread_context["project_root"])
        current_dir = context.user_data.get("current_directory", project_root)
        if not isinstance(current_dir, Path):
            current_dir = Path(str(current_dir))
        current_dir = current_dir.resolve()
        if not self._is_within(current_dir, project_root) or not current_dir.is_dir():
            current_dir = project_root

        thread_states = context.user_data.setdefault("thread_state", {})
        thread_states[thread_context["state_key"]] = {
            "current_directory": str(current_dir),
            "claude_session_id": context.user_data.get("claude_session_id"),
            "project_slug": thread_context["project_slug"],
        }

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        """Return True if path is within root."""
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _extract_message_thread_id(update: Update) -> Optional[int]:
        """Extract topic/thread id from update message for forum/direct topics."""
        message = update.effective_message
        if not message:
            return None
        message_thread_id = getattr(message, "message_thread_id", None)
        if isinstance(message_thread_id, int) and message_thread_id > 0:
            return message_thread_id
        dm_topic = getattr(message, "direct_messages_topic", None)
        topic_id = getattr(dm_topic, "topic_id", None) if dm_topic else None
        if isinstance(topic_id, int) and topic_id > 0:
            return topic_id
        # Telegram omits message_thread_id for the General topic in forum
        # supergroups; its canonical thread ID is 1.
        chat = update.effective_chat
        if chat and getattr(chat, "is_forum", False):
            return 1
        return None

    async def _reject_for_thread_mode(self, update: Update, message: str) -> None:
        """Send a guidance response when strict thread routing rejects an update."""
        query = update.callback_query
        if query:
            try:
                await query.answer()
            except Exception:
                pass
            if query.message:
                await query.message.reply_text(message, parse_mode="HTML")
            return

        if update.effective_message:
            await update.effective_message.reply_text(message, parse_mode="HTML")

    def register_handlers(self, app: Application) -> None:
        """Register handlers based on mode."""
        if self.settings.agentic_mode:
            self._register_agentic_handlers(app)
        else:
            self._register_classic_handlers(app)

    def _register_agentic_handlers(self, app: Application) -> None:
        """Register agentic handlers: commands + text/file/photo."""
        from .handlers import command

        # Commands
        handlers = [
            ("start", self.agentic_start),
            ("new", self.agentic_new),
            ("status", self.agentic_status),
            ("verbose", self.agentic_verbose),
            ("repo", self.agentic_repo),
            ("lang", self.agentic_lang),
            ("restart", command.restart_command),
        ]
        if self.settings.enable_project_threads:
            handlers.append(("sync_threads", command.sync_threads))

        # Code review command
        if self.settings.enable_code_review:
            handlers.append(("review", self.agentic_review))

        # A2A client commands
        if self.settings.enable_a2a:
            handlers.append(("agent", self.agentic_agent_call))
            handlers.append(("agents", self.agentic_agents_manage))

        # History search
        handlers.append(("search", self.agentic_search))

        # Team collaboration
        handlers.append(("team", self.agentic_team))

        for cmd, handler in handlers:
            app.add_handler(CommandHandler(cmd, self._inject_deps(handler)))

        # Text messages -> Claude
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._inject_deps(self.agentic_text),
            ),
            group=10,
        )

        # File uploads -> Claude
        app.add_handler(
            MessageHandler(
                filters.Document.ALL, self._inject_deps(self.agentic_document)
            ),
            group=10,
        )

        # Photo uploads -> Claude
        app.add_handler(
            MessageHandler(filters.PHOTO, self._inject_deps(self.agentic_photo)),
            group=10,
        )

        # Voice messages -> transcribe -> Claude
        app.add_handler(
            MessageHandler(filters.VOICE, self._inject_deps(self.agentic_voice)),
            group=10,
        )

        # Only cd: callbacks (for project selection), scoped by pattern
        app.add_handler(
            CallbackQueryHandler(
                self._inject_deps(self._agentic_callback),
                pattern=r"^cd:",
            )
        )

        # Dangerous operation confirmation callbacks
        app.add_handler(
            CallbackQueryHandler(
                self._inject_deps(self._agentic_dangerous_confirm_callback),
                pattern=r"^dangerous_confirm:",
            )
        )

        # Search pagination callbacks
        app.add_handler(
            CallbackQueryHandler(
                self._inject_deps(self._agentic_search_page_callback),
                pattern=r"^search_page:",
            )
        )

        logger.info("Agentic handlers registered")

    def _register_classic_handlers(self, app: Application) -> None:
        """Register full classic handler set (moved from core.py)."""
        from .handlers import callback, command, message

        handlers = [
            ("start", command.start_command),
            ("help", command.help_command),
            ("new", command.new_session),
            ("continue", command.continue_session),
            ("end", command.end_session),
            ("ls", command.list_files),
            ("cd", command.change_directory),
            ("pwd", command.print_working_directory),
            ("projects", command.show_projects),
            ("status", command.session_status),
            ("export", command.export_session),
            ("actions", command.quick_actions),
            ("git", command.git_command),
            ("lang", self.agentic_lang),
            ("restart", command.restart_command),
        ]
        if self.settings.enable_project_threads:
            handlers.append(("sync_threads", command.sync_threads))

        for cmd, handler in handlers:
            app.add_handler(CommandHandler(cmd, self._inject_deps(handler)))

        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._inject_deps(message.handle_text_message),
            ),
            group=10,
        )
        app.add_handler(
            MessageHandler(
                filters.Document.ALL, self._inject_deps(message.handle_document)
            ),
            group=10,
        )
        app.add_handler(
            MessageHandler(filters.PHOTO, self._inject_deps(message.handle_photo)),
            group=10,
        )
        app.add_handler(
            MessageHandler(filters.VOICE, self._inject_deps(message.handle_voice)),
            group=10,
        )
        app.add_handler(
            CallbackQueryHandler(self._inject_deps(callback.handle_callback_query))
        )

        logger.info("Classic handlers registered (13 commands + full handler set)")

    async def get_bot_commands(self) -> list:  # type: ignore[type-arg]
        """Return bot commands appropriate for current mode."""
        if self.settings.agentic_mode:
            commands = [
                BotCommand("start", "Start the bot"),
                BotCommand("new", t("cmd.new")),
                BotCommand("status", t("cmd.status")),
                BotCommand("verbose", t("cmd.verbose")),
                BotCommand("repo", t("cmd.repo")),
                BotCommand("lang", t("cmd.lang")),
                BotCommand("search", "Search conversation history"),
                BotCommand("team", "Team collaboration commands"),
                BotCommand("restart", t("cmd.restart")),
            ]
            if self.settings.enable_project_threads:
                commands.append(BotCommand("sync_threads", t("cmd.sync_threads")))
            return commands
        else:
            commands = [
                BotCommand("start", t("cmd.start")),
                BotCommand("help", t("cmd.help")),
                BotCommand("new", t("cmd.new")),
                BotCommand("continue", t("cmd.continue")),
                BotCommand("end", t("cmd.end")),
                BotCommand("ls", t("cmd.ls")),
                BotCommand("cd", t("cmd.cd")),
                BotCommand("pwd", t("cmd.pwd")),
                BotCommand("projects", t("cmd.projects")),
                BotCommand("status", t("cmd.status")),
                BotCommand("export", t("cmd.export")),
                BotCommand("actions", t("cmd.actions")),
                BotCommand("git", t("cmd.git")),
                BotCommand("lang", t("cmd.lang")),
                BotCommand("restart", t("cmd.restart")),
            ]
            if self.settings.enable_project_threads:
                commands.append(BotCommand("sync_threads", t("cmd.sync_threads")))
            return commands

    # --- Agentic handlers ---

    async def agentic_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Brief welcome, no buttons."""
        user = update.effective_user
        lang = get_user_lang(context)
        sync_line = ""
        if (
            self.settings.enable_project_threads
            and self.settings.project_threads_mode == "private"
        ):
            if (
                not update.effective_chat
                or getattr(update.effective_chat, "type", "") != "private"
            ):
                await update.message.reply_text(
                    t("start.private_topics_mode", lang),
                    parse_mode="HTML",
                )
                return
            manager = context.bot_data.get("project_threads_manager")
            if manager:
                try:
                    result = await manager.sync_topics(
                        context.bot,
                        chat_id=update.effective_chat.id,
                    )
                    sync_line = t(
                        "start.topics_synced", lang,
                        created=result.created, reused=result.reused,
                    )
                except PrivateTopicsUnavailableError:
                    await update.message.reply_text(
                        manager.private_topics_unavailable_message(),
                        parse_mode="HTML",
                    )
                    return
                except Exception:
                    sync_line = t("start.topic_sync_failed", lang)
        current_dir = context.user_data.get(
            "current_directory", self.settings.approved_directory
        )
        dir_display = f"<code>{current_dir}/</code>"

        safe_name = escape_html(user.first_name)
        await update.message.reply_text(
            t("start.welcome", lang, name=safe_name, dir_display=dir_display)
            + sync_line,
            parse_mode="HTML",
        )

    async def agentic_new(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Reset session, one-line confirmation."""
        context.user_data["claude_session_id"] = None
        context.user_data["session_started"] = True
        context.user_data["force_new_session"] = True

        lang = get_user_lang(context)
        await update.message.reply_text(t("new.reset", lang))

    async def agentic_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Compact one-line status, no buttons."""
        lang = get_user_lang(context)
        current_dir = context.user_data.get(
            "current_directory", self.settings.approved_directory
        )
        dir_display = str(current_dir)

        session_id = context.user_data.get("claude_session_id")
        session_status = "active" if session_id else "none"

        # Cost info
        cost_str = ""
        rate_limiter = context.bot_data.get("rate_limiter")
        if rate_limiter:
            try:
                user_status = rate_limiter.get_user_status(update.effective_user.id)
                cost_usage = user_status.get("cost_usage", {})
                current_cost = cost_usage.get("current", 0.0)
                cost_str = f" \u00b7 Cost: ${current_cost:.2f}"
            except Exception:
                pass

        await update.message.reply_text(
            t("status.line", lang,
              dir_display=dir_display, session_status=session_status,
              cost_str=cost_str)
        )

    async def agentic_review(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Manually trigger a code review: /review <pr_url>."""
        args = update.message.text.split()[1:] if update.message.text else []
        if not args:
            await update.message.reply_text(
                "Usage: <code>/review &lt;pr_url&gt;</code>\n\n"
                "Supports GitHub, GitLab, and Bitbucket PR/MR URLs.",
                parse_mode="HTML",
            )
            return

        pr_url = args[0]
        await update.message.reply_text("Reviewing PR... this may take a moment.")

        try:
            from .features.code_review import CodeReviewManager

            claude_integration = context.bot_data.get("claude_integration")
            if not claude_integration:
                await update.message.reply_text("Claude integration not available.")
                return

            current_dir = context.user_data.get(
                "current_directory", self.settings.approved_directory
            )

            manager = CodeReviewManager(claude_integration)

            # Build a prompt that asks Claude to fetch and review the PR
            review_prompt = (
                f"Please review the pull request at: {pr_url}\n\n"
                "Fetch the diff if possible, then analyze the changes. "
                "Provide a structured code review with:\n"
                "1. A summary of the changes\n"
                "2. Any issues found (with file, line, severity)\n"
                "3. Suggestions for improvement\n"
                "4. An approval recommendation (approve/request_changes/comment)"
            )

            result = await manager.review_pr(
                repo_path=current_dir,
                pr_diff=None,
                pr_title=f"PR from {pr_url}",
                pr_description=review_prompt,
            )

            formatted = result.format_telegram_message()
            await update.message.reply_text(formatted, parse_mode="HTML")

        except Exception as e:
            logger.exception("Code review failed", pr_url=pr_url)
            await update.message.reply_text(
                f"Code review failed: {escape_html(str(e))}",
                parse_mode="HTML",
            )

    def _get_verbose_level(self, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Return effective verbose level: per-user override or global default."""
        user_override = context.user_data.get("verbose_level")
        if user_override is not None:
            return int(user_override)
        return self.settings.verbose_level

    async def agentic_verbose(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Set output verbosity: /verbose [0|1|2]."""
        lang = get_user_lang(context)
        args = update.message.text.split()[1:] if update.message.text else []
        if not args:
            current = self._get_verbose_level(context)
            label_keys = {0: "verbose.quiet", 1: "verbose.normal", 2: "verbose.detailed"}
            label = t(label_keys.get(current, "verbose.normal"), lang)
            await update.message.reply_text(
                t("verbose.current", lang, level=current, label=label),
                parse_mode="HTML",
            )
            return

        try:
            level = int(args[0])
            if level not in (0, 1, 2):
                raise ValueError
        except ValueError:
            await update.message.reply_text(t("verbose.invalid", lang))
            return

        context.user_data["verbose_level"] = level
        label_keys = {0: "verbose.quiet", 1: "verbose.normal", 2: "verbose.detailed"}
        label = t(label_keys[level], lang)
        await update.message.reply_text(
            t("verbose.set", lang, level=level, label=label),
            parse_mode="HTML",
        )

    async def agentic_lang(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Set user language preference: /lang [en|zh]."""
        lang = get_user_lang(context)
        args = update.message.text.split()[1:] if update.message.text else []

        if not args:
            lang_name = LANG_NAMES.get(lang, lang)
            await update.message.reply_text(
                t("lang.current", lang, lang_name=lang_name),
                parse_mode="HTML",
            )
            return

        new_lang = args[0].lower().strip()
        if new_lang not in SUPPORTED_LANGUAGES:
            supported = ", ".join(SUPPORTED_LANGUAGES)
            await update.message.reply_text(
                t("lang.invalid", lang, lang=escape_html(new_lang),
                  supported=supported),
                parse_mode="HTML",
            )
            return

        context.user_data["language"] = new_lang
        lang_name = LANG_NAMES.get(new_lang, new_lang)
        await update.message.reply_text(
            t("lang.set", new_lang, lang_name=lang_name),
            parse_mode="HTML",
        )

    def _format_verbose_progress(
        self,
        activity_log: List[Dict[str, Any]],
        verbose_level: int,
        start_time: float,
        progress_tracker: Optional[ProgressTracker] = None,
    ) -> str:
        """Build the progress message text based on activity so far."""
        if not activity_log:
            return "Working..."

        elapsed = time.time() - start_time

        # Use ProgressTracker stage header when available
        if progress_tracker:
            progress_tracker.check_review_transition()
            header = progress_tracker.format_progress()
        else:
            header = f"Working... ({elapsed:.0f}s)"

        lines: List[str] = [header + "\n"]

        for entry in activity_log[-15:]:  # Show last 15 entries max
            kind = entry.get("kind", "tool")
            if kind == "text":
                # Claude's intermediate reasoning/commentary
                snippet = entry.get("detail", "")
                if verbose_level >= 2:
                    lines.append(f"\U0001f4ac {snippet}")
                else:
                    # Level 1: one short line
                    lines.append(f"\U0001f4ac {snippet[:80]}")
            else:
                # Tool call
                icon = _tool_icon(entry["name"])
                if verbose_level >= 2 and entry.get("detail"):
                    lines.append(f"{icon} {entry['name']}: {entry['detail']}")
                else:
                    lines.append(f"{icon} {entry['name']}")

        if len(activity_log) > 15:
            lines.insert(1, f"... ({len(activity_log) - 15} earlier entries)\n")

        return "\n".join(lines)

    @staticmethod
    def _summarize_tool_input(tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Return a short summary of tool input for verbose level 2."""
        if not tool_input:
            return ""
        if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
            path = tool_input.get("file_path") or tool_input.get("path", "")
            if path:
                # Show just the filename, not the full path
                return path.rsplit("/", 1)[-1]
        if tool_name in ("Glob", "Grep"):
            pattern = tool_input.get("pattern", "")
            if pattern:
                return pattern[:60]
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            if cmd:
                return _redact_secrets(cmd[:100])[:80]
        if tool_name in ("WebFetch", "WebSearch"):
            return (tool_input.get("url", "") or tool_input.get("query", ""))[:60]
        if tool_name == "Task":
            desc = tool_input.get("description", "")
            if desc:
                return desc[:60]
        # Generic: show first key's value
        for v in tool_input.values():
            if isinstance(v, str) and v:
                return v[:60]
        return ""

    @staticmethod
    def _start_typing_heartbeat(
        chat: Any,
        interval: float = 2.0,
    ) -> "asyncio.Task[None]":
        """Start a background typing indicator task.

        Sends typing every *interval* seconds, independently of
        stream events. Cancel the returned task in a ``finally``
        block.
        """

        async def _heartbeat() -> None:
            try:
                while True:
                    await asyncio.sleep(interval)
                    try:
                        await chat.send_action("typing")
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        return asyncio.create_task(_heartbeat())

    def _make_stream_callback(
        self,
        verbose_level: int,
        progress_msg: Any,
        tool_log: List[Dict[str, Any]],
        start_time: float,
        mcp_images: Optional[List[ImageAttachment]] = None,
        approved_directory: Optional[Path] = None,
        draft_streamer: Optional[DraftStreamer] = None,
    ) -> Optional[Callable[[StreamUpdate], Any]]:
        """Create a stream callback for verbose progress updates.

        When *mcp_images* is provided, the callback also intercepts
        ``send_image_to_user`` tool calls and collects validated
        :class:`ImageAttachment` objects for later Telegram delivery.

        When *draft_streamer* is provided, tool activity and assistant
        text are streamed to the user in real time via
        ``sendMessageDraft``.

        Returns None when verbose_level is 0 **and** no MCP image
        collection or draft streaming is requested.
        Typing indicators are handled by a separate heartbeat task.
        """
        need_mcp_intercept = mcp_images is not None and approved_directory is not None

        if verbose_level == 0 and not need_mcp_intercept and draft_streamer is None:
            return None

        last_edit_time = [0.0]  # mutable container for closure
        tracker = ProgressTracker(start_time=start_time)

        async def _on_stream(update_obj: StreamUpdate) -> None:
            # Intercept send_image_to_user MCP tool calls.
            # The SDK namespaces MCP tools as "mcp__<server>__<tool>",
            # so match both the bare name and the namespaced variant.
            if update_obj.tool_calls and need_mcp_intercept:
                for tc in update_obj.tool_calls:
                    tc_name = tc.get("name", "")
                    if tc_name == "send_image_to_user" or tc_name.endswith(
                        "__send_image_to_user"
                    ):
                        tc_input = tc.get("input", {})
                        file_path = tc_input.get("file_path", "")
                        caption = tc_input.get("caption", "")
                        img = validate_image_path(
                            file_path, approved_directory, caption
                        )
                        if img:
                            mcp_images.append(img)

            # Capture tool calls and update progress stage
            if update_obj.tool_calls:
                for tc in update_obj.tool_calls:
                    name = tc.get("name", "unknown")
                    tc_input = tc.get("input", {})
                    detail = self._summarize_tool_input(name, tc_input)
                    # Update progress tracker with each tool call
                    tracker.update_stage(name, tc_input)
                    if verbose_level >= 1:
                        tool_log.append(
                            {"kind": "tool", "name": name, "detail": detail}
                        )
                    if draft_streamer:
                        icon = _tool_icon(name)
                        line = (
                            f"{icon} {name}: {detail}" if detail else f"{icon} {name}"
                        )
                        await draft_streamer.append_tool(line)

            # Capture assistant text (reasoning / commentary)
            if update_obj.type == "assistant" and update_obj.content:
                text = update_obj.content.strip()
                if text:
                    first_line = text.split("\n", 1)[0].strip()
                    if first_line:
                        if verbose_level >= 1:
                            tool_log.append(
                                {"kind": "text", "detail": first_line[:120]}
                            )
                        if draft_streamer:
                            await draft_streamer.append_tool(
                                f"\U0001f4ac {first_line[:120]}"
                            )

            # Stream text to user via draft (prefer token deltas;
            # skip full assistant messages to avoid double-appending)
            if draft_streamer and update_obj.content:
                if update_obj.type == "stream_delta":
                    await draft_streamer.append_text(update_obj.content)

            # Throttle progress message edits to avoid Telegram rate limits
            if not draft_streamer and verbose_level >= 1:
                now = time.time()
                if (now - last_edit_time[0]) >= 2.0 and tool_log:
                    last_edit_time[0] = now
                    new_text = self._format_verbose_progress(
                        tool_log, verbose_level, start_time,
                        progress_tracker=tracker,
                    )
                    try:
                        await progress_msg.edit_text(new_text)
                    except Exception:
                        pass

        return _on_stream

    async def _send_images(
        self,
        update: Update,
        images: List[ImageAttachment],
        reply_to_message_id: Optional[int] = None,
        caption: Optional[str] = None,
        caption_parse_mode: Optional[str] = None,
    ) -> bool:
        """Send extracted images as a media group (album) or documents.

        If *caption* is provided and fits (≤1024 chars), it is attached to the
        photo / first album item so text + images appear as one message.

        Returns True if the caption was successfully embedded in the photo message.
        """
        photos: List[ImageAttachment] = []
        documents: List[ImageAttachment] = []
        for img in images:
            if should_send_as_photo(img.path):
                photos.append(img)
            else:
                documents.append(img)

        # Telegram caption limit
        use_caption = bool(
            caption and len(caption) <= 1024 and photos and not documents
        )
        caption_sent = False

        # Send raster photos as a single album (Telegram groups 2-10 items)
        if photos:
            try:
                if len(photos) == 1:
                    with open(photos[0].path, "rb") as f:
                        await update.message.reply_photo(
                            photo=f,
                            reply_to_message_id=reply_to_message_id,
                            caption=caption if use_caption else None,
                            parse_mode=caption_parse_mode if use_caption else None,
                        )
                    caption_sent = use_caption
                else:
                    media = []
                    file_handles = []
                    for idx, img in enumerate(photos[:10]):
                        fh = open(img.path, "rb")  # noqa: SIM115
                        file_handles.append(fh)
                        media.append(
                            InputMediaPhoto(
                                media=fh,
                                caption=caption if use_caption and idx == 0 else None,
                                parse_mode=(
                                    caption_parse_mode
                                    if use_caption and idx == 0
                                    else None
                                ),
                            )
                        )
                    try:
                        await update.message.chat.send_media_group(
                            media=media,
                            reply_to_message_id=reply_to_message_id,
                        )
                        caption_sent = use_caption
                    finally:
                        for fh in file_handles:
                            fh.close()
            except Exception as e:
                logger.warning("Failed to send photo album", error=str(e))

        # Send SVGs / large files as documents (one by one — can't mix in album)
        for img in documents:
            try:
                with open(img.path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=img.path.name,
                        reply_to_message_id=reply_to_message_id,
                    )
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(
                    "Failed to send document image",
                    path=str(img.path),
                    error=str(e),
                )

        return caption_sent

    async def agentic_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Direct Claude passthrough. Simple progress. No suggestions."""
        user_id = update.effective_user.id
        message_text = update.message.text
        lang = get_user_lang(context)

        logger.info(
            "Agentic text message",
            user_id=user_id,
            message_length=len(message_text),
        )

        # Rate limit check
        rate_limiter = context.bot_data.get("rate_limiter")
        if rate_limiter:
            allowed, limit_message = await rate_limiter.check_rate_limit(user_id, 0.001)
            if not allowed:
                await update.message.reply_text(
                    t("error.rate_limited", lang, message=limit_message)
                )
                return

        chat = update.message.chat
        await chat.send_action("typing")

        verbose_level = self._get_verbose_level(context)
        progress_msg = await update.message.reply_text(t("progress.working", lang))

        claude_integration = context.bot_data.get("claude_integration")
        if not claude_integration:
            await progress_msg.edit_text(t("error.claude_unavailable", lang))
            return

        current_dir = context.user_data.get(
            "current_directory", self.settings.approved_directory
        )
        session_id = context.user_data.get("claude_session_id")

        # Check if /new was used — skip auto-resume for this first message.
        # Flag is only cleared after a successful run so retries keep the intent.
        force_new = bool(context.user_data.get("force_new_session"))

        # --- Verbose progress tracking via stream callback ---
        tool_log: List[Dict[str, Any]] = []
        start_time = time.time()
        mcp_images: List[ImageAttachment] = []

        # Stream drafts (private chats only)
        draft_streamer: Optional[DraftStreamer] = None
        if self.settings.enable_stream_drafts and chat.type == "private":
            draft_streamer = DraftStreamer(
                bot=context.bot,
                chat_id=chat.id,
                draft_id=generate_draft_id(),
                message_thread_id=update.message.message_thread_id,
                throttle_interval=self.settings.stream_draft_interval,
            )

        on_stream = self._make_stream_callback(
            verbose_level,
            progress_msg,
            tool_log,
            start_time,
            mcp_images=mcp_images,
            approved_directory=self.settings.approved_directory,
            draft_streamer=draft_streamer,
        )

        # Independent typing heartbeat — stays alive even with no stream events
        heartbeat = self._start_typing_heartbeat(chat)

        success = True
        try:
            claude_response = await claude_integration.run_command(
                prompt=message_text,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=on_stream,
                force_new=force_new,
            )

            # New session created successfully — clear the one-shot flag
            if force_new:
                context.user_data["force_new_session"] = False

            context.user_data["claude_session_id"] = claude_response.session_id

            # Track directory changes
            from .handlers.message import _update_working_directory_from_claude_response

            _update_working_directory_from_claude_response(
                claude_response, context, self.settings, user_id
            )

            # Store interaction
            storage = context.bot_data.get("storage")
            if storage:
                try:
                    await storage.save_claude_interaction(
                        user_id=user_id,
                        session_id=claude_response.session_id,
                        prompt=message_text,
                        response=claude_response,
                        ip_address=None,
                    )
                except Exception as e:
                    logger.warning("Failed to log interaction", error=str(e))

            # Format response (no reply_markup — strip keyboards)
            from .utils.formatting import ResponseFormatter

            formatter = ResponseFormatter(self.settings)
            formatted_messages = formatter.format_claude_response(
                claude_response.content
            )

        except Exception as e:
            success = False
            logger.error("Claude integration failed", error=str(e), user_id=user_id)
            from .handlers.message import _format_error_message
            from .utils.formatting import FormattedMessage

            formatted_messages = [
                FormattedMessage(_format_error_message(e), parse_mode="HTML")
            ]
        finally:
            heartbeat.cancel()
            if draft_streamer:
                try:
                    await draft_streamer.flush()
                except Exception:
                    logger.debug("Draft flush failed in finally block", user_id=user_id)

        try:
            await progress_msg.delete()
        except Exception:
            logger.debug("Failed to delete progress message, ignoring")

        # Use MCP-collected images (from send_image_to_user tool calls)
        images: List[ImageAttachment] = mcp_images

        # Try to combine text + images in one message when possible
        caption_sent = False
        if images and len(formatted_messages) == 1:
            msg = formatted_messages[0]
            if msg.text and len(msg.text) <= 1024:
                try:
                    caption_sent = await self._send_images(
                        update,
                        images,
                        reply_to_message_id=update.message.message_id,
                        caption=msg.text,
                        caption_parse_mode=msg.parse_mode,
                    )
                except Exception as img_err:
                    logger.warning("Image+caption send failed", error=str(img_err))

        # Send text messages (skip if caption was already embedded in photos)
        if not caption_sent:
            for i, message in enumerate(formatted_messages):
                if not message.text or not message.text.strip():
                    continue
                try:
                    await update.message.reply_text(
                        message.text,
                        parse_mode=message.parse_mode,
                        reply_markup=None,  # No keyboards in agentic mode
                        reply_to_message_id=(
                            update.message.message_id if i == 0 else None
                        ),
                    )
                    if i < len(formatted_messages) - 1:
                        await asyncio.sleep(0.5)
                except Exception as send_err:
                    logger.warning(
                        "Failed to send HTML response, retrying as plain text",
                        error=str(send_err),
                        message_index=i,
                    )
                    try:
                        await update.message.reply_text(
                            message.text,
                            reply_markup=None,
                            reply_to_message_id=(
                                update.message.message_id if i == 0 else None
                            ),
                        )
                    except Exception as plain_err:
                        await update.message.reply_text(
                            f"Failed to deliver response "
                            f"(Telegram error: {str(plain_err)[:150]}). "
                            f"Please try again.",
                            reply_to_message_id=(
                                update.message.message_id if i == 0 else None
                            ),
                        )

            # Send images separately if caption wasn't used
            if images:
                try:
                    await self._send_images(
                        update,
                        images,
                        reply_to_message_id=update.message.message_id,
                    )
                except Exception as img_err:
                    logger.warning("Image send failed", error=str(img_err))

        # Audit log
        audit_logger = context.bot_data.get("audit_logger")
        if audit_logger:
            await audit_logger.log_command(
                user_id=user_id,
                command="text_message",
                args=[message_text[:100]],
                success=success,
            )

    async def agentic_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Process file upload -> Claude, minimal chrome."""
        user_id = update.effective_user.id
        document = update.message.document
        lang = get_user_lang(context)

        logger.info(
            "Agentic document upload",
            user_id=user_id,
            filename=document.file_name,
        )

        # Security validation
        security_validator = context.bot_data.get("security_validator")
        if security_validator:
            valid, error = security_validator.validate_filename(document.file_name)
            if not valid:
                await update.message.reply_text(
                    t("error.file_rejected", lang, error=error)
                )
                return

        # Size check
        max_size = 10 * 1024 * 1024
        if document.file_size > max_size:
            await update.message.reply_text(
                t("error.file_too_large", lang,
                  size=f"{document.file_size / 1024 / 1024:.1f}")
            )
            return

        chat = update.message.chat
        await chat.send_action("typing")
        progress_msg = await update.message.reply_text(t("progress.working", lang))

        # Try enhanced file handler, fall back to basic
        features = context.bot_data.get("features")
        file_handler = features.get_file_handler() if features else None
        prompt: Optional[str] = None

        if file_handler:
            try:
                processed_file = await file_handler.handle_document_upload(
                    document,
                    user_id,
                    update.message.caption or "Please review this file:",
                )
                prompt = processed_file.prompt
            except Exception:
                file_handler = None

        if not file_handler:
            file = await document.get_file()
            file_bytes = await file.download_as_bytearray()
            try:
                content = file_bytes.decode("utf-8")
                if len(content) > 50000:
                    content = content[:50000] + "\n... (truncated)"
                caption = update.message.caption or "Please review this file:"
                prompt = (
                    f"{caption}\n\n**File:** `{document.file_name}`\n\n"
                    f"```\n{content}\n```"
                )
            except UnicodeDecodeError:
                await progress_msg.edit_text(t("error.unsupported_format", lang))
                return

        # Process with Claude
        claude_integration = context.bot_data.get("claude_integration")
        if not claude_integration:
            await progress_msg.edit_text(t("error.claude_unavailable", lang))
            return

        current_dir = context.user_data.get(
            "current_directory", self.settings.approved_directory
        )
        session_id = context.user_data.get("claude_session_id")

        # Check if /new was used — skip auto-resume for this first message.
        # Flag is only cleared after a successful run so retries keep the intent.
        force_new = bool(context.user_data.get("force_new_session"))

        verbose_level = self._get_verbose_level(context)
        tool_log: List[Dict[str, Any]] = []
        mcp_images_doc: List[ImageAttachment] = []
        on_stream = self._make_stream_callback(
            verbose_level,
            progress_msg,
            tool_log,
            time.time(),
            mcp_images=mcp_images_doc,
            approved_directory=self.settings.approved_directory,
        )

        heartbeat = self._start_typing_heartbeat(chat)
        try:
            claude_response = await claude_integration.run_command(
                prompt=prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=on_stream,
                force_new=force_new,
            )

            if force_new:
                context.user_data["force_new_session"] = False

            context.user_data["claude_session_id"] = claude_response.session_id

            from .handlers.message import _update_working_directory_from_claude_response

            _update_working_directory_from_claude_response(
                claude_response, context, self.settings, user_id
            )

            from .utils.formatting import ResponseFormatter

            formatter = ResponseFormatter(self.settings)
            formatted_messages = formatter.format_claude_response(
                claude_response.content
            )

            try:
                await progress_msg.delete()
            except Exception:
                logger.debug("Failed to delete progress message, ignoring")

            # Use MCP-collected images (from send_image_to_user tool calls)
            images: List[ImageAttachment] = mcp_images_doc

            caption_sent = False
            if images and len(formatted_messages) == 1:
                msg = formatted_messages[0]
                if msg.text and len(msg.text) <= 1024:
                    try:
                        caption_sent = await self._send_images(
                            update,
                            images,
                            reply_to_message_id=update.message.message_id,
                            caption=msg.text,
                            caption_parse_mode=msg.parse_mode,
                        )
                    except Exception as img_err:
                        logger.warning("Image+caption send failed", error=str(img_err))

            if not caption_sent:
                for i, message in enumerate(formatted_messages):
                    await update.message.reply_text(
                        message.text,
                        parse_mode=message.parse_mode,
                        reply_markup=None,
                        reply_to_message_id=(
                            update.message.message_id if i == 0 else None
                        ),
                    )
                    if i < len(formatted_messages) - 1:
                        await asyncio.sleep(0.5)

                if images:
                    try:
                        await self._send_images(
                            update,
                            images,
                            reply_to_message_id=update.message.message_id,
                        )
                    except Exception as img_err:
                        logger.warning("Image send failed", error=str(img_err))

        except Exception as e:
            from .handlers.message import _format_error_message

            await progress_msg.edit_text(_format_error_message(e), parse_mode="HTML")
            logger.error("Claude file processing failed", error=str(e), user_id=user_id)
        finally:
            heartbeat.cancel()

    async def agentic_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Process photo -> Claude, minimal chrome."""
        user_id = update.effective_user.id
        lang = get_user_lang(context)

        features = context.bot_data.get("features")
        image_handler = features.get_image_handler() if features else None

        if not image_handler:
            await update.message.reply_text(t("error.photo_unavailable", lang))
            return

        chat = update.message.chat
        await chat.send_action("typing")
        progress_msg = await update.message.reply_text(t("progress.working", lang))

        try:
            photo = update.message.photo[-1]
            processed_image = await image_handler.process_image(
                photo, update.message.caption
            )
            await self._handle_agentic_media_message(
                update=update,
                context=context,
                prompt=processed_image.prompt,
                progress_msg=progress_msg,
                user_id=user_id,
                chat=chat,
            )

        except Exception as e:
            from .handlers.message import _format_error_message

            await progress_msg.edit_text(_format_error_message(e), parse_mode="HTML")
            logger.error(
                "Claude photo processing failed", error=str(e), user_id=user_id
            )

    async def agentic_voice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Transcribe voice message -> Claude, minimal chrome."""
        user_id = update.effective_user.id
        lang = get_user_lang(context)

        features = context.bot_data.get("features")
        voice_handler = features.get_voice_handler() if features else None

        if not voice_handler:
            await update.message.reply_text(self._voice_unavailable_message(lang))
            return

        chat = update.message.chat
        await chat.send_action("typing")
        progress_msg = await update.message.reply_text(t("progress.transcribing", lang))

        try:
            voice = update.message.voice
            processed_voice = await voice_handler.process_voice_message(
                voice, update.message.caption
            )

            await progress_msg.edit_text(t("progress.working", lang))
            await self._handle_agentic_media_message(
                update=update,
                context=context,
                prompt=processed_voice.prompt,
                progress_msg=progress_msg,
                user_id=user_id,
                chat=chat,
            )

        except Exception as e:
            from .handlers.message import _format_error_message

            await progress_msg.edit_text(_format_error_message(e), parse_mode="HTML")
            logger.error(
                "Claude voice processing failed", error=str(e), user_id=user_id
            )

    async def _handle_agentic_media_message(
        self,
        *,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        prompt: str,
        progress_msg: Any,
        user_id: int,
        chat: Any,
    ) -> None:
        """Run a media-derived prompt through Claude and send responses."""
        lang = get_user_lang(context)
        claude_integration = context.bot_data.get("claude_integration")
        if not claude_integration:
            await progress_msg.edit_text(t("error.claude_unavailable", lang))
            return

        current_dir = context.user_data.get(
            "current_directory", self.settings.approved_directory
        )
        session_id = context.user_data.get("claude_session_id")
        force_new = bool(context.user_data.get("force_new_session"))

        verbose_level = self._get_verbose_level(context)
        tool_log: List[Dict[str, Any]] = []
        mcp_images_media: List[ImageAttachment] = []
        on_stream = self._make_stream_callback(
            verbose_level,
            progress_msg,
            tool_log,
            time.time(),
            mcp_images=mcp_images_media,
            approved_directory=self.settings.approved_directory,
        )

        heartbeat = self._start_typing_heartbeat(chat)
        try:
            claude_response = await claude_integration.run_command(
                prompt=prompt,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=on_stream,
                force_new=force_new,
            )
        finally:
            heartbeat.cancel()

        if force_new:
            context.user_data["force_new_session"] = False

        context.user_data["claude_session_id"] = claude_response.session_id

        from .handlers.message import _update_working_directory_from_claude_response

        _update_working_directory_from_claude_response(
            claude_response, context, self.settings, user_id
        )

        from .utils.formatting import ResponseFormatter

        formatter = ResponseFormatter(self.settings)
        formatted_messages = formatter.format_claude_response(claude_response.content)

        try:
            await progress_msg.delete()
        except Exception:
            logger.debug("Failed to delete progress message, ignoring")

        # Use MCP-collected images (from send_image_to_user tool calls).
        images: List[ImageAttachment] = mcp_images_media

        caption_sent = False
        if images and len(formatted_messages) == 1:
            msg = formatted_messages[0]
            if msg.text and len(msg.text) <= 1024:
                try:
                    caption_sent = await self._send_images(
                        update,
                        images,
                        reply_to_message_id=update.message.message_id,
                        caption=msg.text,
                        caption_parse_mode=msg.parse_mode,
                    )
                except Exception as img_err:
                    logger.warning("Image+caption send failed", error=str(img_err))

        if not caption_sent:
            for i, message in enumerate(formatted_messages):
                if not message.text or not message.text.strip():
                    continue
                await update.message.reply_text(
                    message.text,
                    parse_mode=message.parse_mode,
                    reply_markup=None,
                    reply_to_message_id=(update.message.message_id if i == 0 else None),
                )
                if i < len(formatted_messages) - 1:
                    await asyncio.sleep(0.5)

            if images:
                try:
                    await self._send_images(
                        update,
                        images,
                        reply_to_message_id=update.message.message_id,
                    )
                except Exception as img_err:
                    logger.warning("Image send failed", error=str(img_err))

    def _voice_unavailable_message(self, lang: str = "en") -> str:
        """Return provider-aware guidance when voice feature is unavailable."""
        return t(
            "voice.unavailable", lang,
            api_key_env=self.settings.voice_provider_api_key_env,
            provider_name=self.settings.voice_provider_display_name,
        )

    async def agentic_repo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """List repos in workspace or switch to one.

        /repo          — list subdirectories with git indicators
        /repo <name>   — switch to that directory, resume session if available
        """
        lang = get_user_lang(context)
        args = update.message.text.split()[1:] if update.message.text else []
        base = self.settings.approved_directory
        current_dir = context.user_data.get("current_directory", base)

        if args:
            # Switch to named repo
            target_name = args[0]
            target_path = base / target_name
            if not target_path.is_dir():
                await update.message.reply_text(
                    t("error.dir_not_found", lang,
                      name=escape_html(target_name)),
                    parse_mode="HTML",
                )
                return

            context.user_data["current_directory"] = target_path

            # Try to find a resumable session
            claude_integration = context.bot_data.get("claude_integration")
            session_id = None
            if claude_integration:
                existing = await claude_integration._find_resumable_session(
                    update.effective_user.id, target_path
                )
                if existing:
                    session_id = existing.session_id
            context.user_data["claude_session_id"] = session_id

            is_git = (target_path / ".git").is_dir()
            git_badge = t("repo.git_badge", lang) if is_git else ""
            session_badge = t("repo.session_resumed", lang) if session_id else ""

            await update.message.reply_text(
                t("repo.switched", lang,
                  name=escape_html(target_name),
                  git_badge=git_badge, session_badge=session_badge),
                parse_mode="HTML",
            )
            return

        # No args — list repos
        try:
            entries = sorted(
                [
                    d
                    for d in base.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                ],
                key=lambda d: d.name,
            )
        except OSError as e:
            await update.message.reply_text(
                t("error.workspace_read", lang, error=str(e))
            )
            return

        if not entries:
            await update.message.reply_text(
                t("repo.no_repos", lang,
                  path=escape_html(str(base))),
                parse_mode="HTML",
            )
            return

        lines: List[str] = []
        keyboard_rows: List[list] = []  # type: ignore[type-arg]
        current_name = current_dir.name if current_dir != base else None

        for d in entries:
            is_git = (d / ".git").is_dir()
            icon = "\U0001f4e6" if is_git else "\U0001f4c1"
            marker = " \u25c0" if d.name == current_name else ""
            lines.append(f"{icon} <code>{escape_html(d.name)}/</code>{marker}")

        # Build inline keyboard (2 per row)
        for i in range(0, len(entries), 2):
            row = []
            for j in range(2):
                if i + j < len(entries):
                    name = entries[i + j].name
                    row.append(InlineKeyboardButton(name, callback_data=f"cd:{name}"))
            keyboard_rows.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        await update.message.reply_text(
            t("repo.title", lang) + "\n\n" + "\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    async def _agentic_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle cd: callbacks — switch directory and resume session if available."""
        lang = get_user_lang(context)
        query = update.callback_query
        await query.answer()

        data = query.data
        _, project_name = data.split(":", 1)

        base = self.settings.approved_directory
        new_path = base / project_name

        if not new_path.is_dir():
            await query.edit_message_text(
                t("error.dir_not_found", lang,
                  name=escape_html(project_name)),
                parse_mode="HTML",
            )
            return

        context.user_data["current_directory"] = new_path

        # Look for a resumable session instead of always clearing
        claude_integration = context.bot_data.get("claude_integration")
        session_id = None
        if claude_integration:
            existing = await claude_integration._find_resumable_session(
                query.from_user.id, new_path
            )
            if existing:
                session_id = existing.session_id
        context.user_data["claude_session_id"] = session_id

        is_git = (new_path / ".git").is_dir()
        git_badge = t("repo.git_badge", lang) if is_git else ""
        session_badge = t("repo.session_resumed", lang) if session_id else ""

        await query.edit_message_text(
            t("repo.switched", lang,
              name=escape_html(project_name),
              git_badge=git_badge, session_badge=session_badge),
            parse_mode="HTML",
        )

        # Audit log
        audit_logger = context.bot_data.get("audit_logger")
        if audit_logger:
            await audit_logger.log_command(
                user_id=query.from_user.id,
                command="cd",
                args=[project_name],
                success=True,
            )

    # ---- A2A client handlers ----

    async def agentic_agent_call(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Call a registered remote A2A agent.

        Usage: /agent <alias> <message>
        """
        if not update.message or not update.message.text:
            return

        lang = get_user_lang(context)
        parts = update.message.text.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text(
                t("a2a.agent_usage", lang),
                parse_mode="HTML",
            )
            return

        alias = parts[1]
        message_text = parts[2]

        registry = context.bot_data.get("a2a_registry")
        client_manager = context.bot_data.get("a2a_client_manager")
        if not registry or not client_manager:
            await update.message.reply_text(t("error.a2a_not_enabled", lang))
            return

        user_id = update.effective_user.id
        agent = registry.get(user_id, alias)
        if not agent:
            await update.message.reply_text(
                t("a2a.agent_not_found", lang,
                  alias=escape_html(alias)),
                parse_mode="HTML",
            )
            return

        await update.effective_chat.send_action("typing")

        try:
            response_text = await client_manager.send_message(
                agent.url, message_text
            )
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "\n\n... (truncated)"

            header = f"\U0001f916 <b>{escape_html(agent.name or alias)}</b>:\n\n"
            await update.message.reply_text(
                header + escape_html(response_text),
                parse_mode="HTML",
            )
        except ValueError as e:
            await update.message.reply_text(
                f"\u274c {escape_html(str(e))}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("A2A agent call failed", alias=alias, error=str(e))
            await update.message.reply_text(
                t("a2a.call_failed", lang,
                  alias=escape_html(alias),
                  error=escape_html(str(e)[:500])),
                parse_mode="HTML",
            )

    async def agentic_agents_manage(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Manage registered A2A agents.

        /agents              -- list registered agents
        /agents add <alias> <url>  -- register a new agent
        /agents remove <alias>     -- remove an agent
        """
        if not update.message or not update.message.text:
            return

        lang = get_user_lang(context)
        registry = context.bot_data.get("a2a_registry")
        client_manager = context.bot_data.get("a2a_client_manager")
        if not registry or not client_manager:
            await update.message.reply_text(t("error.a2a_not_enabled", lang))
            return

        user_id = update.effective_user.id
        parts = update.message.text.split()

        # /agents (list)
        if len(parts) == 1:
            agents = registry.list_agents(user_id)
            if not agents:
                await update.message.reply_text(
                    t("a2a.no_agents", lang),
                    parse_mode="HTML",
                )
                return

            lines = [t("a2a.agents_title", lang)]
            for a in agents:
                name_str = f" ({escape_html(a.name)})" if a.name else ""
                lines.append(
                    f"\u2022 <code>{escape_html(a.alias)}</code>{name_str}\n"
                    f"  {escape_html(a.url)}"
                )
            await update.message.reply_text(
                "\n".join(lines), parse_mode="HTML"
            )
            return

        action = parts[1].lower()

        # /agents add <alias> <url>
        if action == "add" and len(parts) >= 4:
            alias = parts[2]
            url = parts[3]

            await update.effective_chat.send_action("typing")

            try:
                # URL validation happens inside resolve_agent (SSRF protection)
                card = await client_manager.resolve_agent(url)
                agent = await registry.register(
                    user_id=user_id,
                    alias=alias,
                    url=url,
                    name=card.name,
                    description=card.description,
                )
                await update.message.reply_text(
                    t("a2a.agent_registered", lang,
                      alias=escape_html(alias),
                      name=escape_html(agent.name or "N/A"),
                      url=escape_html(url)),
                    parse_mode="HTML",
                )
            except ValueError as e:
                await update.message.reply_text(
                    f"\u274c {escape_html(str(e))}",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(
                    "Failed to resolve A2A agent card",
                    url=url,
                    error=str(e),
                )
                await update.message.reply_text(
                    t("a2a.resolve_failed", lang,
                      error=escape_html(str(e)[:500])),
                    parse_mode="HTML",
                )
            return

        # /agents remove <alias>
        if action == "remove" and len(parts) >= 3:
            alias = parts[2]
            if await registry.unregister(user_id, alias):
                await client_manager.clear_cache()
                await update.message.reply_text(
                    t("a2a.agent_removed", lang,
                      alias=escape_html(alias)),
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    t("a2a.agent_not_exists", lang,
                      alias=escape_html(alias)),
                    parse_mode="HTML",
                )
            return

        # Unknown sub-command
        await update.message.reply_text(
            t("a2a.agents_usage", lang),
            parse_mode="HTML",
        )

    # ---- Search handler ----

    async def agentic_search(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Search conversation history.

        /search <query> — search past conversations
        """
        if not update.message or not update.message.text:
            return

        parts = update.message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await update.message.reply_text(
                "<b>Usage:</b> <code>/search &lt;query&gt;</code>\n\n"
                "Search your past conversations by keyword.",
                parse_mode="HTML",
            )
            return

        search_query = parts[1].strip()
        user_id = update.effective_user.id
        page_size = 5

        db_manager = context.bot_data.get("db_manager")
        if not db_manager:
            await update.message.reply_text(
                "Database is not available for search."
            )
            return

        from ..storage.repositories import HistoryRepository

        history_repo = HistoryRepository(db_manager)

        total_count = await history_repo.count_search_results(user_id, search_query)
        if total_count == 0:
            await update.message.reply_text(
                f"\U0001f50d No results found for "
                f"<code>{escape_html(search_query)}</code>.",
                parse_mode="HTML",
            )
            return

        results = await history_repo.search_messages(
            user_id, search_query, limit=page_size, offset=0
        )

        total_pages = max(1, (total_count + page_size - 1) // page_size)

        # Format results
        lines = [
            f"\U0001f50d <b>Search:</b> <code>{escape_html(search_query)}</code>"
            f" (page 1/{total_pages}, {total_count} results)\n"
        ]
        for r in results:
            ts = r.get("timestamp", "")
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%Y-%m-%d %H:%M")
            prompt_snippet = escape_html(r.get("prompt_snippet", "")[:80])
            lines.append(f"\u2022 <i>{ts}</i>\n  {prompt_snippet}")

        # Pagination keyboard (only if more than one page)
        reply_markup = None
        if total_pages > 1:
            buttons = [
                InlineKeyboardButton(
                    "1/" + str(total_pages),
                    callback_data=f"search_page:{search_query}:0",
                ),
                InlineKeyboardButton(
                    "\u27a1\ufe0f Next",
                    callback_data=f"search_page:{search_query}:1",
                ),
            ]
            reply_markup = InlineKeyboardMarkup([buttons])

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    # ---- Team collaboration handlers ----

    async def agentic_team(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Team collaboration commands.

        /team create <name>          — create a team
        /team invite <user_id>       — invite a member
        /team list                   — list your teams
        /team projects               — list shared projects
        /team share <project_path>   — share a project with team
        """
        if not update.message or not update.message.text:
            return

        parts = update.message.text.split()
        user_id = update.effective_user.id

        if len(parts) < 2:
            await update.message.reply_text(
                "\U0001f465 <b>Team Commands</b>\n\n"
                "<code>/team create &lt;name&gt;</code> — create a team\n"
                "<code>/team invite &lt;user_id&gt;</code> — invite a member\n"
                "<code>/team list</code> — list your teams\n"
                "<code>/team projects</code> — list shared projects\n"
                "<code>/team share &lt;project_path&gt;</code> — share a project",
                parse_mode="HTML",
            )
            return

        collaboration_manager = context.bot_data.get("collaboration_manager")
        if not collaboration_manager:
            await update.message.reply_text(
                "Team collaboration is not configured. "
                "Ensure database is available."
            )
            return

        action = parts[1].lower()

        if action == "create":
            if len(parts) < 3:
                await update.message.reply_text(
                    "<b>Usage:</b> <code>/team create &lt;name&gt;</code>",
                    parse_mode="HTML",
                )
                return
            team_name = " ".join(parts[2:])
            team_id = await collaboration_manager.create_team(team_name, user_id)
            await update.message.reply_text(
                f"\u2705 Team <b>{escape_html(team_name)}</b> created.\n"
                f"ID: <code>{escape_html(team_id[:12])}...</code>\n\n"
                f"Invite members with:\n"
                f"<code>/team invite &lt;user_id&gt;</code>",
                parse_mode="HTML",
            )

        elif action == "invite":
            if len(parts) < 3:
                await update.message.reply_text(
                    "<b>Usage:</b> <code>/team invite &lt;user_id&gt;</code>",
                    parse_mode="HTML",
                )
                return
            try:
                target_user_id = int(parts[2])
            except ValueError:
                await update.message.reply_text(
                    "Invalid user ID. Must be a number.",
                )
                return

            # Find user's teams — use the first one they created
            teams = await collaboration_manager.get_user_teams(user_id)
            if not teams:
                await update.message.reply_text(
                    "You don't belong to any teams. "
                    "Create one first with <code>/team create &lt;name&gt;</code>.",
                    parse_mode="HTML",
                )
                return

            team = teams[0]  # Use the most recent team
            success = await collaboration_manager.invite_member(
                team.team_id, target_user_id, user_id
            )
            if success:
                await update.message.reply_text(
                    f"\u2705 User <code>{target_user_id}</code> added to "
                    f"team <b>{escape_html(team.name)}</b>.",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    "Failed to add member. You may not have permission, "
                    "or the user is already a member.",
                )

        elif action == "list":
            teams = await collaboration_manager.get_user_teams(user_id)
            if not teams:
                await update.message.reply_text(
                    "\U0001f465 You don't belong to any teams.\n"
                    "Create one: <code>/team create &lt;name&gt;</code>",
                    parse_mode="HTML",
                )
                return

            lines = ["\U0001f465 <b>Your Teams</b>\n"]
            for t in teams:
                members = await collaboration_manager.get_team_members(t.team_id)
                lines.append(
                    f"\u2022 <b>{escape_html(t.name)}</b> "
                    f"({len(members)} members)\n"
                    f"  ID: <code>{escape_html(t.team_id[:12])}...</code>"
                )
            await update.message.reply_text(
                "\n".join(lines), parse_mode="HTML"
            )

        elif action == "projects":
            teams = await collaboration_manager.get_user_teams(user_id)
            if not teams:
                await update.message.reply_text(
                    "You don't belong to any teams.",
                )
                return

            lines = ["\U0001f4c2 <b>Shared Projects</b>\n"]
            found = False
            for t in teams:
                projects = await collaboration_manager.get_shared_projects(t.team_id)
                if projects:
                    found = True
                    lines.append(f"\n<b>{escape_html(t.name)}</b>:")
                    for p in projects:
                        lines.append(
                            f"  \u2022 <code>{escape_html(p.project_path)}</code>"
                        )
            if not found:
                lines.append("<i>No shared projects yet.</i>")

            await update.message.reply_text(
                "\n".join(lines), parse_mode="HTML"
            )

        elif action == "share":
            if len(parts) < 3:
                await update.message.reply_text(
                    "<b>Usage:</b> <code>/team share &lt;project_path&gt;</code>",
                    parse_mode="HTML",
                )
                return

            project_path = parts[2]
            teams = await collaboration_manager.get_user_teams(user_id)
            if not teams:
                await update.message.reply_text(
                    "You don't belong to any teams.",
                )
                return

            team = teams[0]
            shared = await collaboration_manager.share_project(
                team.team_id, project_path, user_id
            )
            if shared:
                await update.message.reply_text(
                    f"\u2705 Project <code>{escape_html(project_path)}</code> "
                    f"shared with team <b>{escape_html(team.name)}</b>.\n"
                    f"Shared session: <code>{escape_html(shared.shared_session_id[:12])}...</code>",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    "Failed to share project. Check your team membership.",
                )

        else:
            await update.message.reply_text(
                "\U0001f465 <b>Unknown team action.</b>\n\n"
                "Available: create, invite, list, projects, share",
                parse_mode="HTML",
            )

    # ---- Confirmation & search callbacks for agentic mode ----

    async def _agentic_dangerous_confirm_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle dangerous_confirm: callbacks in agentic mode."""
        from .handlers.callback import handle_dangerous_confirm_callback

        query = update.callback_query
        await query.answer()
        data = query.data
        # Strip the "dangerous_confirm:" prefix
        _, param = data.split(":", 1)
        await handle_dangerous_confirm_callback(query, param, context)

    async def _agentic_search_page_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle search_page: callbacks in agentic mode."""
        from .handlers.callback import handle_search_page_callback

        query = update.callback_query
        await query.answer()
        data = query.data
        _, param = data.split(":", 1)
        await handle_search_page_callback(query, param, context)
