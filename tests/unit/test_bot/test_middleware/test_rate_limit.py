"""Tests for rate limiting middleware."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.bot.middleware.rate_limit import (
    burst_protection_middleware,
    cost_tracking_middleware,
    estimate_message_cost,
    rate_limit_middleware,
)


class TestEstimateMessageCost:
    """Test message cost estimation functionality."""

    def test_text_message_cost(self):
        """Test cost estimation for simple text messages."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = "Hello world"
        event.effective_message.document = None
        event.effective_message.photo = None

        cost = estimate_message_cost(event)

        # Base cost (0.01) + length cost (11 * 0.0001)
        expected = 0.01 + (11 * 0.0001)
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_no_message(self):
        """Test cost estimation when no message present."""
        event = MagicMock()
        event.effective_message = None

        cost = estimate_message_cost(event)

        # Base cost only
        assert cost == pytest.approx(0.01, rel=1e-5)

    def test_message_without_text(self):
        """Test cost estimation for message without text."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = ""  # Empty string instead of None
        event.effective_message.document = None
        event.effective_message.photo = None

        cost = estimate_message_cost(event)

        # Base cost only
        assert cost == pytest.approx(0.01, rel=1e-5)

    def test_file_upload_with_document(self):
        """Test cost estimation for file uploads with document."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = "test"
        event.effective_message.document = MagicMock()  # Has document
        event.effective_message.photo = None

        cost = estimate_message_cost(event)

        # Base (0.01) + length (4 * 0.0001) + file (0.05)
        expected = 0.01 + (4 * 0.0001) + 0.05
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_file_upload_with_photo(self):
        """Test cost estimation for file uploads with photo."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = "test"
        event.effective_message.document = None
        event.effective_message.photo = MagicMock()  # Has photo

        cost = estimate_message_cost(event)

        # Base (0.01) + length (4 * 0.0001) + file (0.05)
        expected = 0.01 + (4 * 0.0001) + 0.05
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_command_message(self):
        """Test cost estimation for command messages."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = "/start"
        event.effective_message.document = None
        event.effective_message.photo = None

        cost = estimate_message_cost(event)

        # Base (0.01) + length (6 * 0.0001) + command (0.02)
        expected = 0.01 + (6 * 0.0001) + 0.02
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_complex_operation_keywords(self):
        """Test cost estimation for messages with complex keywords."""
        complex_keywords = [
            "analyze",
            "generate",
            "create",
            "build",
            "compile",
            "test",
            "debug",
            "refactor",
            "optimize",
            "explain",
        ]

        for keyword in complex_keywords:
            event = MagicMock()
            event.effective_message = MagicMock()
            event.effective_message.text = f"Please {keyword} this code"
            event.effective_message.document = None
            event.effective_message.photo = None

            cost = estimate_message_cost(event)

            # Should include complex operation cost
            text_len = len(f"Please {keyword} this code")
            expected = 0.01 + (text_len * 0.0001) + 0.03
            assert cost == pytest.approx(expected, rel=1e-5)

    def test_complex_keyword_case_insensitive(self):
        """Test that complex keywords are detected case-insensitively."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = "Please ANALYZE this"
        event.effective_message.document = None
        event.effective_message.photo = None

        cost = estimate_message_cost(event)

        # Should include complex operation cost
        expected = 0.01 + (19 * 0.0001) + 0.03
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_command_with_complex_keyword(self):
        """Test that command cost takes precedence over complex keyword."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = "/analyze something"
        event.effective_message.document = None
        event.effective_message.photo = None

        cost = estimate_message_cost(event)

        # Command cost (0.02) should be applied, not complex keyword cost
        expected = 0.01 + (18 * 0.0001) + 0.02
        assert cost == pytest.approx(expected, rel=1e-5)

    def test_file_upload_with_command(self):
        """Test that file upload cost takes precedence."""
        event = MagicMock()
        event.effective_message = MagicMock()
        event.effective_message.text = "/upload"
        event.effective_message.document = MagicMock()
        event.effective_message.photo = None

        cost = estimate_message_cost(event)

        # File upload cost (0.05) should be applied
        expected = 0.01 + (7 * 0.0001) + 0.05
        assert cost == pytest.approx(expected, rel=1e-5)


class TestRateLimitMiddleware:
    """Test rate limiting middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_user.username = "test_user"
        event.effective_message = MagicMock()
        event.effective_message.text = "test message"
        event.effective_message.document = None
        event.effective_message.photo = None
        event.effective_message.reply_text = AsyncMock()
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        rate_limiter = MagicMock()
        rate_limiter.check_rate_limit = AsyncMock(return_value=(True, ""))
        return rate_limiter

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        audit_logger = MagicMock()
        audit_logger.log_rate_limit_exceeded = AsyncMock()
        return audit_logger

    @pytest.fixture
    def mock_data(self, mock_rate_limiter, mock_audit_logger):
        """Create mock data dictionary."""
        return {
            "rate_limiter": mock_rate_limiter,
            "audit_logger": mock_audit_logger,
        }

    async def test_no_user_information(self, mock_handler, mock_data):
        """Test middleware with no user information."""
        event = MagicMock()
        event.effective_user = None

        result = await rate_limit_middleware(mock_handler, event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once_with(event, mock_data)
        mock_data["rate_limiter"].check_rate_limit.assert_not_called()

    async def test_no_rate_limiter(self, mock_event, mock_handler):
        """Test middleware when rate limiter is not available."""
        data = {}

        result = await rate_limit_middleware(mock_handler, mock_event, data)

        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_event, data)

    async def test_rate_limit_not_exceeded(self, mock_event, mock_handler, mock_data):
        """Test middleware when rate limit is not exceeded."""
        result = await rate_limit_middleware(mock_handler, mock_event, mock_data)

        assert result == "handler_result"
        mock_data["rate_limiter"].check_rate_limit.assert_called_once()
        call_kwargs = mock_data["rate_limiter"].check_rate_limit.call_args.kwargs
        assert call_kwargs["user_id"] == 12345
        assert call_kwargs["tokens"] == 1
        assert "cost" in call_kwargs
        mock_handler.assert_called_once_with(mock_event, mock_data)
        mock_event.effective_message.reply_text.assert_not_called()

    async def test_rate_limit_exceeded(self, mock_event, mock_handler, mock_data):
        """Test middleware when rate limit is exceeded."""
        mock_data["rate_limiter"].check_rate_limit.return_value = (
            False,
            "Rate limit exceeded",
        )

        result = await rate_limit_middleware(mock_handler, mock_event, mock_data)

        assert result is None
        mock_data["rate_limiter"].check_rate_limit.assert_called_once()
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Rate limit exceeded" in call_args
        mock_handler.assert_not_called()

    async def test_rate_limit_exceeded_logs_audit(
        self, mock_event, mock_handler, mock_data
    ):
        """Test that rate limit violations are logged."""
        mock_data["rate_limiter"].check_rate_limit.return_value = (
            False,
            "Too many requests",
        )

        result = await rate_limit_middleware(mock_handler, mock_event, mock_data)

        assert result is None
        mock_data["audit_logger"].log_rate_limit_exceeded.assert_called_once()
        call_kwargs = mock_data["audit_logger"].log_rate_limit_exceeded.call_args.kwargs
        assert call_kwargs["user_id"] == 12345
        assert call_kwargs["limit_type"] == "combined"

    async def test_rate_limit_exceeded_no_audit_logger(
        self, mock_event, mock_handler, mock_rate_limiter
    ):
        """Test rate limit exceeded without audit logger."""
        data = {"rate_limiter": mock_rate_limiter, "audit_logger": None}
        mock_rate_limiter.check_rate_limit.return_value = (False, "Rate limit exceeded")

        result = await rate_limit_middleware(mock_handler, mock_event, data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_rate_limit_exceeded_no_message(
        self, mock_handler, mock_data
    ):
        """Test rate limit exceeded without message to reply to."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_user.username = "test_user"
        event.effective_message = None

        mock_data["rate_limiter"].check_rate_limit.return_value = (
            False,
            "Rate limit exceeded",
        )

        result = await rate_limit_middleware(mock_handler, event, mock_data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_user_without_username(self, mock_handler, mock_data):
        """Test middleware with user without username."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        del event.effective_user.username
        event.effective_message = MagicMock()
        event.effective_message.text = "test"
        event.effective_message.document = None
        event.effective_message.photo = None

        result = await rate_limit_middleware(mock_handler, event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once()


class TestCostTrackingMiddleware:
    """Test cost tracking middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.from_user = MagicMock()
        event.from_user.id = 12345
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        return MagicMock()

    async def test_successful_handler_execution(
        self, mock_event, mock_handler, mock_rate_limiter
    ):
        """Test cost tracking with successful handler execution."""
        data = {"rate_limiter": mock_rate_limiter}

        with patch("time.time") as mock_time:
            mock_time.side_effect = [100.0, 100.5]  # Start and end times

            result = await cost_tracking_middleware(mock_handler, mock_event, data)

            assert result == "handler_result"
            mock_handler.assert_called_once_with(mock_event, data)

    async def test_handler_execution_with_actual_cost(
        self, mock_event, mock_handler, mock_rate_limiter
    ):
        """Test cost tracking when actual cost is provided."""
        data = {"rate_limiter": mock_rate_limiter, "actual_cost": 0.15}

        with patch("time.time") as mock_time:
            mock_time.side_effect = [100.0, 100.5]

            result = await cost_tracking_middleware(mock_handler, mock_event, data)

            assert result == "handler_result"
            mock_handler.assert_called_once()

    async def test_handler_execution_without_rate_limiter(
        self, mock_event, mock_handler
    ):
        """Test cost tracking without rate limiter."""
        data = {}

        with patch("time.time") as mock_time:
            mock_time.side_effect = [100.0, 100.5]

            result = await cost_tracking_middleware(mock_handler, mock_event, data)

            assert result == "handler_result"
            mock_handler.assert_called_once()

    async def test_handler_execution_with_zero_cost(
        self, mock_event, mock_handler, mock_rate_limiter
    ):
        """Test cost tracking with zero actual cost."""
        data = {"rate_limiter": mock_rate_limiter, "actual_cost": 0.0}

        with patch("time.time") as mock_time:
            mock_time.side_effect = [100.0, 100.5]

            result = await cost_tracking_middleware(mock_handler, mock_event, data)

            assert result == "handler_result"
            mock_handler.assert_called_once()

    async def test_handler_execution_failure(
        self, mock_event, mock_rate_limiter
    ):
        """Test cost tracking when handler raises exception."""
        handler = AsyncMock()
        handler.side_effect = ValueError("Test error")
        data = {"rate_limiter": mock_rate_limiter}

        with patch("time.time") as mock_time:
            mock_time.side_effect = [100.0, 100.5]

            with pytest.raises(ValueError, match="Test error"):
                await cost_tracking_middleware(handler, mock_event, data)

            handler.assert_called_once()


class TestBurstProtectionMiddleware:
    """Test burst protection middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.from_user = MagicMock()
        event.from_user.id = 12345
        event.effective_message = MagicMock()
        event.effective_message.reply_text = AsyncMock()
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    async def test_normal_request_rate(self, mock_event, mock_handler):
        """Test middleware with normal request rate."""
        data = {}

        with patch("time.time", return_value=100.0):
            result = await burst_protection_middleware(mock_handler, mock_event, data)

            assert result == "handler_result"
            mock_handler.assert_called_once_with(mock_event, data)
            mock_event.effective_message.reply_text.assert_not_called()

    async def test_burst_detection_first_warning(self, mock_event, mock_handler):
        """Test burst detection and first warning."""
        data = {}

        # Simulate 6 rapid requests
        with patch("time.time") as mock_time:
            for i in range(6):
                mock_time.return_value = 100.0 + i * 0.1
                result = await burst_protection_middleware(
                    mock_handler, mock_event, data
                )

                if i < 5:
                    # First 5 requests should succeed
                    assert result == "handler_result"
                else:
                    # 6th request triggers first warning but still processes
                    assert "burst_tracker" in data
                    assert data["burst_tracker"][12345]["warnings_sent"] == 1

        # Check that warning was sent
        mock_event.effective_message.reply_text.assert_called()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Slow down" in call_args

    async def test_burst_detection_second_warning(self, mock_event, mock_handler):
        """Test second burst warning."""
        data = {}

        # Simulate rapid requests to trigger second warning
        with patch("time.time") as mock_time:
            # First burst (6 requests)
            for i in range(6):
                mock_time.return_value = 100.0 + i * 0.1
                await burst_protection_middleware(mock_handler, mock_event, data)

            # Reset mock to check next call
            mock_event.effective_message.reply_text.reset_mock()

            # Another request to trigger second warning
            mock_time.return_value = 100.7
            await burst_protection_middleware(mock_handler, mock_event, data)

        assert data["burst_tracker"][12345]["warnings_sent"] == 2
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Rate limit warning" in call_args

    async def test_burst_detection_third_warning(self, mock_event, mock_handler):
        """Test third burst warning."""
        data = {}

        with patch("time.time") as mock_time:
            # Trigger multiple warnings
            for i in range(8):
                mock_time.return_value = 100.0 + i * 0.1
                await burst_protection_middleware(mock_handler, mock_event, data)

        assert data["burst_tracker"][12345]["warnings_sent"] == 3
        # Should still show warning message
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Rate limit warning" in call_args

    async def test_burst_detection_block(self, mock_event, mock_handler):
        """Test that excessive burst results in blocking."""
        data = {}

        with patch("time.time") as mock_time:
            # Trigger enough warnings to block
            for i in range(10):
                mock_time.return_value = 100.0 + i * 0.1
                result = await burst_protection_middleware(
                    mock_handler, mock_event, data
                )

        # Last request should be blocked
        assert result is None
        assert data["burst_tracker"][12345]["warnings_sent"] > 3
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Temporarily blocked" in call_args

    async def test_old_requests_cleanup(self, mock_event, mock_handler):
        """Test that old requests are cleaned up."""
        data = {}

        with patch("time.time") as mock_time:
            # First request at t=100
            mock_time.return_value = 100.0
            await burst_protection_middleware(mock_handler, mock_event, data)

            # Second request at t=111 (11 seconds later, outside 10s window)
            mock_time.return_value = 111.0
            await burst_protection_middleware(mock_handler, mock_event, data)

            # Should only have 1 request in recent_requests
            assert len(data["burst_tracker"][12345]["recent_requests"]) == 1
            assert data["burst_tracker"][12345]["recent_requests"][0] == 111.0

    async def test_multiple_users_tracking(self, mock_handler):
        """Test that burst tracking works independently for multiple users."""
        data = {}

        event1 = MagicMock()
        event1.from_user = MagicMock()
        event1.from_user.id = 11111
        event1.effective_message = MagicMock()
        event1.effective_message.reply_text = AsyncMock()

        event2 = MagicMock()
        event2.from_user = MagicMock()
        event2.from_user.id = 22222
        event2.effective_message = MagicMock()
        event2.effective_message.reply_text = AsyncMock()

        with patch("time.time", return_value=100.0):
            # User 1 makes requests
            for _ in range(3):
                await burst_protection_middleware(mock_handler, event1, data)

            # User 2 makes requests
            for _ in range(3):
                await burst_protection_middleware(mock_handler, event2, data)

        # Both users should have independent tracking
        assert 11111 in data["burst_tracker"]
        assert 22222 in data["burst_tracker"]
        assert len(data["burst_tracker"][11111]["recent_requests"]) == 3
        assert len(data["burst_tracker"][22222]["recent_requests"]) == 3

    async def test_burst_without_message(self, mock_handler):
        """Test burst protection when no message object is available."""
        event = MagicMock()
        event.from_user = MagicMock()
        event.from_user.id = 12345
        event.effective_message = None
        data = {}

        with patch("time.time") as mock_time:
            # Trigger burst
            for i in range(7):
                mock_time.return_value = 100.0 + i * 0.1
                result = await burst_protection_middleware(mock_handler, event, data)

        # Should still track but not send messages
        assert data["burst_tracker"][12345]["warnings_sent"] > 0
