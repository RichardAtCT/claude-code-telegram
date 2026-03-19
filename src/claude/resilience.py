"""Graceful degradation: CircuitBreaker, RetryHandler, RequestQueue.

Provides resilience patterns for Claude API calls:
- CircuitBreaker: prevents cascading failures by stopping calls after N failures.
- RetryHandler: exponential backoff for transient errors.
- RequestQueue: persists requests when circuit is open, replays when it closes.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog

from ..storage.database import DatabaseManager

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject calls
    HALF_OPEN = "half_open" # Testing — allow one call to probe


class CircuitBreaker:
    """Simple circuit breaker with three states.

    CLOSED  -> OPEN after ``threshold`` consecutive failures.
    OPEN    -> HALF_OPEN after ``cooldown_seconds`` elapse.
    HALF_OPEN -> CLOSED on success, OPEN on failure.
    """

    def __init__(
        self,
        threshold: int = 5,
        cooldown_seconds: int = 60,
    ) -> None:
        self._threshold = threshold
        self._cooldown_seconds = cooldown_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._on_state_change: Optional[Callable[[CircuitState], Any]] = None

    # --- Public API ---

    def can_execute(self) -> bool:
        """Return True if a call is allowed right now."""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._cooldown_seconds:
                self._transition(CircuitState.HALF_OPEN)
                return True
            return False
        # HALF_OPEN: allow one probe
        return True

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state in (CircuitState.HALF_OPEN, CircuitState.CLOSED):
            self._failure_count = 0
            if self._state != CircuitState.CLOSED:
                self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif (
            self._state == CircuitState.CLOSED
            and self._failure_count >= self._threshold
        ):
            self._transition(CircuitState.OPEN)

    def get_state(self) -> CircuitState:
        """Return current circuit state."""
        # Check for automatic OPEN -> HALF_OPEN transition on read
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._cooldown_seconds:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def set_on_state_change(self, callback: Callable[[CircuitState], Any]) -> None:
        """Register a callback invoked on every state transition."""
        self._on_state_change = callback

    # --- Internal ---

    def _transition(self, new_state: CircuitState) -> None:
        old = self._state
        self._state = new_state
        logger.info(
            "Circuit breaker state change",
            old_state=old.value,
            new_state=new_state.value,
            failure_count=self._failure_count,
        )
        if self._on_state_change:
            try:
                self._on_state_change(new_state)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# RetryHandler
# ---------------------------------------------------------------------------

# Errors considered transient (worth retrying)
_TRANSIENT_SUBSTRINGS = [
    "429",
    "503",
    "rate limit",
    "too many requests",
    "service unavailable",
    "connection",
    "timeout",
    "timed out",
    "network",
    "ECONNRESET",
    "ECONNREFUSED",
    "temporary",
]


def is_transient_error(error: Exception) -> bool:
    """Return True if the error looks transient (network, 429, 503)."""
    msg = str(error).lower()
    return any(sub in msg for sub in _TRANSIENT_SUBSTRINGS)


class RetryHandler:
    """Retry with exponential backoff for transient errors."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

    async def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute *func* with retries on transient errors.

        Non-transient errors are raised immediately.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if not is_transient_error(exc) or attempt >= self._max_retries:
                    raise

                delay = min(
                    self._base_delay * (2 ** attempt),
                    self._max_delay,
                )
                logger.warning(
                    "Transient error, retrying",
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    delay_seconds=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RequestQueue
# ---------------------------------------------------------------------------

@dataclass
class PendingRequest:
    """A queued request awaiting replay."""

    id: Optional[int] = None
    user_id: int = 0
    chat_id: int = 0
    prompt: str = ""
    working_directory: str = ""
    queued_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | processing | completed | failed
    retry_count: int = 0


class RequestQueue:
    """Persist pending requests to SQLite and replay when circuit closes.

    Uses the ``pending_requests`` table managed via database migration.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        max_queue_size: int = 100,
    ) -> None:
        self._db = db_manager
        self._max_queue_size = max_queue_size
        self._replay_task: Optional[asyncio.Task] = None
        self._replay_callback: Optional[Callable] = None

    def set_replay_callback(
        self, callback: Callable[[PendingRequest], Any]
    ) -> None:
        """Set the async callback used to replay queued requests."""
        self._replay_callback = callback

    async def enqueue(self, request: PendingRequest) -> bool:
        """Add a request to the queue. Returns False if queue is full."""
        current_size = await self._count_pending()
        if current_size >= self._max_queue_size:
            logger.warning(
                "Request queue full, dropping request",
                user_id=request.user_id,
                queue_size=current_size,
                max_size=self._max_queue_size,
            )
            return False

        async with self._db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO pending_requests
                    (user_id, chat_id, prompt, working_directory,
                     queued_at, status, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.user_id,
                    request.chat_id,
                    request.prompt,
                    request.working_directory,
                    request.queued_at,
                    "pending",
                    0,
                ),
            )
            await conn.commit()

        logger.info(
            "Request queued",
            user_id=request.user_id,
            chat_id=request.chat_id,
        )
        return True

    async def get_pending(self, limit: int = 10) -> List[PendingRequest]:
        """Retrieve oldest pending requests."""
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, user_id, chat_id, prompt, working_directory,
                       queued_at, status, retry_count
                FROM pending_requests
                WHERE status = 'pending'
                ORDER BY queued_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()

        return [
            PendingRequest(
                id=row[0],
                user_id=row[1],
                chat_id=row[2],
                prompt=row[3],
                working_directory=row[4],
                queued_at=row[5],
                status=row[6],
                retry_count=row[7],
            )
            for row in rows
        ]

    async def mark_status(
        self, request_id: int, status: str, increment_retry: bool = False
    ) -> None:
        """Update the status (and optionally retry count) of a queued request."""
        async with self._db.get_connection() as conn:
            if increment_retry:
                await conn.execute(
                    """
                    UPDATE pending_requests
                    SET status = ?, retry_count = retry_count + 1
                    WHERE id = ?
                    """,
                    (status, request_id),
                )
            else:
                await conn.execute(
                    "UPDATE pending_requests SET status = ? WHERE id = ?",
                    (status, request_id),
                )
            await conn.commit()

    async def start_replay(self) -> None:
        """Start a background task to replay pending requests."""
        if self._replay_task and not self._replay_task.done():
            return
        self._replay_task = asyncio.create_task(self._replay_loop())

    async def stop_replay(self) -> None:
        """Cancel the replay background task."""
        if self._replay_task and not self._replay_task.done():
            self._replay_task.cancel()
            try:
                await self._replay_task
            except asyncio.CancelledError:
                pass

    async def _replay_loop(self) -> None:
        """Process pending requests one by one."""
        if not self._replay_callback:
            logger.warning("No replay callback set, skipping queue replay")
            return

        pending = await self.get_pending(limit=20)
        if not pending:
            return

        logger.info("Replaying queued requests", count=len(pending))

        for req in pending:
            try:
                await self.mark_status(req.id, "processing")
                await self._replay_callback(req)
                await self.mark_status(req.id, "completed")
                logger.info(
                    "Queued request replayed successfully",
                    request_id=req.id,
                    user_id=req.user_id,
                )
            except Exception as exc:
                logger.error(
                    "Queued request replay failed",
                    request_id=req.id,
                    error=str(exc),
                )
                await self.mark_status(
                    req.id, "failed", increment_retry=True
                )

    async def _count_pending(self) -> int:
        async with self._db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM pending_requests WHERE status = 'pending'"
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
