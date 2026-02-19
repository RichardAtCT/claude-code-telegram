"""Tests for rate limiting system."""

from datetime import UTC, datetime, timedelta

import pytest

from src.config import create_test_config
from src.security.rate_limiter import RateLimitBucket, RateLimiter


class TestRateLimitBucket:
    """Test rate limit bucket functionality."""

    def test_bucket_creation(self):
        """Test bucket creation with initial tokens."""
        bucket = RateLimitBucket(
            capacity=10, tokens=10, last_update=datetime.now(UTC), refill_rate=1.0
        )

        assert bucket.capacity == 10
        assert bucket.tokens == 10
        assert bucket.refill_rate == 1.0

    def test_token_consumption(self):
        """Test consuming tokens from bucket."""
        bucket = RateLimitBucket(
            capacity=10, tokens=5, last_update=datetime.now(UTC), refill_rate=1.0
        )

        # Should be able to consume available tokens
        assert bucket.consume(3) is True
        assert abs(bucket.tokens - 2) < 0.01  # Allow for floating point precision

        # Should fail to consume more than available
        assert bucket.consume(5) is False
        assert abs(bucket.tokens - 2) < 0.01  # Should remain unchanged (with precision)

    def test_token_refill(self):
        """Test token refill over time."""
        past_time = datetime.now(UTC) - timedelta(seconds=5)
        bucket = RateLimitBucket(
            capacity=10,
            tokens=5,
            last_update=past_time,
            refill_rate=1.0,  # 1 token per second
        )

        # Trigger refill by checking status
        status = bucket.get_status()

        # Should have refilled ~5 tokens (5 seconds * 1 token/second)
        assert bucket.tokens == 10  # Capped at capacity
        assert status["tokens"] == 10

    def test_wait_time_calculation(self):
        """Test wait time calculation when tokens not available."""
        bucket = RateLimitBucket(
            capacity=10, tokens=2, last_update=datetime.now(UTC), refill_rate=1.0
        )

        # Should be able to consume available tokens immediately
        wait_time = bucket.get_wait_time(2)
        assert wait_time == 0.0

        # Should need to wait for more tokens
        wait_time = bucket.get_wait_time(5)
        assert abs(wait_time - 3.0) < 0.01  # Need 3 more tokens at 1 token/second

    def test_bucket_status(self):
        """Test bucket status reporting."""
        bucket = RateLimitBucket(
            capacity=10, tokens=7, last_update=datetime.now(UTC), refill_rate=2.0
        )

        status = bucket.get_status()

        assert status["capacity"] == 10
        assert abs(status["tokens"] - 7) < 0.01  # Allow for floating point precision
        assert abs(status["utilization"] - 0.3) < 0.01  # (10-7)/10
        assert status["refill_rate"] == 2.0


class TestRateLimiter:
    """Test rate limiter functionality."""

    @pytest.fixture
    def config(self):
        return create_test_config(
            rate_limit_requests=10,
            rate_limit_window=60,
            rate_limit_burst=20,
            claude_max_cost_per_user=5.0,
        )

    @pytest.fixture
    def rate_limiter(self, config):
        return RateLimiter(config)

    def test_rate_limiter_initialization(self, rate_limiter, config):
        """Test rate limiter initialization."""
        assert rate_limiter.config == config
        assert (
            rate_limiter.refill_rate
            == config.rate_limit_requests / config.rate_limit_window
        )
        assert len(rate_limiter.request_buckets) == 0
        assert len(rate_limiter.cost_tracker) == 0

    async def test_successful_rate_limit_check(self, rate_limiter):
        """Test successful rate limit check."""
        user_id = 123

        # First request should pass
        allowed, message = await rate_limiter.check_rate_limit(
            user_id, cost=0.5, tokens=1
        )
        assert allowed is True
        assert message is None

        # Should have created bucket and tracked cost
        assert user_id in rate_limiter.request_buckets
        assert rate_limiter.cost_tracker[user_id] == 0.5

    async def test_request_rate_limit_exceeded(self, rate_limiter):
        """Test request rate limit exceeded."""
        user_id = 123

        # Consume all tokens
        bucket = rate_limiter._get_or_create_bucket(user_id)
        bucket.tokens = 0

        # Should be rate limited
        allowed, message = await rate_limiter.check_rate_limit(user_id, tokens=1)
        assert allowed is False
        assert "Rate limit exceeded" in message
        assert "wait" in message.lower()

    async def test_cost_limit_exceeded(self, rate_limiter):
        """Test cost limit exceeded."""
        user_id = 123

        # Set cost near limit and set reset time to prevent auto-reset
        rate_limiter.cost_tracker[user_id] = 4.8
        rate_limiter.cost_reset_time[user_id] = datetime.now(UTC)  # Prevent reset

        # Request that would exceed limit
        allowed, message = await rate_limiter.check_rate_limit(user_id, cost=0.5)
        assert allowed is False
        assert "Cost limit exceeded" in message
        assert "Remaining budget" in message

    async def test_cost_tracking(self, rate_limiter):
        """Test cost tracking functionality."""
        user_id = 123

        # Track multiple costs
        await rate_limiter.check_rate_limit(user_id, cost=1.0)
        await rate_limiter.check_rate_limit(user_id, cost=1.5)
        await rate_limiter.check_rate_limit(user_id, cost=0.5)

        assert rate_limiter.cost_tracker[user_id] == 3.0

    async def test_user_limit_reset(self, rate_limiter):
        """Test resetting user limits."""
        user_id = 123

        # Set up some usage
        await rate_limiter.check_rate_limit(user_id, cost=2.0, tokens=5)

        # Verify usage
        assert rate_limiter.cost_tracker[user_id] == 2.0
        bucket = rate_limiter.request_buckets[user_id]
        assert bucket.tokens < bucket.capacity

        # Reset limits
        await rate_limiter.reset_user_limits(user_id)

        # Verify reset
        assert rate_limiter.cost_tracker[user_id] == 0
        assert (
            rate_limiter.request_buckets[user_id].tokens
            == rate_limiter.request_buckets[user_id].capacity
        )

    async def test_cost_tracker_auto_reset(self, rate_limiter):
        """Test automatic cost tracker reset after time period."""
        user_id = 123

        # Set old reset time
        old_time = datetime.now(UTC) - timedelta(days=2)
        rate_limiter.cost_reset_time[user_id] = old_time
        rate_limiter.cost_tracker[user_id] = 3.0

        # Trigger reset check
        rate_limiter._maybe_reset_cost_tracker(user_id)

        # Should have reset
        assert rate_limiter.cost_tracker[user_id] == 0
        assert rate_limiter.cost_reset_time[user_id] > old_time

    async def test_user_status_reporting(self, rate_limiter):
        """Test user status reporting."""
        user_id = 123

        # Set up some usage
        await rate_limiter.check_rate_limit(user_id, cost=2.0, tokens=3)

        status = rate_limiter.get_user_status(user_id)

        assert "request_bucket" in status
        assert "cost_usage" in status
        assert status["cost_usage"]["current"] == 2.0
        assert status["cost_usage"]["remaining"] == 3.0  # 5.0 - 2.0
        assert 0 <= status["cost_usage"]["utilization"] <= 1

    async def test_global_status_reporting(self, rate_limiter):
        """Test global status reporting."""
        # Set up multiple users
        await rate_limiter.check_rate_limit(123, cost=1.0)
        await rate_limiter.check_rate_limit(456, cost=2.0)

        status = rate_limiter.get_global_status()

        assert status["active_users"] == 2
        assert status["total_cost_tracked"] == 3.0
        assert "config" in status
        assert (
            status["config"]["max_cost_per_user"]
            == rate_limiter.config.claude_max_cost_per_user
        )

    async def test_cleanup_inactive_users(self, rate_limiter):
        """Test cleanup of inactive users."""
        user_id = 123

        # Create old bucket
        bucket = rate_limiter._get_or_create_bucket(user_id)
        bucket.last_update = datetime.now(UTC) - timedelta(hours=25)
        rate_limiter.cost_tracker[user_id] = 1.0

        # Cleanup
        cleaned = await rate_limiter.cleanup_inactive_users(timedelta(hours=24))

        assert cleaned == 1
        assert user_id not in rate_limiter.request_buckets
        assert user_id not in rate_limiter.cost_tracker

    async def test_concurrent_access(self, rate_limiter):
        """Test concurrent access to rate limiter."""
        import asyncio

        user_id = 123

        async def make_request():
            return await rate_limiter.check_rate_limit(user_id, cost=0.1, tokens=1)

        # Make multiple concurrent requests
        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed (bucket has enough capacity)
        assert all(result[0] for result in results)

        # Cost should be properly tracked
        expected_cost = 10 * 0.1
        assert abs(rate_limiter.cost_tracker[user_id] - expected_cost) < 0.01

    async def test_bucket_creation_per_user(self, rate_limiter):
        """Test that buckets are created per user."""
        user1, user2 = 123, 456

        # Make requests for different users
        await rate_limiter.check_rate_limit(user1, cost=1.0)
        await rate_limiter.check_rate_limit(user2, cost=2.0)

        # Should have separate buckets and cost tracking
        assert user1 in rate_limiter.request_buckets
        assert user2 in rate_limiter.request_buckets
        assert rate_limiter.cost_tracker[user1] == 1.0
        assert rate_limiter.cost_tracker[user2] == 2.0

    async def test_edge_case_zero_cost(self, rate_limiter):
        """Test handling of zero cost requests."""
        user_id = 123

        allowed, message = await rate_limiter.check_rate_limit(user_id, cost=0.0)
        assert allowed is True
        assert rate_limiter.cost_tracker[user_id] == 0.0

    async def test_edge_case_large_token_request(self, rate_limiter):
        """Test handling of large token requests."""
        user_id = 123

        # Request more tokens than bucket capacity
        bucket = rate_limiter._get_or_create_bucket(user_id)
        large_request = bucket.capacity + 10

        allowed, message = await rate_limiter.check_rate_limit(
            user_id, tokens=large_request
        )
        assert allowed is False
        assert "Rate limit exceeded" in message
