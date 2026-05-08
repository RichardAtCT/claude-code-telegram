"""Resilient Telegram API helpers.

The bot must not fail a Claude run just because Telegram transiently rate-limits
or returns a gateway/network error while we update progress UI.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut

logger = structlog.get_logger()

T = TypeVar("T")

_TRANSIENT_ERROR_MARKERS = (
    "too many requests",
    "retry after",
    "bad gateway",
    "gateway timeout",
    "502",
    "503",
    "504",
    "timed out",
    "timeout",
    "connection",
)


def is_transient_telegram_error(exc: BaseException) -> bool:
    """Return True for Telegram/API errors that are safe to retry or suppress."""
    if isinstance(exc, (RetryAfter, TimedOut, NetworkError)):
        return True
    if isinstance(exc, TelegramError):
        message = str(exc).lower()
        return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)
    return False


def retry_after_seconds(exc: BaseException) -> float | None:
    """Extract Telegram RetryAfter seconds, if available."""
    value = getattr(exc, "retry_after", None)
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


async def resilient_telegram_call(
    call: Callable[[], Awaitable[T]],
    *,
    operation: str,
    chat_id: int | None = None,
    attempts: int = 2,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    fail_silently: bool = False,
) -> T | None:
    """Run a Telegram API call with bounded retry/backoff.

    For non-critical UI operations (typing, progress edits, deleting the progress
    message), pass ``fail_silently=True`` so Telegram instability never aborts the
    Claude request. For final delivery, keep ``fail_silently=False`` so callers
    can use a fallback path.
    """
    attempts = max(1, attempts)
    last_exc: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except Exception as exc:  # noqa: BLE001 - API boundary: classify below
            last_exc = exc
            transient = is_transient_telegram_error(exc)
            should_retry = transient and attempt < attempts
            logger.warning(
                "Telegram API call failed",
                operation=operation,
                chat_id=chat_id,
                attempt=attempt,
                attempts=attempts,
                transient=transient,
                retrying=should_retry,
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
            if not should_retry:
                break
            delay = retry_after_seconds(exc)
            if delay is None:
                delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            await asyncio.sleep(delay)

    if fail_silently:
        return None
    assert last_exc is not None
    raise last_exc
