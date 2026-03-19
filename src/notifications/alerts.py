"""Alert mechanism for cost, error rate, and security violation monitoring.

Monitors thresholds and sends deduplicated alerts to admin chat IDs
via the NotificationService / Telegram bot.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Literal, Optional

import structlog
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from ..events.bus import EventBus
from ..events.types import AlertEvent

logger = structlog.get_logger()


@dataclass
class _AlertRecord:
    """Tracks the last time a specific alert was sent for dedup."""

    alert_type: str
    last_sent: float = 0.0


class AlertManager:
    """Monitor thresholds and dispatch alerts to admin chats.

    Supports:
    - Per-user cost threshold
    - Global (aggregate) cost threshold
    - Error rate (errors per window)
    - Security violation count

    Alerts are deduplicated: the same alert type won't fire more than
    once per cooldown period.
    """

    def __init__(
        self,
        bot: Bot,
        event_bus: EventBus,
        admin_chat_ids: Optional[List[int]] = None,
        cost_threshold_per_user: float = 10.0,
        cost_threshold_global: float = 100.0,
        error_rate_threshold: int = 10,
        error_rate_window_seconds: int = 300,
        cooldown_seconds: int = 3600,
    ) -> None:
        self._bot = bot
        self._event_bus = event_bus
        self._admin_chat_ids = admin_chat_ids or []
        self._cost_threshold_per_user = cost_threshold_per_user
        self._cost_threshold_global = cost_threshold_global
        self._error_rate_threshold = error_rate_threshold
        self._error_rate_window = error_rate_window_seconds
        self._cooldown = cooldown_seconds

        # State tracking
        self._user_costs: Dict[int, float] = {}
        self._global_cost: float = 0.0
        self._error_timestamps: Deque[float] = deque()
        self._security_violation_count: int = 0

        # Deduplication: alert_key -> last_sent_timestamp
        self._alert_history: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public check methods
    # ------------------------------------------------------------------

    async def check_cost_alert(self, user_id: int, current_cost: float) -> None:
        """Check and potentially fire per-user and global cost alerts."""
        self._user_costs[user_id] = current_cost
        self._global_cost = sum(self._user_costs.values())

        # Per-user threshold
        if current_cost >= self._cost_threshold_per_user:
            await self.send_alert(
                alert_type="cost_per_user",
                severity="warning",
                message=(
                    f"User {user_id} has reached "
                    f"${current_cost:.2f} "
                    f"(threshold: ${self._cost_threshold_per_user:.2f})"
                ),
                details={"user_id": user_id, "cost": current_cost},
                dedup_key=f"cost_user_{user_id}",
            )

        # Global threshold
        if self._global_cost >= self._cost_threshold_global:
            await self.send_alert(
                alert_type="cost_global",
                severity="critical",
                message=(
                    f"Global cost has reached "
                    f"${self._global_cost:.2f} "
                    f"(threshold: ${self._cost_threshold_global:.2f})"
                ),
                details={"global_cost": self._global_cost, "user_costs": dict(self._user_costs)},
                dedup_key="cost_global",
            )

    async def check_error_rate(self) -> None:
        """Record an error and check if error rate exceeds the threshold."""
        now = time.time()
        self._error_timestamps.append(now)

        # Prune old entries outside the window
        cutoff = now - self._error_rate_window
        while self._error_timestamps and self._error_timestamps[0] < cutoff:
            self._error_timestamps.popleft()

        count = len(self._error_timestamps)
        if count >= self._error_rate_threshold:
            await self.send_alert(
                alert_type="error_rate",
                severity="critical",
                message=(
                    f"Error rate alert: {count} errors in the last "
                    f"{self._error_rate_window // 60} minutes "
                    f"(threshold: {self._error_rate_threshold})"
                ),
                details={"error_count": count, "window_seconds": self._error_rate_window},
                dedup_key="error_rate",
            )

    async def check_security_violations(self) -> None:
        """Record a security violation and send an alert."""
        self._security_violation_count += 1
        await self.send_alert(
            alert_type="security_violation",
            severity="critical",
            message=(
                f"Security violation detected "
                f"(total: {self._security_violation_count})"
            ),
            details={"total_violations": self._security_violation_count},
            dedup_key="security_violation",
        )

    # ------------------------------------------------------------------
    # Core alert dispatch
    # ------------------------------------------------------------------

    async def send_alert(
        self,
        alert_type: str,
        severity: Literal["info", "warning", "critical"],
        message: str,
        details: Optional[Dict[str, Any]] = None,
        dedup_key: Optional[str] = None,
    ) -> None:
        """Send an alert to admin chats with deduplication.

        If *dedup_key* is provided, the same key won't trigger another
        alert within the cooldown period.
        """
        key = dedup_key or f"{alert_type}:{severity}"
        now = time.time()

        # Dedup check
        last_sent = self._alert_history.get(key, 0.0)
        if (now - last_sent) < self._cooldown:
            logger.debug(
                "Alert suppressed by cooldown",
                alert_type=alert_type,
                dedup_key=key,
                seconds_remaining=int(self._cooldown - (now - last_sent)),
            )
            return

        self._alert_history[key] = now

        # Publish event on the bus
        alert_event = AlertEvent(
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details or {},
            source="alert_manager",
        )
        try:
            await self._event_bus.publish(alert_event)
        except Exception:
            logger.warning("Failed to publish AlertEvent", alert_type=alert_type)

        # Send to admin chats via Telegram
        severity_icons = {
            "info": "\u2139\ufe0f",
            "warning": "\u26a0\ufe0f",
            "critical": "\U0001f6a8",
        }
        icon = severity_icons.get(severity, "\u26a0\ufe0f")

        text = (
            f"{icon} <b>Alert: {alert_type}</b> "
            f"[{severity.upper()}]\n\n"
            f"{message}"
        )

        for chat_id in self._admin_chat_ids:
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError as e:
                logger.error(
                    "Failed to send alert to admin",
                    chat_id=chat_id,
                    alert_type=alert_type,
                    error=str(e),
                )

        logger.info(
            "Alert dispatched",
            alert_type=alert_type,
            severity=severity,
            message=message,
        )
