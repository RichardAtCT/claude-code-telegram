"""Discord bot client for Claude Code remote access.

Mirrors the Telegram bot's agentic mode: receives messages, sends them to
Claude via ClaudeIntegration, and streams back the response. Shares the
same core dependencies (storage, security, claude_integration) as the
Telegram bot.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import structlog

from ..claude.facade import ClaudeIntegration
from ..claude.sdk_integration import StreamUpdate
from ..config.settings import Settings
from ..security.rate_limiter import RateLimiter
from ..storage.facade import Storage

logger = structlog.get_logger()

# Lazy import discord to avoid ImportError when discord.py is not installed
_discord = None
_commands = None


def _ensure_discord() -> None:
    """Import discord.py lazily, raising a clear error if not installed."""
    global _discord, _commands
    if _discord is None:
        try:
            import discord
            import discord.ext.commands as commands

            _discord = discord
            _commands = commands
        except ImportError:
            raise ImportError(
                "discord.py is required for Discord integration. "
                "Install with: poetry install -E discord"
            )


# Discord message limit (leave buffer for formatting)
DISCORD_MAX_MESSAGE_LENGTH = 1900

# Tool name -> emoji mapping (shared with Telegram orchestrator)
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
    "WebFetch": "\U0001f310",
    "WebSearch": "\U0001f310",
}


def _tool_icon(name: str) -> str:
    """Return emoji for a tool, with a default wrench."""
    return _TOOL_ICONS.get(name, "\U0001f527")


def _chunk_text(text: str, limit: int = DISCORD_MAX_MESSAGE_LENGTH) -> List[str]:
    """Split text into chunks that fit Discord's message limit.

    Prefers splitting at newlines, then spaces, then hard cut.
    """
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Try to split at a newline within the limit
        split_pos = remaining.rfind("\n", 0, limit)
        if split_pos == -1 or split_pos < limit // 2:
            # Try splitting at a space
            split_pos = remaining.rfind(" ", 0, limit)
        if split_pos == -1 or split_pos < limit // 2:
            # Hard cut
            split_pos = limit

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip("\n")

    return chunks


class DiscordBot:
    """Discord bot that provides remote Claude Code access.

    Designed to run alongside the Telegram bot in the same asyncio loop.
    Uses shared ClaudeIntegration, Storage, and RateLimiter instances.
    """

    def __init__(self, settings: Settings, deps: Dict[str, Any]) -> None:
        _ensure_discord()
        self.settings = settings
        self.deps = deps
        self._active_requests: Dict[int, asyncio.Event] = {}

        # Per-user session state (mirrors Telegram's context.user_data)
        self._user_sessions: Dict[int, Dict[str, Any]] = {}

        # Set up intents
        intents = _discord.Intents.default()
        intents.message_content = True  # Required to read message text

        self._client = _discord.Client(intents=intents)
        self._setup_events()

    def _setup_events(self) -> None:
        """Register Discord event handlers."""

        @self._client.event
        async def on_ready() -> None:
            logger.info(
                "Discord bot connected",
                user=str(self._client.user),
                guilds=len(self._client.guilds),
            )

        @self._client.event
        async def on_message(message: Any) -> None:
            # Ignore own messages
            if message.author == self._client.user:
                return

            # Ignore bot messages
            if message.author.bot:
                return

            await self._handle_message(message)

    def _is_user_allowed(self, user_id: int) -> bool:
        """Check if a Discord user is allowed to use the bot."""
        allowed = self.settings.discord_allowed_users
        if not allowed:
            # No whitelist = allow all (dev mode behavior)
            return self.settings.development_mode
        return user_id in allowed

    def _is_guild_allowed(self, guild_id: Optional[int]) -> bool:
        """Check if a Discord guild is allowed."""
        allowed = self.settings.discord_allowed_guilds
        if not allowed:
            # No guild whitelist = allow all guilds
            return True
        if guild_id is None:
            # DMs are always allowed
            return True
        return guild_id in allowed

    def _should_respond(self, message: Any) -> bool:
        """Determine if the bot should respond to this message.

        In DMs: always respond.
        In guilds: only respond when mentioned or replied to.
        """
        # DMs
        if message.guild is None:
            return True

        # Check guild allowlist
        if not self._is_guild_allowed(message.guild.id):
            return False

        # In guilds, require mention or reply
        if self._client.user in message.mentions:
            return True

        # Check if replying to the bot's message
        if message.reference and message.reference.resolved:
            ref = message.reference.resolved
            if hasattr(ref, "author") and ref.author == self._client.user:
                return True

        return False

    def _get_user_state(self, user_id: int) -> Dict[str, Any]:
        """Get or create per-user session state."""
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = {
                "current_directory": self.settings.approved_directory,
                "claude_session_id": None,
                "force_new_session": False,
                "verbose_level": self.settings.verbose_level,
            }
        return self._user_sessions[user_id]

    async def _handle_message(self, message: Any) -> None:
        """Process an incoming Discord message."""
        if not self._should_respond(message):
            return

        user_id = message.author.id

        # Auth check
        if not self._is_user_allowed(user_id):
            logger.info("Discord: unauthorized user", user_id=user_id)
            await message.reply(
                "You are not authorized to use this bot.", mention_author=False
            )
            return

        # Extract text (strip bot mention if in guild)
        text = message.content
        if self._client.user and message.guild:
            text = text.replace(f"<@{self._client.user.id}>", "").strip()

        if not text:
            return

        # Handle commands
        if text.startswith("/"):
            await self._handle_command(message, text)
            return

        # Rate limit check
        rate_limiter: Optional[RateLimiter] = self.deps.get("rate_limiter")
        if rate_limiter:
            allowed, limit_message = await rate_limiter.check_rate_limit(user_id, 0.001)
            if not allowed:
                await message.reply(
                    f"\u23f1\ufe0f {limit_message}", mention_author=False
                )
                return

        logger.info(
            "Discord agentic message",
            user_id=user_id,
            message_length=len(text),
            guild=message.guild.id if message.guild else "DM",
        )

        claude_integration: Optional[ClaudeIntegration] = self.deps.get(
            "claude_integration"
        )
        if not claude_integration:
            await message.reply(
                "Claude integration not available. Check configuration.",
                mention_author=False,
            )
            return

        user_state = self._get_user_state(user_id)
        current_dir = user_state["current_directory"]
        session_id = user_state["claude_session_id"]
        force_new = user_state.get("force_new_session", False)
        verbose_level = user_state.get("verbose_level", 1)

        # Interrupt event for cancellation
        interrupt_event = asyncio.Event()
        self._active_requests[user_id] = interrupt_event

        # Send "Working..." and show typing
        progress_msg = await message.reply("Working...", mention_author=False)

        # Stream callback for verbose progress
        tool_log: List[Dict[str, Any]] = []
        start_time = time.time()
        last_update_time = 0.0

        async def on_stream(update: StreamUpdate) -> None:
            nonlocal last_update_time

            if interrupt_event.is_set():
                return

            now = time.time()
            # Throttle progress updates to avoid rate limiting
            if now - last_update_time < 2.0:
                return

            if verbose_level == 0:
                return

            if update.type == "tool_call" and update.tool_name:
                icon = _tool_icon(update.tool_name)
                tool_log.append({"name": update.tool_name, "time": now - start_time})

                elapsed = int(now - start_time)
                tool_names = " \u2192 ".join(
                    _tool_icon(t["name"]) + t["name"] for t in tool_log[-5:]
                )
                progress_text = f"Working... ({elapsed}s)\n{tool_names}"

                try:
                    await progress_msg.edit(content=progress_text)
                    last_update_time = now
                except Exception:
                    pass

        # Typing indicator
        typing_task = asyncio.create_task(self._typing_heartbeat(message.channel))

        success = True
        try:
            claude_response = await claude_integration.run_command(
                prompt=text,
                working_directory=current_dir,
                user_id=user_id,
                session_id=session_id,
                on_stream=on_stream,
                force_new=force_new,
                interrupt_event=interrupt_event,
            )

            if force_new:
                user_state["force_new_session"] = False

            user_state["claude_session_id"] = claude_response.session_id

            # Store interaction
            storage: Optional[Storage] = self.deps.get("storage")
            if storage:
                try:
                    await storage.save_claude_interaction(
                        user_id=user_id,
                        session_id=claude_response.session_id,
                        prompt=text,
                        response=claude_response,
                        ip_address=None,
                    )
                except Exception as e:
                    logger.warning("Failed to log Discord interaction", error=str(e))

            response_content = claude_response.content or ""
            if claude_response.interrupted:
                response_content += "\n\n_(Interrupted by user)_"

        except Exception as e:
            success = False
            logger.error(
                "Claude integration failed (Discord)",
                error=str(e),
                user_id=user_id,
            )
            response_content = f"Error: {e}"
        finally:
            typing_task.cancel()
            self._active_requests.pop(user_id, None)

        # Delete progress message
        try:
            await progress_msg.delete()
        except Exception:
            logger.debug("Failed to delete Discord progress message")

        # Send response chunks
        if not response_content.strip():
            response_content = "_(No response from Claude)_"

        chunks = _chunk_text(response_content)
        for i, chunk in enumerate(chunks):
            try:
                if i == 0:
                    await message.reply(chunk, mention_author=False)
                else:
                    await message.channel.send(chunk)
            except Exception as e:
                logger.error(
                    "Failed to send Discord message chunk",
                    error=str(e),
                    chunk_index=i,
                )

    async def _handle_command(self, message: Any, text: str) -> None:
        """Handle slash-like commands in Discord."""
        user_state = self._get_user_state(message.author.id)

        parts = text.split(maxsplit=1)
        command = parts[0].lower()

        if command == "/new":
            user_state["force_new_session"] = True
            user_state["claude_session_id"] = None
            await message.reply(
                "Session cleared. Next message starts a fresh conversation.",
                mention_author=False,
            )

        elif command == "/status":
            session_id = user_state.get("claude_session_id")
            current_dir = user_state.get("current_directory")
            verbose = user_state.get("verbose_level", 1)
            status_text = (
                f"**Status**\n"
                f"Session: `{session_id or 'None'}`\n"
                f"Directory: `{current_dir}`\n"
                f"Verbose: `{verbose}`"
            )
            await message.reply(status_text, mention_author=False)

        elif command == "/verbose":
            if len(parts) > 1 and parts[1].strip().isdigit():
                level = int(parts[1].strip())
                if 0 <= level <= 2:
                    user_state["verbose_level"] = level
                    await message.reply(
                        f"Verbose level set to {level}.", mention_author=False
                    )
                    return
            await message.reply(
                "Usage: `/verbose 0|1|2`", mention_author=False
            )

        elif command == "/stop":
            interrupt = self._active_requests.get(message.author.id)
            if interrupt:
                interrupt.set()
                await message.reply(
                    "Stopping current request...", mention_author=False
                )
            else:
                await message.reply(
                    "No active request to stop.", mention_author=False
                )

        else:
            await message.reply(
                "Available commands: `/new`, `/status`, `/verbose`, `/stop`",
                mention_author=False,
            )

    async def _typing_heartbeat(self, channel: Any) -> None:
        """Keep typing indicator alive until cancelled."""
        try:
            while True:
                await channel.trigger_typing()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    async def start(self) -> None:
        """Start the Discord bot (async, non-blocking for asyncio.gather)."""
        token = self.settings.discord_token_str
        if not token:
            raise ValueError("Discord bot token not configured")

        logger.info("Starting Discord bot")
        await self._client.start(token)

    async def stop(self) -> None:
        """Gracefully stop the Discord bot."""
        logger.info("Stopping Discord bot")
        await self._client.close()
