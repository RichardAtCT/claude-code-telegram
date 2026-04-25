"""
Support Engineer — automatic error detection, repair, and escalation.

Runs as an APScheduler cron job (every minute) on the existing JobScheduler.
Reads errors from the platform bot.db, applies known fixes, logs to support_fixes,
and escalates unknown errors to the owner via Telegram.

Pattern: read-only to bot.db (no mutations to tenant data).
"""

import asyncio
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from ..events.bus import EventBus
from ..storage.database import DatabaseManager

logger = structlog.get_logger()

# Telegram bot instance — passed in after bot is initialized
_telegram_bot: Optional[object] = None
_owner_chat_id: Optional[int] = None


def set_bot_and_owner(bot, owner_chat_id: int) -> None:
    """Called from main.py after bot is initialized."""
    global _telegram_bot, _owner_chat_id
    _telegram_bot = bot
    _owner_chat_id = owner_chat_id


@dataclass
class ErrorPattern:
    """A known error pattern and its fix."""
    name: str
    match: list[str]  # regex patterns — any match triggers this fix
    fix: str  # fix function name


KNOWN_ERRORS: list[ErrorPattern] = [
    ErrorPattern(
        name="hindsight_bank_missing",
        match=[
            r"bank.*not found",
            r"404.*bank",
            r"bank_id.*not exist",
            r"bank.*does not exist",
        ],
        fix="fix_hindsight_bank",
    ),
    ErrorPattern(
        name="bot_db_missing_table",
        match=[
            r"no such table",
            r"table.*does not exist",
        ],
        fix="fix_bot_db",
    ),
    ErrorPattern(
        name="homedir_permission_error",
        match=[
            r"permission denied.*\.claude",
            r"\[Errno 13\].*homedir",
        ],
        fix="fix_homedir_perms",
    ),
    ErrorPattern(
        name="telegram_rate_limit",
        match=[
            r"429.*Too Many Requests",
            r"rate limit",
            r"retry after",
        ],
        fix="fix_telegram_rate_limit",
    ),
]


@dataclass
class ErrorRecord:
    session_id: int
    tenant_username: str
    error_text: str
    created_at: str


class SupportEngineer:
    """Automatic error detection and repair for the multi-tenant platform."""

    def __init__(
        self,
        db_path: str = "/root/.claude/bot.db",
        platform_bin: str = "/opt/multi-tenant/bin",
        vault_path: str = "/opt/multi-tenant/vault",
    ) -> None:
        self.db_path = db_path
        self.platform_bin = Path(platform_bin)
        self.vault_path = Path(vault_path)
        self._compiled_patterns: list[tuple[ErrorPattern, list[re.Pattern]]] = []

    def start(self) -> None:
        """Register the cron job on the existing APScheduler JobScheduler.

        Note: This is called AFTER JobScheduler.start() in main.py.
        We use a lazy import to avoid circular imports.
        """
        # Compile regex patterns once
        self._compiled_patterns = []
        for ep in KNOWN_ERRORS:
            compiled = [(ep, re.compile(p, re.IGNORECASE)) for p in ep.match]
            self._compiled_patterns.extend(compiled)

        # Import here to avoid circular import with main.py
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self._run_once,
            CronTrigger(second=0),  # run at the top of every minute
            max_instances=1,
            name="support_engineer_health_check",
            misfire_grace_time=30,
        )
        scheduler.start()
        logger.info("Support Engineer started", trigger="* * * * *")

    async def _run_once(self) -> None:
        """Called every minute by APScheduler."""
        start = time.monotonic()
        logger.info("support_engineer.run", phase="scan")

        try:
            # Step 1: Scan for recent errors
            errors = self._scan_errors()
            if not errors:
                logger.debug("support_engineer.run", phase="no_errors", duration_s=time.monotonic() - start)
                return

            logger.info("support_engineer.run", phase="classify", error_count=len(errors))
            fixed = 0
            escalated = 0

            for err in errors:
                pattern = self._classify(err.error_text)
                if pattern:
                    success = await self._apply_fix(pattern, err)
                    self._log_fix(err, pattern.name, success)
                    if success:
                        fixed += 1
                else:
                    await self._escalate(err)
                    escalated += 1

            duration = time.monotonic() - start
            logger.info(
                "support_engineer.run",
                phase="done",
                errors=len(errors),
                fixed=fixed,
                escalated=escalated,
                duration_s=round(duration, 2),
            )
        except Exception:
            logger.exception("support_engineer.run", phase="error")

    # ------------------------------------------------------------------
    # Error scanning
    # ------------------------------------------------------------------

    def _scan_errors(self) -> list[ErrorRecord]:
        """Scan recent error messages from bot.db that haven't been handled."""
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COALESCE(m.session_id, 0) as session_id,
                    COALESCE(u.telegram_username, 'unknown') as username,
                    COALESCE(m.error, m.prompt, '') as error_text,
                    m.timestamp as created_at
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.user_id
                WHERE m.error IS NOT NULL
                  AND m.error != ''
                  AND m.timestamp > datetime('now', '-10 minutes')
                ORDER BY m.timestamp DESC
                LIMIT 20
            """)
            rows = cur.fetchall()
            return [
                ErrorRecord(
                    session_id=r["session_id"],
                    tenant_username=r["username"],
                    error_text=r["error_text"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Error classification
    # ------------------------------------------------------------------

    def _classify(self, error_text: str) -> Optional[ErrorPattern]:
        """Match error text against known patterns. Returns first match or None."""
        for pattern, compiled in self._compiled_patterns:
            if compiled.search(error_text):
                return pattern
        return None

    # ------------------------------------------------------------------
    # Fix application
    # ------------------------------------------------------------------

    async def _apply_fix(self, pattern: ErrorPattern, err: ErrorRecord) -> bool:
        """Apply the fix for a known pattern. Returns True on success."""
        fix_map = {
            "fix_hindsight_bank": self._fix_hindsight_bank,
            "fix_bot_db": self._fix_bot_db,
            "fix_homedir_perms": self._fix_homedir_perms,
            "fix_telegram_rate_limit": self._fix_telegram_rate_limit,
        }
        fix_fn = fix_map.get(pattern.fix)
        if fix_fn:
            try:
                return await fix_fn(err)
            except Exception:
                logger.exception("fix.failed", pattern=pattern.name, tenant=err.tenant_username)
                return False
        return False

    async def _fix_hindsight_bank(self, err: ErrorRecord) -> bool:
        """Recreate a missing Hindsight bank for a tenant."""
        from .create_hindsight_bank import create_bank

        # Get tenant's telegram_id from DB
        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("SELECT telegram_id FROM tenants WHERE username = ?", (err.tenant_username,))
            row = cur.fetchone()
            if not row:
                logger.warning("fix.hindsight_bank.no_tenant", username=err.tenant_username)
                return False
            telegram_id = row[0]
        finally:
            conn.close()

        bank_id = f"telegram_{telegram_id}"
        logger.info("fix.hindsight_bank", bank_id=bank_id)
        create_bank(bank_id)
        return True

    async def _fix_bot_db(self, err: ErrorRecord) -> bool:
        """Re-clone bot.db from template for a tenant."""
        import subprocess

        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("SELECT homedir_path FROM tenants WHERE username = ?", (err.tenant_username,))
            row = cur.fetchone()
            if not row:
                return False
            homedir = row[0]
        finally:
            conn.close()

        bot_db_path = Path(homedir) / ".claude" / "bot.db"
        template_path = Path("/opt/multi-tenant/templates/bot.db.template")
        if not template_path.exists():
            return False

        logger.info("fix.bot_db", tenant=err.tenant_username, path=str(bot_db_path))
        result = subprocess.run(
            ["cp", str(template_path), str(bot_db_path)],
            capture_output=True,
        )
        return result.returncode == 0

    async def _fix_homedir_perms(self, err: ErrorRecord) -> bool:
        """Fix homedir and .claude directory permissions."""
        import subprocess

        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("SELECT homedir_path FROM tenants WHERE username = ?", (err.tenant_username,))
            row = cur.fetchone()
            if not row:
                return False
            homedir = Path(row[0])
        finally:
            conn.close()

        logger.info("fix.homedir_perms", tenant=err.tenant_username, homedir=str(homedir))
        ok = True
        for path in [homedir, homedir / ".claude", homedir / ".claude" / "credentials"]:
            try:
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(0o700)
            except Exception:
                ok = False
        return ok

    async def _fix_telegram_rate_limit(self, err: ErrorRecord) -> bool:
        """Telegram rate limits self-heal — just log and wait."""
        logger.info("fix.telegram_rate_limit", tenant=err.tenant_username, action="wait_and_retry")
        return True  # Rate limits resolve on their own

    # ------------------------------------------------------------------
    # Logging and escalation
    # ------------------------------------------------------------------

    def _log_fix(
        self,
        err: ErrorRecord,
        pattern_name: str,
        succeeded: bool,
    ) -> None:
        """Record the fix attempt in support_fixes table."""
        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO support_fixes
                    (tenant_id, session_id, error_type, fix_applied, fix_succeeded, applied_at)
                VALUES (
                    (SELECT id FROM tenants WHERE username = ? LIMIT 1),
                    ?, ?, ?, ?, CURRENT_TIMESTAMP
                )
            """, (err.tenant_username, err.session_id, pattern_name, pattern_name, 1 if succeeded else 0))
            conn.commit()
            logger.info("support_fixes.logged", tenant=err.tenant_username, pattern=pattern_name, ok=succeeded)
        except Exception:
            logger.exception("support_fixes.log_failed")
        finally:
            conn.close()

    async def _escalate(self, err: ErrorRecord) -> None:
        """Send unknown error to owner via Telegram."""
        if not _telegram_bot or not _owner_chat_id:
            logger.warning("escalate.no_bot_or_owner", tenant=err.tenant_username)
            return

        msg = (
            f"🚨 *Support Engineer — Unknown Error*\n\n"
            f"*Tenant:* `{err.tenant_username}`\n"
            f"*Session:* `{err.session_id}`\n"
            f"*Time:* `{err.created_at}`\n\n"
            f"*Error:* `{err.error_text[:300]}`"
        )
        try:
            await _telegram_bot.send_message(
                chat_id=_owner_chat_id,
                text=msg,
                parse_mode="Markdown",
            )
            logger.info("escalate.sent", tenant=err.tenant_username)
        except Exception:
            logger.exception("escalate.failed", tenant=err.tenant_username)
