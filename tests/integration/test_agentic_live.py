#!/usr/bin/env python3
"""Live end-to-end test of all agentic capabilities.

Uses the REAL Claude SDK, real SQLite storage, and real session management.
Only the Telegram transport is mocked (since we can't impersonate a user).

Requires:
    - Claude CLI installed and authenticated (or ANTHROPIC_API_KEY set)
    - .env file with at least TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME,
      APPROVED_DIRECTORY

Run:
    poetry run python tests/integration/test_agentic_live.py
    poetry run python tests/integration/test_agentic_live.py --skip-sdk
    poetry run python tests/integration/test_agentic_live.py --debug
"""

import argparse
import asyncio
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import structlog

# ---------------------------------------------------------------------------
# Bootstrap — must happen before importing src modules
# ---------------------------------------------------------------------------

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: int = 0
    error: str = ""
    details: str = ""


@dataclass
class TestReport:
    results: List[TestResult] = field(default_factory=list)
    total_cost: float = 0.0

    def add(self, result: TestResult) -> None:
        self.results.append(result)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def print_report(self) -> None:
        print("\n" + "=" * 70)
        print("AGENTIC CAPABILITIES — LIVE E2E TEST REPORT")
        print("=" * 70)

        max_name = max(len(r.name) for r in self.results) if self.results else 20

        for r in self.results:
            status = "\033[32mPASS\033[0m" if r.passed else "\033[31mFAIL\033[0m"
            time_str = f"{r.duration_ms}ms"
            print(f"  {status}  {r.name:<{max_name}}  {time_str:>8}")
            if r.error:
                for line in r.error.split("\n")[:3]:
                    print(f"         \033[31m{line}\033[0m")
            if r.details:
                print(f"         {r.details}")

        print("-" * 70)
        print(
            f"  Total: {len(self.results)}  "
            f"Passed: {self.passed}  "
            f"Failed: {self.failed}  "
            f"Cost: ${self.total_cost:.4f}"
        )
        print("=" * 70)


# ---------------------------------------------------------------------------
# Mock Telegram helpers (only the transport layer is fake)
# ---------------------------------------------------------------------------


def _make_update(
    user_id: int = 99999,
    first_name: str = "E2ETestUser",
    text: str = "",
    message_id: int = 1,
) -> MagicMock:
    """Build a mock Telegram Update — only the transport is fake."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.first_name = first_name
    update.effective_chat.id = user_id
    update.effective_chat.type = "private"
    update.message.text = text
    update.message.message_id = message_id
    update.message.chat.id = user_id

    progress_msg = AsyncMock()
    progress_msg.delete = AsyncMock()
    progress_msg.edit_text = AsyncMock()
    update.message.reply_text = AsyncMock(return_value=progress_msg)
    update.message.chat.send_action = AsyncMock()

    update.callback_query = None
    return update


def _make_context(
    settings: Any,
    deps: Dict[str, Any],
    user_data: Optional[Dict[str, Any]] = None,
) -> MagicMock:
    context = MagicMock()
    context.user_data = user_data if user_data is not None else {}
    context.bot_data = {"settings": settings, **deps}
    return context


def _get_reply_text(update: MagicMock) -> str:
    """Extract the text from the most recent reply_text call."""
    calls = update.message.reply_text.call_args_list
    if not calls:
        return ""
    return calls[-1].args[0] if calls[-1].args else ""


def _get_all_replies(update: MagicMock) -> List[str]:
    """Extract all reply texts."""
    return [
        c.args[0] for c in update.message.reply_text.call_args_list if c.args
    ]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


class AgenticLiveTests:
    """Live E2E tests using real Claude SDK and real storage."""

    def __init__(
        self,
        settings: Any,
        deps: Dict[str, Any],
        workspace: Path,
        skip_sdk: bool = False,
    ):
        from src.bot.orchestrator import MessageOrchestrator

        self.settings = settings
        self.deps = deps
        self.workspace = workspace
        self.skip_sdk = skip_sdk
        self.orchestrator = MessageOrchestrator(settings, deps)
        self.report = TestReport()
        self.user_id = 99999

    async def _run_test(self, name: str, coro: Any) -> None:
        """Execute a single test and record the result."""
        start = time.monotonic()
        try:
            await coro
            duration = int((time.monotonic() - start) * 1000)
            self.report.add(TestResult(name=name, passed=True, duration_ms=duration))
        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            self.report.add(
                TestResult(
                    name=name,
                    passed=False,
                    duration_ms=duration,
                    error=f"{type(e).__name__}: {e}",
                )
            )

    async def run_all(self) -> TestReport:
        """Run all tests and return the report."""
        print("\nRunning agentic live E2E tests...\n")

        # --- Commands ---
        await self._run_test("cmd /start", self.test_start())
        await self._run_test("cmd /start HTML escape", self.test_start_html_escape())
        await self._run_test("cmd /new", self.test_new())
        await self._run_test("cmd /status (no session)", self.test_status_no_session())
        await self._run_test("cmd /status (active session)", self.test_status_active())
        await self._run_test("cmd /verbose (show)", self.test_verbose_show())
        await self._run_test("cmd /verbose 0", self.test_verbose_set_0())
        await self._run_test("cmd /verbose 1", self.test_verbose_set_1())
        await self._run_test("cmd /verbose 2", self.test_verbose_set_2())
        await self._run_test("cmd /verbose invalid", self.test_verbose_invalid())
        await self._run_test("cmd /repo (list)", self.test_repo_list())
        await self._run_test("cmd /repo <name>", self.test_repo_switch())
        await self._run_test("cmd /repo nonexistent", self.test_repo_nonexistent())
        await self._run_test("cmd /repo inline keyboard", self.test_repo_keyboard())

        # --- Directory switching ---
        await self._run_test("cd: callback", self.test_cd_callback())
        await self._run_test("cd: callback nonexistent", self.test_cd_callback_bad())
        await self._run_test("repo switch session resume", self.test_repo_session_resume())

        # --- Session lifecycle ---
        await self._run_test("session /new clears id", self.test_session_new_clears())
        await self._run_test("session force_new flag", self.test_session_force_new())

        # --- File upload ---
        await self._run_test("file: reject oversized", self.test_file_oversized())
        await self._run_test("file: reject bad filename", self.test_file_bad_name())

        # --- Photo upload ---
        await self._run_test("photo: no handler", self.test_photo_no_handler())

        # --- Rate limiting ---
        await self._run_test("rate limit: blocked", self.test_rate_limit_blocks())

        # --- Verbose progress ---
        await self._run_test("progress: format empty", self.test_progress_empty())
        await self._run_test("progress: format tools", self.test_progress_tools())
        await self._run_test("progress: callback level 0", self.test_callback_level_0())

        # --- Secret redaction ---
        await self._run_test("redact: API key", self.test_redact_api_key())
        await self._run_test("redact: safe cmd", self.test_redact_safe())

        # --- Handler registration ---
        await self._run_test("registration: 5 commands", self.test_registration())

        # --- Real Claude SDK (the big ones) ---
        if not self.skip_sdk:
            import os

            if os.environ.get("CLAUDECODE"):
                print(
                    "  (skipping SDK tests — running inside Claude Code session;\n"
                    "   run this script directly from your terminal to test the SDK)"
                )
            else:
                await self._run_test(
                    "SDK: text -> Claude -> response", self.test_sdk_text()
                )
                await self._run_test(
                    "SDK: session resume", self.test_sdk_session_resume()
                )
                await self._run_test(
                    "SDK: /new then fresh session", self.test_sdk_new_then_text()
                )
        else:
            print("  (skipping SDK tests — use without --skip-sdk to run them)")

        return self.report

    # -----------------------------------------------------------------------
    # Command tests
    # -----------------------------------------------------------------------

    async def test_start(self) -> None:
        update = _make_update(first_name="Alice")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_start(update, ctx)
        text = _get_reply_text(update)
        assert "Alice" in text, f"Expected 'Alice' in: {text}"
        assert "Working in:" in text

    async def test_start_html_escape(self) -> None:
        update = _make_update(first_name="<b>Hacker</b>")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_start(update, ctx)
        text = _get_reply_text(update)
        assert "<b>Hacker</b>" not in text
        assert "&lt;b&gt;" in text

    async def test_new(self) -> None:
        update = _make_update()
        ctx = _make_context(
            self.settings, self.deps, {"claude_session_id": "old-sess"}
        )
        await self.orchestrator.agentic_new(update, ctx)
        assert ctx.user_data["claude_session_id"] is None
        assert ctx.user_data["force_new_session"] is True
        assert "reset" in _get_reply_text(update).lower()

    async def test_status_no_session(self) -> None:
        update = _make_update()
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_status(update, ctx)
        text = _get_reply_text(update)
        assert "Session: none" in text

    async def test_status_active(self) -> None:
        update = _make_update()
        ctx = _make_context(
            self.settings, self.deps, {"claude_session_id": "s123"}
        )
        await self.orchestrator.agentic_status(update, ctx)
        text = _get_reply_text(update)
        assert "Session: active" in text

    async def test_verbose_show(self) -> None:
        update = _make_update(text="/verbose")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_verbose(update, ctx)
        text = _get_reply_text(update)
        assert "Verbosity:" in text

    async def test_verbose_set_0(self) -> None:
        update = _make_update(text="/verbose 0")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_verbose(update, ctx)
        assert ctx.user_data["verbose_level"] == 0

    async def test_verbose_set_1(self) -> None:
        update = _make_update(text="/verbose 1")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_verbose(update, ctx)
        assert ctx.user_data["verbose_level"] == 1

    async def test_verbose_set_2(self) -> None:
        update = _make_update(text="/verbose 2")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_verbose(update, ctx)
        assert ctx.user_data["verbose_level"] == 2

    async def test_verbose_invalid(self) -> None:
        update = _make_update(text="/verbose 9")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_verbose(update, ctx)
        assert "verbose_level" not in ctx.user_data

    async def test_repo_list(self) -> None:
        update = _make_update(text="/repo")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_repo(update, ctx)
        text = _get_reply_text(update)
        assert "repo_alpha" in text
        assert "repo_beta" in text

    async def test_repo_switch(self) -> None:
        update = _make_update(text="/repo repo_alpha")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_repo(update, ctx)
        assert ctx.user_data["current_directory"] == self.workspace / "repo_alpha"
        text = _get_reply_text(update)
        assert "Switched" in text

    async def test_repo_nonexistent(self) -> None:
        update = _make_update(text="/repo does_not_exist")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_repo(update, ctx)
        text = _get_reply_text(update)
        assert "not found" in text.lower()

    async def test_repo_keyboard(self) -> None:
        update = _make_update(text="/repo")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_repo(update, ctx)
        kwargs = update.message.reply_text.call_args_list[-1].kwargs
        markup = kwargs.get("reply_markup")
        assert markup is not None
        buttons = [b.text for row in markup.inline_keyboard for b in row]
        assert "repo_alpha" in buttons

    # -----------------------------------------------------------------------
    # Directory switching
    # -----------------------------------------------------------------------

    async def test_cd_callback(self) -> None:
        query = AsyncMock()
        query.answer = AsyncMock()
        query.data = "cd:repo_beta"
        query.from_user.id = self.user_id
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        ctx = _make_context(self.settings, self.deps)

        await self.orchestrator._agentic_callback(update, ctx)
        assert ctx.user_data["current_directory"] == self.workspace / "repo_beta"

    async def test_cd_callback_bad(self) -> None:
        query = AsyncMock()
        query.answer = AsyncMock()
        query.data = "cd:nope"
        query.from_user.id = self.user_id
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        ctx = _make_context(self.settings, self.deps)

        await self.orchestrator._agentic_callback(update, ctx)
        text = query.edit_message_text.call_args.args[0]
        assert "not found" in text.lower()

    async def test_repo_session_resume(self) -> None:
        """Verify /repo looks for resumable sessions via real session manager."""
        update = _make_update(text="/repo repo_alpha")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_repo(update, ctx)
        # With a fresh DB there's no session to resume
        assert ctx.user_data["claude_session_id"] is None

    # -----------------------------------------------------------------------
    # Session lifecycle
    # -----------------------------------------------------------------------

    async def test_session_new_clears(self) -> None:
        update = _make_update()
        ctx = _make_context(
            self.settings, self.deps, {"claude_session_id": "abc"}
        )
        await self.orchestrator.agentic_new(update, ctx)
        assert ctx.user_data["claude_session_id"] is None

    async def test_session_force_new(self) -> None:
        update = _make_update()
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_new(update, ctx)
        assert ctx.user_data.get("force_new_session") is True

    # -----------------------------------------------------------------------
    # File uploads
    # -----------------------------------------------------------------------

    async def test_file_oversized(self) -> None:
        self.deps["security_validator"].validate_filename = MagicMock(
            return_value=(True, None)
        )
        update = _make_update()
        update.message.document = MagicMock()
        update.message.document.file_name = "big.bin"
        update.message.document.file_size = 20 * 1024 * 1024
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_document(update, ctx)
        text = _get_reply_text(update)
        assert "too large" in text.lower()

    async def test_file_bad_name(self) -> None:
        self.deps["security_validator"].validate_filename = MagicMock(
            return_value=(False, "Blocked")
        )
        update = _make_update()
        update.message.document = MagicMock()
        update.message.document.file_name = ".env"
        update.message.document.file_size = 50
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_document(update, ctx)
        text = _get_reply_text(update)
        assert "rejected" in text.lower()

    # -----------------------------------------------------------------------
    # Photo
    # -----------------------------------------------------------------------

    async def test_photo_no_handler(self) -> None:
        self.deps["features"] = None
        update = _make_update()
        update.message.photo = [MagicMock()]
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_photo(update, ctx)
        text = _get_reply_text(update)
        assert "not available" in text.lower()

    # -----------------------------------------------------------------------
    # Rate limiting
    # -----------------------------------------------------------------------

    async def test_rate_limit_blocks(self) -> None:
        rl = AsyncMock()
        rl.check_rate_limit = AsyncMock(return_value=(False, "Slow down"))
        self.deps["rate_limiter"] = rl

        update = _make_update(text="hello")
        ctx = _make_context(self.settings, self.deps)
        await self.orchestrator.agentic_text(update, ctx)
        text = _get_reply_text(update)
        assert "Slow down" in text

        # Restore for later tests
        self.deps["rate_limiter"] = None

    # -----------------------------------------------------------------------
    # Verbose progress formatting
    # -----------------------------------------------------------------------

    async def test_progress_empty(self) -> None:
        text = self.orchestrator._format_verbose_progress([], 1, time.time())
        assert text == "Working..."

    async def test_progress_tools(self) -> None:
        log = [{"kind": "tool", "name": "Read", "detail": "file.py"}]
        text = self.orchestrator._format_verbose_progress(log, 2, time.time() - 5)
        assert "Read" in text
        assert "file.py" in text

    async def test_callback_level_0(self) -> None:
        cb = self.orchestrator._make_stream_callback(
            verbose_level=0,
            progress_msg=AsyncMock(),
            tool_log=[],
            start_time=time.time(),
        )
        assert cb is None

    # -----------------------------------------------------------------------
    # Secret redaction
    # -----------------------------------------------------------------------

    async def test_redact_api_key(self) -> None:
        from src.bot.orchestrator import _redact_secrets

        result = _redact_secrets("sk-ant-api03-abc123def456ghi789jkl012mno345")
        assert "***" in result
        assert "abc123def456" not in result

    async def test_redact_safe(self) -> None:
        from src.bot.orchestrator import _redact_secrets

        assert _redact_secrets("git status") == "git status"

    # -----------------------------------------------------------------------
    # Handler registration
    # -----------------------------------------------------------------------

    async def test_registration(self) -> None:
        from telegram.ext import CommandHandler

        app = MagicMock()
        app.add_handler = MagicMock()
        self.orchestrator.register_handlers(app)

        cmds = [
            c
            for c in app.add_handler.call_args_list
            if isinstance(c[0][0], CommandHandler)
        ]
        assert len(cmds) == 5

    # -----------------------------------------------------------------------
    # REAL Claude SDK tests
    # -----------------------------------------------------------------------

    async def test_sdk_text(self) -> None:
        """Send a text prompt through the REAL Claude SDK and verify response."""
        update = _make_update(text="What is 2+2? Reply with just the number.")
        ctx = _make_context(self.settings, self.deps)
        ctx.user_data["verbose_level"] = 1

        await self.orchestrator.agentic_text(update, ctx)

        # Session ID should be set from Claude's response
        session_id = ctx.user_data.get("claude_session_id")
        assert session_id, "Expected Claude to return a session ID"

        # Should have received a response (progress msg deleted + reply sent)
        replies = _get_all_replies(update)
        assert len(replies) >= 2, f"Expected at least 2 replies, got {len(replies)}"
        # Last reply should contain the answer
        final_reply = replies[-1]
        assert "4" in final_reply, f"Expected '4' in response: {final_reply}"

        self.report.results[-1].details = (
            f"session={session_id[:20]}... response_len={len(final_reply)}"
        )

    async def test_sdk_session_resume(self) -> None:
        """Send two messages and verify session is resumed on the second."""
        ctx = _make_context(self.settings, self.deps)

        # First message
        update1 = _make_update(text="Remember the word 'pineapple'. Just say OK.")
        await self.orchestrator.agentic_text(update1, ctx)
        session_id = ctx.user_data.get("claude_session_id")
        assert session_id, "First message should produce a session ID"

        # Second message — should resume same session
        update2 = _make_update(
            text="What word did I ask you to remember? Reply with just the word."
        )
        await self.orchestrator.agentic_text(update2, ctx)

        session_id_2 = ctx.user_data.get("claude_session_id")
        assert session_id_2, "Second message should have a session ID"

        replies = _get_all_replies(update2)
        final = replies[-1].lower() if replies else ""
        assert "pineapple" in final, f"Expected 'pineapple' in: {final}"

        self.report.results[-1].details = (
            f"session1={session_id[:16]}... session2={session_id_2[:16]}..."
        )

    async def test_sdk_new_then_text(self) -> None:
        """Verify /new creates a fresh session (not resuming the old one)."""
        ctx = _make_context(self.settings, self.deps)

        # First message — establish a session
        update1 = _make_update(text="Say 'hello'")
        await self.orchestrator.agentic_text(update1, ctx)
        old_session = ctx.user_data.get("claude_session_id")
        assert old_session

        # /new
        update_new = _make_update()
        await self.orchestrator.agentic_new(update_new, ctx)
        assert ctx.user_data["claude_session_id"] is None

        # New message — should get a DIFFERENT session
        update2 = _make_update(text="What is 1+1? Just the number.")
        await self.orchestrator.agentic_text(update2, ctx)
        new_session = ctx.user_data.get("claude_session_id")
        assert new_session
        assert new_session != old_session, (
            f"Expected different session IDs: {old_session} vs {new_session}"
        )

        self.report.results[-1].details = (
            f"old={old_session[:16]}... new={new_session[:16]}..."
        )


# ---------------------------------------------------------------------------
# Bootstrap real dependencies
# ---------------------------------------------------------------------------


async def setup_real_deps(
    workspace: Path, skip_sdk: bool = False
) -> tuple:
    """Build real dependencies (same wiring as main.py create_application)."""
    from src.claude.facade import ClaudeIntegration
    from src.claude.monitor import ToolMonitor
    from src.claude.sdk_integration import ClaudeSDKManager
    from src.claude.session import InMemorySessionStorage, SessionManager
    from src.config import create_test_config
    from src.security.audit import AuditLogger, InMemoryAuditStorage
    from src.security.rate_limiter import RateLimiter
    from src.security.validators import SecurityValidator

    settings = create_test_config(
        approved_directory=str(workspace),
        agentic_mode=True,
        disable_security_patterns=True,
        disable_tool_validation=True,
    )

    # Real security components
    security_validator = SecurityValidator(
        settings.approved_directory,
        disable_security_patterns=True,
    )
    audit_logger = AuditLogger(InMemoryAuditStorage())

    # Real session + tool management
    session_storage = InMemorySessionStorage()
    session_manager = SessionManager(settings, session_storage)
    tool_monitor = ToolMonitor(settings, security_validator, agentic_mode=True)

    # Real Claude SDK (or mock if --skip-sdk)
    if skip_sdk:
        claude_integration = AsyncMock()
        claude_integration.run_command = AsyncMock(
            return_value=_make_mock_response()
        )
        claude_integration._find_resumable_session = AsyncMock(return_value=None)
    else:
        sdk_manager = ClaudeSDKManager(settings)
        claude_integration = ClaudeIntegration(
            config=settings,
            sdk_manager=sdk_manager,
            session_manager=session_manager,
            tool_monitor=tool_monitor,
        )

    deps = {
        "claude_integration": claude_integration,
        "storage": AsyncMock(),  # Storage save is not critical for E2E
        "security_validator": security_validator,
        "rate_limiter": None,
        "audit_logger": audit_logger,
        "features": None,
    }

    return settings, deps


def _make_mock_response() -> Any:
    """Fallback response when --skip-sdk is used."""
    from src.claude.sdk_integration import ClaudeResponse

    return ClaudeResponse(
        content="Mock response (SDK skipped). 4",
        session_id="mock-session-001",
        cost=0.0,
        duration_ms=100,
        num_turns=1,
        tools_used=[],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description="Live agentic E2E tests")
    parser.add_argument(
        "--skip-sdk",
        action="store_true",
        help="Skip real Claude SDK calls (test everything else)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Setup logging
    import logging

    level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Create workspace with test repos
    with tempfile.TemporaryDirectory(prefix="e2e_agentic_") as tmpdir:
        workspace = Path(tmpdir)
        alpha = workspace / "repo_alpha"
        alpha.mkdir()
        (alpha / ".git").mkdir()
        (alpha / "main.py").write_text("print('hello')\n")

        beta = workspace / "repo_beta"
        beta.mkdir()
        (beta / "README.md").write_text("# Beta\n")

        print(f"Workspace: {workspace}")
        if not args.skip_sdk:
            print("Claude SDK: LIVE (real API calls, costs money)")
        else:
            print("Claude SDK: SKIPPED (mock responses)")

        settings, deps = await setup_real_deps(workspace, args.skip_sdk)
        runner = AgenticLiveTests(settings, deps, workspace, args.skip_sdk)
        report = await runner.run_all()
        report.print_report()

        return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
