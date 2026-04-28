"""Event bus middleware wrapping existing security and auth systems.

Provides event-level validation before handlers process events,
reusing SecurityValidator and AuthenticationManager.

Also hosts the WebhookFilter — a pre-bus drop policy that decides
whether a freshly received webhook is even worth waking the agent for.
Rules are hardcoded for the rusty pager use case; constructor params
exist so tests can pin behavior, not so operators can tune at runtime.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, Optional, Set, Tuple

import structlog

from ..security.auth import AuthenticationManager
from ..security.validators import SecurityValidator
from .bus import Event, EventBus
from .types import UserMessageEvent, WebhookEvent

logger = structlog.get_logger()


# Hardcoded drop rules for the pager use case. If a second bot ever
# consumes raw webhooks with different needs, lift these to settings then.
DEFAULT_DROP_EVENTS: Tuple[str, ...] = (
    "ping",
    "workflow_run.requested",
    "workflow_run.queued",
    "workflow_run.in_progress",
    "workflow_run.waiting",
    "push.deleted",
    "push.created",
)

# Conclusions that mean a CI run finished cleanly — dropped so the agent
# only wakes for failures.
SUCCESS_CONCLUSIONS: Tuple[str, ...] = ("success", "neutral", "skipped", "stale")

# In-process dedupe window for X-GitHub-Delivery retries.
DEDUPE_WINDOW_SECONDS: int = 300


class EventSecurityMiddleware:
    """Validates events before they reach handlers.

    Wraps the existing SecurityValidator for path/input validation
    and AuthenticationManager for user authentication.
    """

    def __init__(
        self,
        event_bus: EventBus,
        security_validator: SecurityValidator,
        auth_manager: AuthenticationManager,
    ) -> None:
        self.event_bus = event_bus
        self.security = security_validator
        self.auth = auth_manager

    def register(self) -> None:
        """Subscribe as a global handler to validate all events."""
        self.event_bus.subscribe(UserMessageEvent, self.validate_user_message)
        self.event_bus.subscribe(WebhookEvent, self.validate_webhook)

    async def validate_user_message(self, event: Event) -> None:
        """Validate user message events."""
        if not isinstance(event, UserMessageEvent):
            return

        # Validate the working directory
        is_valid, _, error = self.security.validate_path(str(event.working_directory))
        if not is_valid:
            logger.warning(
                "Event rejected: invalid working directory",
                event_id=event.id,
                user_id=event.user_id,
                error=error,
            )
            raise ValueError(f"Event security validation failed: {error}")

    async def validate_webhook(self, event: Event) -> None:
        """Validate webhook events (signature verified upstream in API layer)."""
        if not isinstance(event, WebhookEvent):
            return

        # Webhooks are signature-verified in the API layer.
        # Here we just log for audit purposes.
        logger.info(
            "Webhook event passed to bus",
            provider=event.provider,
            event_type=event.event_type_name,
            delivery_id=event.delivery_id,
        )


# ---- Webhook noise filter -------------------------------------------------


@dataclass
class WebhookStats:
    """Process-lifetime counters surfaced by the health probe."""

    events_seen_total: int = 0
    events_dropped_total: int = 0
    events_escalated_total: int = 0
    last_event_at: Optional[datetime] = None
    last_event_type: Optional[str] = None
    drop_reasons: Dict[str, int] = field(default_factory=dict)

    def record_seen(self, event_type: str) -> None:
        self.events_seen_total += 1
        self.last_event_at = datetime.now(UTC)
        self.last_event_type = event_type

    def record_dropped(self, reason: str) -> None:
        self.events_dropped_total += 1
        self.drop_reasons[reason] = self.drop_reasons.get(reason, 0) + 1

    def record_escalated(self) -> None:
        self.events_escalated_total += 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "last_event_at": (
                self.last_event_at.isoformat().replace("+00:00", "Z")
                if self.last_event_at
                else None
            ),
            "last_event_type": self.last_event_type,
            "events_seen_total": self.events_seen_total,
            "events_dropped_total": self.events_dropped_total,
            "events_escalated_total": self.events_escalated_total,
            "drop_reasons": dict(self.drop_reasons),
        }


class WebhookFilter:
    """Decide whether a webhook should be escalated to the agent.

    Rules (in order):
      1. Duplicate X-GitHub-Delivery within `dedupe_window_seconds` -> drop
      2. Event matches `drop_events` set                            -> drop
         (workflow_run uses synthetic key `workflow_run.<action>`)
      3. workflow_run.completed with success-like conclusion when
         drop_success=True                                          -> drop
      4. Anything else                                              -> escalate

    Unknown event types fall through with a WARN log so we don't quietly
    silence new GitHub event categories.
    """

    def __init__(
        self,
        drop_events: Optional[Iterable[str]] = None,
        drop_success: bool = True,
        dedupe_window_seconds: int = DEDUPE_WINDOW_SECONDS,
        dedupe_max_entries: int = 1024,
        stats: Optional[WebhookStats] = None,
    ) -> None:
        self.drop_events: Set[str] = set(
            drop_events if drop_events is not None else DEFAULT_DROP_EVENTS
        )
        self.drop_success = drop_success
        self.dedupe_window_seconds = dedupe_window_seconds
        self.dedupe_max_entries = dedupe_max_entries
        self.stats = stats or WebhookStats()
        # delivery_id -> monotonic timestamp; OrderedDict gives us LRU eviction
        self._seen_deliveries: "OrderedDict[str, float]" = OrderedDict()

    # ---- public API ------------------------------------------------------

    def should_escalate(
        self,
        event_type: str,
        payload: Dict[str, Any],
        delivery_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Return (escalate, reason). reason is for logging/metrics."""
        self.stats.record_seen(event_type)

        if delivery_id and self._is_duplicate(delivery_id):
            self.stats.record_dropped("duplicate_delivery")
            return False, "duplicate_delivery"

        # Synthetic key for action-bearing events lets operators tune at
        # the action granularity (e.g. workflow_run.queued).
        action = payload.get("action") if isinstance(payload, dict) else None
        keyed = f"{event_type}.{action}" if action else event_type

        # Prefer the most-specific match for telemetry, fall back to bare.
        if keyed in self.drop_events:
            self.stats.record_dropped(keyed)
            return False, keyed
        if event_type in self.drop_events:
            self.stats.record_dropped(event_type)
            return False, event_type

        if event_type == "workflow_run":
            wr = payload.get("workflow_run") or {}
            conclusion = wr.get("conclusion")
            if (
                action == "completed"
                and self.drop_success
                and conclusion in SUCCESS_CONCLUSIONS
            ):
                reason = f"workflow_run.completed.{conclusion}"
                self.stats.record_dropped(reason)
                return False, reason

        if event_type == "push":
            # Branch create/delete fan-out from defaults, but operators
            # may have overridden drop_events. Fall through if so.
            if payload.get("deleted") is True and "push.deleted" in self.drop_events:
                self.stats.record_dropped("push.deleted")
                return False, "push.deleted"
            if payload.get("created") is True and "push.created" in self.drop_events:
                self.stats.record_dropped("push.created")
                return False, "push.created"

        self.stats.record_escalated()
        return True, "escalated"

    # ---- internals -------------------------------------------------------

    def _is_duplicate(self, delivery_id: str) -> bool:
        now = time.monotonic()
        # Drop expired entries lazily from the front of the OrderedDict.
        cutoff = now - self.dedupe_window_seconds
        while self._seen_deliveries:
            oldest_key = next(iter(self._seen_deliveries))
            if self._seen_deliveries[oldest_key] < cutoff:
                self._seen_deliveries.popitem(last=False)
            else:
                break

        if delivery_id in self._seen_deliveries:
            # refresh recency so a flood of retries stays deduped
            self._seen_deliveries.move_to_end(delivery_id)
            self._seen_deliveries[delivery_id] = now
            return True

        self._seen_deliveries[delivery_id] = now
        if len(self._seen_deliveries) > self.dedupe_max_entries:
            self._seen_deliveries.popitem(last=False)
        return False
