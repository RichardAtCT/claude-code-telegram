"""Claude Code Python SDK integration."""

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    Message,
    PermissionResultAllow,
    PermissionResultDeny,
    ProcessError,
    ResultMessage,
    ToolPermissionContext,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk._errors import MessageParseError
from claude_agent_sdk._internal.message_parser import parse_message
from claude_agent_sdk.types import StreamEvent

from ..config.settings import Settings
from ..security.validators import SecurityValidator
from .exceptions import (
    ClaudeMCPError,
    ClaudeParsingError,
    ClaudeProcessError,
    ClaudeTimeoutError,
)
from .monitor import _is_claude_internal_path, check_bash_directory_boundary

logger = structlog.get_logger()


@dataclass
class ClaudeResponse:
    """Response from Claude Code SDK."""

    content: str
    session_id: str
    cost: float
    duration_ms: int
    num_turns: int
    is_error: bool = False
    error_type: Optional[str] = None
    tools_used: List[Dict[str, Any]] = field(default_factory=list)
    interrupted: bool = False


@dataclass
class StreamUpdate:
    """Streaming update from Claude SDK."""

    type: str  # 'assistant', 'user', 'system', 'result', 'stream_delta', 'thinking'
    content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None


class ClaudeSDKManager:
    """Manage Claude Code SDK integration.

    Keeps a persistent ClaudeSDKClient alive per session so that follow-up
    messages can be injected via interrupt() + query() without creating a
    new subprocess.
    """

    def __init__(
        self,
        config: Settings,
        security_validator: Optional[SecurityValidator] = None,
    ):
        """Initialize SDK manager with configuration."""
        self.config = config
        self.security_validator = security_validator

        if config.anthropic_api_key_str:
            os.environ["ANTHROPIC_API_KEY"] = config.anthropic_api_key_str
            logger.info("Using provided API key for Claude SDK authentication")
        else:
            logger.info("No API key provided, using existing Claude CLI authentication")

        self._active_client: Optional[ClaudeSDKClient] = None
        self._is_processing = False

    @property
    def is_processing(self) -> bool:
        """Whether a command is currently being processed."""
        return self._is_processing

    async def interrupt(self) -> bool:
        """Send interrupt signal to the running Claude command (like Ctrl+C).

        Returns True if there was an active client to interrupt.
        """
        client = self._active_client
        if client is None:
            return False
        logger.info("Sending interrupt to active Claude client")
        try:
            await client.interrupt()
            return True
        except Exception as e:
            logger.debug("Interrupt signal failed", error=str(e))
            return False

    async def abort(self) -> bool:
        """Forcefully abort the running command (interrupt + kill subprocess)."""
        client = self._active_client
        if client is None:
            return False
        logger.info("Aborting active Claude client")
        try:
            await client.interrupt()
        except Exception as e:
            logger.debug("Interrupt signal failed (may already be done)", error=str(e))
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning("Error disconnecting client during abort", error=str(e))
        self._active_client = None
        return True

    async def execute_command(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        stream_callback: Optional[Callable[[StreamUpdate], None]] = None,
    ) -> ClaudeResponse:
        """Execute Claude Code command via SDK."""
        start_time = asyncio.get_event_loop().time()
        self._is_processing = True

        logger.info(
            "Starting Claude SDK command",
            working_directory=str(working_directory),
            session_id=session_id,
            continue_session=continue_session,
        )

        try:
            stderr_lines: List[str] = []

            def _stderr_callback(line: str) -> None:
                stderr_lines.append(line)
                logger.debug("Claude CLI stderr", line=line)

            options = ClaudeAgentOptions(
                max_turns=self.config.claude_max_turns,
                model=self.config.claude_model or None,
                cwd=str(working_directory),
                cli_path=self.config.claude_cli_path or None,
                include_partial_messages=stream_callback is not None,
                permission_mode="bypassPermissions",
                setting_sources=["project"],
                stderr=_stderr_callback,
            )

            if self.config.enable_mcp and self.config.mcp_config_path:
                options.mcp_servers = self._load_mcp_config(self.config.mcp_config_path)
                logger.info(
                    "MCP servers configured",
                    mcp_config_path=str(self.config.mcp_config_path),
                )

            if session_id and continue_session:
                options.resume = session_id
                logger.info("Resuming previous session", session_id=session_id)

            messages: List[Message] = []
            interrupted = False

            async def _run_client() -> None:
                nonlocal interrupted
                client = ClaudeSDKClient(options)
                self._active_client = client
                try:
                    await client.connect()
                    await client.query(prompt)

                    async for raw_data in client._query.receive_messages():
                        try:
                            message = parse_message(raw_data)
                        except MessageParseError as e:
                            logger.debug(
                                "Skipping unparseable message", error=str(e)
                            )
                            continue

                        messages.append(message)

                        if isinstance(message, ResultMessage):
                            break

                        if stream_callback:
                            try:
                                await self._handle_stream_message(
                                    message, stream_callback
                                )
                            except Exception as callback_error:
                                logger.warning(
                                    "Stream callback failed",
                                    error=str(callback_error),
                                    error_type=type(callback_error).__name__,
                                )
                except asyncio.CancelledError:
                    interrupted = True
                    logger.info("Claude command was interrupted/cancelled")
                finally:
                    self._active_client = None
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

            await asyncio.wait_for(
                _run_client(),
                timeout=self.config.claude_timeout_seconds,
            )

            # Extract results from messages
            cost = 0.0
            tools_used: List[Dict[str, Any]] = []
            claude_session_id = None
            result_content = None
            for message in messages:
                if isinstance(message, ResultMessage):
                    cost = getattr(message, "total_cost_usd", 0.0) or 0.0
                    claude_session_id = getattr(message, "session_id", None)
                    result_content = getattr(message, "result", None)
                    current_time = asyncio.get_event_loop().time()
                    for msg in messages:
                        if isinstance(msg, AssistantMessage):
                            msg_content = getattr(msg, "content", [])
                            if msg_content and isinstance(msg_content, list):
                                for block in msg_content:
                                    if isinstance(block, ToolUseBlock):
                                        tools_used.append(
                                            {
                                                "name": getattr(
                                                    block, "name", "unknown"
                                                ),
                                                "timestamp": current_time,
                                                "input": getattr(block, "input", {}),
                                            }
                                        )
                    break

            if not claude_session_id:
                for message in messages:
                    msg_session_id = getattr(message, "session_id", None)
                    if msg_session_id and not isinstance(message, ResultMessage):
                        claude_session_id = msg_session_id
                        logger.info(
                            "Got session ID from stream event (fallback)",
                            session_id=claude_session_id,
                        )
                        break

            duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            final_session_id = claude_session_id or session_id or ""

            if claude_session_id and claude_session_id != session_id:
                logger.info(
                    "Got session ID from Claude",
                    claude_session_id=claude_session_id,
                    previous_session_id=session_id,
                )

            if result_content is not None:
                content = re.sub(
                    r'\[ThinkingBlock\(thinking=\'.*?\',\s*signature=\'.*?\'\)\]\s*',
                    '', result_content, flags=re.DOTALL
                )
                content = content.strip()
            else:
                # Use only the LAST AssistantMessage's text content.
                # Earlier assistant messages contain intermediate reasoning
                # that was already shown to the user via 💬 messages.
                content_parts = []
                for msg in reversed(messages):
                    if isinstance(msg, AssistantMessage):
                        msg_content = getattr(msg, "content", [])
                        if msg_content and isinstance(msg_content, list):
                            for block in msg_content:
                                if hasattr(block, "text"):
                                    content_parts.append(block.text)
                        elif msg_content:
                            content_parts.append(str(msg_content))
                        if content_parts:
                            break  # Stop at the last assistant message with text
                content = "\n".join(content_parts)

            return ClaudeResponse(
                content=content,
                session_id=final_session_id,
                cost=cost,
                duration_ms=duration_ms,
                num_turns=len(
                    [
                        m
                        for m in messages
                        if isinstance(m, (UserMessage, AssistantMessage))
                    ]
                ),
                tools_used=tools_used,
                interrupted=interrupted,
            )

        except asyncio.TimeoutError:
            logger.error(
                "Claude SDK command timed out",
                timeout_seconds=self.config.claude_timeout_seconds,
            )
            raise ClaudeTimeoutError(
                f"Claude SDK timed out after {self.config.claude_timeout_seconds}s"
            )

        except CLINotFoundError as e:
            logger.error("Claude CLI not found", error=str(e))
            error_msg = (
                "Claude Code not found. Please ensure Claude is installed:\n"
                "  npm install -g @anthropic-ai/claude-code\n\n"
                "If already installed, try one of these:\n"
                "  1. Add Claude to your PATH\n"
                "  2. Create a symlink: ln -s $(which claude) /usr/local/bin/claude\n"
                "  3. Set CLAUDE_CLI_PATH environment variable"
            )
            raise ClaudeProcessError(error_msg)

        except ProcessError as e:
            error_str = str(e)
            captured_stderr = "\n".join(stderr_lines[-20:]) if stderr_lines else ""
            if captured_stderr:
                error_str = f"{error_str}\nStderr: {captured_stderr}"
            logger.error(
                "Claude process failed",
                error=error_str,
                exit_code=getattr(e, "exit_code", None),
                stderr=captured_stderr or None,
            )
            if "mcp" in error_str.lower():
                raise ClaudeMCPError(f"MCP server error: {error_str}")
            raise ClaudeProcessError(f"Claude process error: {error_str}")

        except CLIConnectionError as e:
            error_str = str(e)
            logger.error("Claude connection error", error=error_str)
            if "mcp" in error_str.lower() or "server" in error_str.lower():
                raise ClaudeMCPError(f"MCP server connection failed: {error_str}")
            raise ClaudeProcessError(f"Failed to connect to Claude: {error_str}")

        except CLIJSONDecodeError as e:
            logger.error("Claude SDK JSON decode error", error=str(e))
            raise ClaudeParsingError(f"Failed to decode Claude response: {str(e)}")

        except ClaudeSDKError as e:
            logger.error("Claude SDK error", error=str(e))
            raise ClaudeProcessError(f"Claude SDK error: {str(e)}")

        except Exception as e:
            exceptions = getattr(e, "exceptions", None)
            if exceptions is not None:
                logger.error(
                    "Task group error in Claude SDK",
                    error=str(e),
                    error_type=type(e).__name__,
                    exception_count=len(exceptions),
                    exceptions=[str(ex) for ex in exceptions[:3]],
                )
                raise ClaudeProcessError(
                    f"Claude SDK task error: {exceptions[0] if exceptions else e}"
                )

            logger.error(
                "Unexpected error in Claude SDK",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ClaudeProcessError(f"Unexpected error: {str(e)}")

        finally:
            self._is_processing = False

    async def _handle_stream_message(
        self, message: Message, stream_callback: Callable[[StreamUpdate], None]
    ) -> None:
        """Handle streaming message from claude-agent-sdk."""
        try:
            if isinstance(message, AssistantMessage):
                content = getattr(message, "content", [])
                text_parts = []
                thinking_parts = []
                tool_calls = []

                if content and isinstance(content, list):
                    for block in content:
                        if isinstance(block, ToolUseBlock):
                            tool_calls.append(
                                {
                                    "name": getattr(block, "name", "unknown"),
                                    "input": getattr(block, "input", {}),
                                    "id": getattr(block, "id", None),
                                }
                            )
                        elif hasattr(block, "text"):
                            text_parts.append(block.text)
                        elif hasattr(block, "thinking"):
                            thinking = getattr(block, "thinking", "")
                            if thinking:
                                thinking_parts.append(thinking)

                if thinking_parts:
                    thinking_update = StreamUpdate(
                        type="thinking",
                        content="\n".join(thinking_parts),
                    )
                    await stream_callback(thinking_update)

                if text_parts or tool_calls:
                    update = StreamUpdate(
                        type="assistant",
                        content=("\n".join(text_parts) if text_parts else None),
                        tool_calls=tool_calls if tool_calls else None,
                    )
                    await stream_callback(update)
                elif content and not thinking_parts:
                    update = StreamUpdate(
                        type="assistant",
                        content=str(content),
                    )
                    await stream_callback(update)

            elif isinstance(message, StreamEvent):
                event = message.event or {}
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            update = StreamUpdate(
                                type="stream_delta",
                                content=text,
                            )
                            await stream_callback(update)

            elif isinstance(message, UserMessage):
                content = getattr(message, "content", "")
                raw_content = getattr(message, "content", None)
                if isinstance(raw_content, list):
                    for block in raw_content:
                        if hasattr(block, "content") and hasattr(block, "tool_use_id"):
                            result_text = str(getattr(block, "content", ""))
                            update = StreamUpdate(
                                type="tool_result",
                                content=result_text,
                            )
                            await stream_callback(update)
                elif content:
                    update = StreamUpdate(
                        type="user",
                        content=content,
                    )
                    await stream_callback(update)

        except Exception as e:
            logger.warning("Stream callback failed", error=str(e))

    def _load_mcp_config(self, config_path: Path) -> Dict[str, Any]:
        """Load MCP server configuration from a JSON file."""
        import json

        try:
            with open(config_path) as f:
                config_data = json.load(f)
            return config_data.get("mcpServers", {})
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                "Failed to load MCP config", path=str(config_path), error=str(e)
            )
            return {}
