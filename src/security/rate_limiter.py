"""Rate limiting implementation with multiple strategies.

Features:
- Token bucket algorithm
- Cost-based limiting
- Per-user tracking
- Burst handling
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import structlog

from ..config.settings import Settings

logger = structlog.get_logger()


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""

    capacity: int
    tokens: float
    last_update: datetime
    refill_rate: float = 1.0  # tokens per second

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from bucket."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """Refill tokens based on time passed."""
        now = datetime.now(UTC)
        elapsed = (now - self.last_update).total_seconds()
        self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))
        self.last_update = now

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait before tokens are available."""
        self._refill()
        if self.tokens >= tokens:
            return 0.0

        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate

    def get_status(self) -> Dict[str, float]:
        """Get current bucket status."""
        self._refill()
        return {
            "capacity": self.capacity,
            "tokens": self.tokens,
            "utilization": (self.capacity - self.tokens) / self.capacity,
            "refill_rate": self.refill_rate,
        }


class RateLimiter:
    """Main rate limiting system with request and cost-based limits."""

    def __init__(self, config: Settings):
        self.config = config
        self.request_buckets: Dict[int, RateLimitBucket] = {}
        self.cost_tracker: Dict[int, float] = defaultdict(float)
        self.cost_reset_time: Dict[int, datetime] = {}
        self.locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Calculate refill rate from config
        self.refill_rate = (
            self.config.rate_limit_requests / self.config.rate_limit_window
        )

        logger.info(
            "Rate limiter initialized",
            requests_per_window=self.config.rate_limit_requests,
            window_seconds=self.config.rate_limit_window,
            burst_capacity=self.config.rate_limit_burst,
            max_cost_per_user=self.config.claude_max_cost_per_user,
            refill_rate=self.refill_rate,
        )

    async def check_rate_limit(
        self, user_id: int, cost: float = 1.0, tokens: int = 1
    ) -> Tuple[bool, Optional[str]]:
        """Check if request is allowed under rate limits."""
        async with self.locks[user_id]:
            # Check request rate limit
            rate_allowed, rate_message = self._check_request_rate(user_id, tokens)
            if not rate_allowed:
                logger.warning(
                    "Request rate limit exceeded",
                    user_id=user_id,
                    tokens_requested=tokens,
                )
                return False, rate_message

            # Check cost limit
            cost_allowed, cost_message = self._check_cost_limit(user_id, cost)
            if not cost_allowed:
                logger.warning(
                    "Cost limit exceeded",
                    user_id=user_id,
                    cost_requested=cost,
                    current_usage=self.cost_tracker[user_id],
                )
                return False, cost_message

            # If both checks pass, consume resources
            self._consume_request_tokens(user_id, tokens)
            self._track_cost(user_id, cost)

            logger.debug(
                "Rate limit check passed", user_id=user_id, cost=cost, tokens=tokens
            )
            return True, None

    def _check_request_rate(
        self, user_id: int, tokens: int
    ) -> Tuple[bool, Optional[str]]:
        """Check request rate limit."""
        bucket = self._get_or_create_bucket(user_id)

        if bucket.consume(tokens):
            return True, None

        wait_time = bucket.get_wait_time(tokens)
        status = bucket.get_status()

        message = (
            f"Rate limit exceeded. Please wait {wait_time:.1f} seconds "
            f"before making more requests. "
            f"Bucket: {status['tokens']:.1f}/{status['capacity']} tokens available."
        )
        return False, message

    def _check_cost_limit(
        self, user_id: int, cost: float
    ) -> Tuple[bool, Optional[str]]:
        """Check cost-based limit."""
        # Reset cost tracker if enough time has passed
        self._maybe_reset_cost_tracker(user_id)

        current_cost = self.cost_tracker[user_id]
        if current_cost + cost > self.config.claude_max_cost_per_user:
            remaining = max(0, self.config.claude_max_cost_per_user - current_cost)
            message = (
                f"Cost limit exceeded. Remaining budget: ${remaining:.2f}. "
                f"Current usage: ${current_cost:.2f}/"
                f"${self.config.claude_max_cost_per_user:.2f}"
            )
            return False, message

        return True, None

    def _consume_request_tokens(self, user_id: int, tokens: int) -> None:
        """Consume tokens from request bucket."""
        bucket = self._get_or_create_bucket(user_id)
        bucket.consume(tokens)

    def _track_cost(self, user_id: int, cost: float) -> None:
        """Track cost usage for user."""
        self.cost_tracker[user_id] += cost

        logger.debug(
            "Cost tracked",
            user_id=user_id,
            cost=cost,
            total_usage=self.cost_tracker[user_id],
        )

    def _get_or_create_bucket(self, user_id: int) -> RateLimitBucket:
        """Get or create rate limit bucket for user."""
        if user_id not in self.request_buckets:
            self.request_buckets[user_id] = RateLimitBucket(
                capacity=self.config.rate_limit_burst,
                tokens=self.config.rate_limit_burst,
                last_update=datetime.now(UTC),
                refill_rate=self.refill_rate,
            )
            logger.debug("Created rate limit bucket", user_id=user_id)

        return self.request_buckets[user_id]

    def _maybe_reset_cost_tracker(self, user_id: int) -> None:
        """Reset cost tracker if reset period has passed."""
        now = datetime.now(UTC)
        last_reset = self.cost_reset_time.get(user_id, now - timedelta(days=1))

        # Reset daily (configurable)
        reset_interval = timedelta(hours=24)
        if now - last_reset >= reset_interval:
            old_cost = self.cost_tracker[user_id]
            self.cost_tracker[user_id] = 0
            self.cost_reset_time[user_id] = now

            if old_cost > 0:
                logger.info(
                    "Cost tracker reset",
                    user_id=user_id,
                    old_cost=old_cost,
                    reset_time=now.isoformat(),
                )

    async def reset_user_limits(self, user_id: int) -> None:
        """Reset all limits for a user (admin function)."""
        async with self.locks[user_id]:
            # Reset cost tracking
            old_cost = self.cost_tracker[user_id]
            self.cost_tracker[user_id] = 0
            self.cost_reset_time[user_id] = datetime.now(UTC)

            # Reset request bucket
            if user_id in self.request_buckets:
                self.request_buckets[user_id].tokens = self.request_buckets[
                    user_id
                ].capacity
                self.request_buckets[user_id].last_update = datetime.now(UTC)

            logger.info("User limits reset", user_id=user_id, old_cost=old_cost)

    def get_user_status(self, user_id: int) -> Dict[str, Any]:
        """Get current rate limit status for user."""
        # Get request bucket status
        bucket = self._get_or_create_bucket(user_id)
        bucket_status = bucket.get_status()

        # Get cost status
        self._maybe_reset_cost_tracker(user_id)
        current_cost = self.cost_tracker[user_id]
        cost_remaining = max(0, self.config.claude_max_cost_per_user - current_cost)

        return {
            "request_bucket": bucket_status,
            "cost_usage": {
                "current": current_cost,
                "limit": self.config.claude_max_cost_per_user,
                "remaining": cost_remaining,
                "utilization": current_cost / self.config.claude_max_cost_per_user,
            },
            "last_reset": self.cost_reset_time.get(
                user_id, datetime.now(UTC)
            ).isoformat(),
        }

    def get_global_status(self) -> Dict[str, Any]:
        """Get global rate limiter statistics."""
        return {
            "active_users": len(self.request_buckets),
            "total_cost_tracked": sum(self.cost_tracker.values()),
            "config": {
                "requests_per_window": self.config.rate_limit_requests,
                "window_seconds": self.config.rate_limit_window,
                "burst_capacity": self.config.rate_limit_burst,
                "max_cost_per_user": self.config.claude_max_cost_per_user,
                "refill_rate": self.refill_rate,
            },
        }

    async def cleanup_inactive_users(
        self, inactive_threshold: timedelta = timedelta(hours=24)
    ) -> int:
        """Clean up rate limit data for inactive users."""
        now = datetime.now(UTC)
        inactive_users = []

        # Find users with old buckets
        for user_id, bucket in self.request_buckets.items():
            if now - bucket.last_update > inactive_threshold:
                inactive_users.append(user_id)

        # Clean up data
        for user_id in inactive_users:
            self.request_buckets.pop(user_id, None)
            self.cost_tracker.pop(user_id, None)
            self.cost_reset_time.pop(user_id, None)
            self.locks.pop(user_id, None)

        if inactive_users:
            logger.info(
                "Cleaned up inactive users",
                count=len(inactive_users),
                threshold_hours=inactive_threshold.total_seconds() / 3600,
            )

        return len(inactive_users)
