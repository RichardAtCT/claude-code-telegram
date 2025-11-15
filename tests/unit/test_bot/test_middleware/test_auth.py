"""Tests for authentication middleware."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from src.bot.middleware.auth import admin_required, auth_middleware, require_auth


class TestAuthMiddleware:
    """Test authentication middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_user.username = "test_user"
        event.effective_message = MagicMock()
        event.effective_message.reply_text = AsyncMock()
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    @pytest.fixture
    def mock_auth_manager(self):
        """Create a mock authentication manager."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated = Mock(return_value=False)
        auth_manager.refresh_session = Mock(return_value=False)
        auth_manager.get_session = Mock(return_value=None)
        auth_manager.authenticate_user = AsyncMock(return_value=False)
        return auth_manager

    @pytest.fixture
    def mock_audit_logger(self):
        """Create a mock audit logger."""
        audit_logger = MagicMock()
        audit_logger.log_auth_attempt = AsyncMock()
        return audit_logger

    @pytest.fixture
    def mock_data(self, mock_auth_manager, mock_audit_logger):
        """Create mock data dictionary."""
        return {
            "auth_manager": mock_auth_manager,
            "audit_logger": mock_audit_logger,
        }

    async def test_no_user_information(self, mock_handler):
        """Test middleware with no user information."""
        event = MagicMock()
        event.effective_user = None
        data = {"auth_manager": MagicMock()}

        result = await auth_middleware(mock_handler, event, data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_no_auth_manager(self, mock_event, mock_handler):
        """Test middleware when auth manager is not available."""
        data = {}

        result = await auth_middleware(mock_handler, event=mock_event, data=data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Authentication system unavailable" in call_args
        mock_handler.assert_not_called()

    async def test_no_auth_manager_no_message(self, mock_handler):
        """Test middleware when auth manager is not available and no message."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = None
        data = {}

        result = await auth_middleware(mock_handler, event=event, data=data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_authenticated_user_with_session_refresh(
        self, mock_event, mock_handler, mock_data
    ):
        """Test middleware with already authenticated user and successful refresh."""
        mock_auth_manager = mock_data["auth_manager"]
        mock_auth_manager.is_authenticated.return_value = True
        mock_auth_manager.refresh_session.return_value = True

        mock_session = MagicMock()
        mock_session.auth_provider = "whitelist"
        mock_auth_manager.get_session.return_value = mock_session

        result = await auth_middleware(mock_handler, mock_event, mock_data)

        assert result == "handler_result"
        mock_auth_manager.is_authenticated.assert_called_once_with(12345)
        mock_auth_manager.refresh_session.assert_called_once_with(12345)
        mock_handler.assert_called_once_with(mock_event, mock_data)

    async def test_authenticated_user_no_session_refresh(
        self, mock_event, mock_handler, mock_data
    ):
        """Test middleware with authenticated user but failed session refresh."""
        mock_auth_manager = mock_data["auth_manager"]
        mock_auth_manager.is_authenticated.return_value = True
        mock_auth_manager.refresh_session.return_value = False

        result = await auth_middleware(mock_handler, mock_event, mock_data)

        assert result == "handler_result"
        mock_auth_manager.is_authenticated.assert_called_once_with(12345)
        mock_auth_manager.refresh_session.assert_called_once_with(12345)
        mock_handler.assert_called_once_with(mock_event, mock_data)

    async def test_authenticated_user_without_username(
        self, mock_handler, mock_data
    ):
        """Test authenticated user without username attribute."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        # Don't set username attribute at all
        del event.effective_user.username
        event.effective_message = MagicMock()

        mock_auth_manager = mock_data["auth_manager"]
        mock_auth_manager.is_authenticated.return_value = True

        result = await auth_middleware(mock_handler, event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once()

    async def test_successful_authentication(self, mock_event, mock_handler, mock_data):
        """Test successful authentication for unauthenticated user."""
        mock_auth_manager = mock_data["auth_manager"]
        mock_auth_manager.is_authenticated.return_value = False
        mock_auth_manager.authenticate_user.return_value = True

        mock_session = MagicMock()
        mock_session.auth_provider = "token"
        mock_auth_manager.get_session.return_value = mock_session

        result = await auth_middleware(mock_handler, mock_event, mock_data)

        assert result == "handler_result"
        mock_auth_manager.authenticate_user.assert_called_once_with(12345)
        mock_data["audit_logger"].log_auth_attempt.assert_called_once_with(
            user_id=12345,
            success=True,
            method="automatic",
            reason="message_received",
        )
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Welcome" in call_args
        mock_handler.assert_called_once_with(mock_event, mock_data)

    async def test_successful_authentication_no_session(
        self, mock_event, mock_handler, mock_data
    ):
        """Test successful authentication but no session object."""
        mock_auth_manager = mock_data["auth_manager"]
        mock_auth_manager.is_authenticated.return_value = False
        mock_auth_manager.authenticate_user.return_value = True
        mock_auth_manager.get_session.return_value = None

        result = await auth_middleware(mock_handler, mock_event, mock_data)

        assert result == "handler_result"
        mock_handler.assert_called_once()

    async def test_failed_authentication(self, mock_event, mock_handler, mock_data):
        """Test failed authentication attempt."""
        mock_auth_manager = mock_data["auth_manager"]
        mock_auth_manager.is_authenticated.return_value = False
        mock_auth_manager.authenticate_user.return_value = False

        result = await auth_middleware(mock_handler, mock_event, mock_data)

        assert result is None
        mock_auth_manager.authenticate_user.assert_called_once_with(12345)
        mock_data["audit_logger"].log_auth_attempt.assert_called_once_with(
            user_id=12345,
            success=False,
            method="automatic",
            reason="message_received",
        )
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Authentication Required" in call_args
        assert "12345" in call_args
        mock_handler.assert_not_called()

    async def test_failed_authentication_no_message(self, mock_handler, mock_data):
        """Test failed authentication without message to reply to."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_user.username = "test_user"
        event.effective_message = None

        mock_auth_manager = mock_data["auth_manager"]
        mock_auth_manager.is_authenticated.return_value = False
        mock_auth_manager.authenticate_user.return_value = False

        result = await auth_middleware(mock_handler, event, mock_data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_authentication_without_audit_logger(
        self, mock_event, mock_handler, mock_auth_manager
    ):
        """Test authentication flow when audit logger is not available."""
        data = {"auth_manager": mock_auth_manager, "audit_logger": None}
        mock_auth_manager.is_authenticated.return_value = False
        mock_auth_manager.authenticate_user.return_value = False

        result = await auth_middleware(mock_handler, mock_event, data)

        assert result is None
        mock_auth_manager.authenticate_user.assert_called_once()
        mock_handler.assert_not_called()


class TestRequireAuthMiddleware:
    """Test require_auth middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = MagicMock()
        event.effective_message.reply_text = AsyncMock()
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    async def test_no_user_information(self, mock_handler):
        """Test require_auth with no user information."""
        event = MagicMock()
        event.effective_user = None
        event.effective_message = MagicMock()
        event.effective_message.reply_text = AsyncMock()

        auth_manager = MagicMock()
        auth_manager.is_authenticated = Mock(return_value=False)
        data = {"auth_manager": auth_manager}

        result = await require_auth(mock_handler, event, data)

        assert result is None
        event.effective_message.reply_text.assert_called_once()
        call_args = event.effective_message.reply_text.call_args[0][0]
        assert "Authentication required" in call_args
        mock_handler.assert_not_called()

    async def test_no_auth_manager(self, mock_event, mock_handler):
        """Test require_auth when auth manager is not available."""
        data = {}

        result = await require_auth(mock_handler, mock_event, data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        mock_handler.assert_not_called()

    async def test_authenticated_user(self, mock_event, mock_handler):
        """Test require_auth with authenticated user."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = True
        data = {"auth_manager": auth_manager}

        result = await require_auth(mock_handler, mock_event, data)

        assert result == "handler_result"
        auth_manager.is_authenticated.assert_called_once_with(12345)
        mock_handler.assert_called_once_with(mock_event, data)
        mock_event.effective_message.reply_text.assert_not_called()

    async def test_unauthenticated_user(self, mock_event, mock_handler):
        """Test require_auth with unauthenticated user."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = False
        data = {"auth_manager": auth_manager}

        result = await require_auth(mock_handler, mock_event, data)

        assert result is None
        auth_manager.is_authenticated.assert_called_once_with(12345)
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Authentication required" in call_args
        mock_handler.assert_not_called()

    async def test_unauthenticated_user_no_message(self, mock_handler):
        """Test require_auth with unauthenticated user and no message."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = None

        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = False
        data = {"auth_manager": auth_manager}

        result = await require_auth(mock_handler, event, data)

        assert result is None
        mock_handler.assert_not_called()


class TestAdminRequiredMiddleware:
    """Test admin_required middleware functionality."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Telegram event/update."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = MagicMock()
        event.effective_message.reply_text = AsyncMock()
        return event

    @pytest.fixture
    def mock_handler(self):
        """Create a mock handler function."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    async def test_no_user_information(self, mock_handler):
        """Test admin_required with no user information."""
        event = MagicMock()
        event.effective_user = None
        event.effective_message = MagicMock()
        event.effective_message.reply_text = AsyncMock()

        auth_manager = MagicMock()
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, event, data)

        assert result is None
        event.effective_message.reply_text.assert_called_once()
        mock_handler.assert_not_called()

    async def test_no_auth_manager(self, mock_event, mock_handler):
        """Test admin_required when auth manager is not available."""
        data = {}

        result = await admin_required(mock_handler, mock_event, data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        mock_handler.assert_not_called()

    async def test_unauthenticated_user(self, mock_event, mock_handler):
        """Test admin_required with unauthenticated user."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = False
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, mock_event, data)

        assert result is None
        auth_manager.is_authenticated.assert_called_once_with(12345)
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Authentication required" in call_args
        mock_handler.assert_not_called()

    async def test_authenticated_user_no_session(self, mock_event, mock_handler):
        """Test admin_required with authenticated user but no session."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = True
        auth_manager.get_session.return_value = None
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, mock_event, data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Session information unavailable" in call_args
        mock_handler.assert_not_called()

    async def test_authenticated_user_no_user_info(self, mock_event, mock_handler):
        """Test admin_required with session but no user_info."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = True
        mock_session = MagicMock()
        mock_session.user_info = None
        auth_manager.get_session.return_value = mock_session
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, mock_event, data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Session information unavailable" in call_args
        mock_handler.assert_not_called()

    async def test_authenticated_user_not_admin(self, mock_event, mock_handler):
        """Test admin_required with authenticated non-admin user."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = True
        mock_session = MagicMock()
        mock_session.user_info = {"permissions": ["user", "read"]}
        auth_manager.get_session.return_value = mock_session
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, mock_event, data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Admin Access Required" in call_args
        mock_handler.assert_not_called()

    async def test_authenticated_user_no_permissions(self, mock_event, mock_handler):
        """Test admin_required with authenticated user without permissions."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = True
        mock_session = MagicMock()
        mock_session.user_info = {"name": "test"}  # Has user_info but no permissions key
        auth_manager.get_session.return_value = mock_session
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, mock_event, data)

        assert result is None
        mock_event.effective_message.reply_text.assert_called_once()
        call_args = mock_event.effective_message.reply_text.call_args[0][0]
        assert "Admin Access Required" in call_args
        mock_handler.assert_not_called()

    async def test_authenticated_admin_user(self, mock_event, mock_handler):
        """Test admin_required with authenticated admin user."""
        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = True
        mock_session = MagicMock()
        mock_session.user_info = {"permissions": ["user", "admin", "read"]}
        auth_manager.get_session.return_value = mock_session
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, mock_event, data)

        assert result == "handler_result"
        auth_manager.is_authenticated.assert_called_once_with(12345)
        auth_manager.get_session.assert_called_once_with(12345)
        mock_handler.assert_called_once_with(mock_event, data)
        mock_event.effective_message.reply_text.assert_not_called()

    async def test_admin_user_no_message(self, mock_handler):
        """Test admin_required with admin user but no message object."""
        event = MagicMock()
        event.effective_user = MagicMock()
        event.effective_user.id = 12345
        event.effective_message = None

        auth_manager = MagicMock()
        auth_manager.is_authenticated.return_value = True
        mock_session = MagicMock()
        mock_session.user_info = {"permissions": ["admin"]}
        auth_manager.get_session.return_value = mock_session
        data = {"auth_manager": auth_manager}

        result = await admin_required(mock_handler, event, data)

        assert result == "handler_result"
        mock_handler.assert_called_once()
