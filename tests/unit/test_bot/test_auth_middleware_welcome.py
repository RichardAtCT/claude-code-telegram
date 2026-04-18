"""Regression tests for auth middleware's welcome message behavior.

When a user runs an /auth command while not authenticated, the middleware
authenticates them (possibly via whitelist or token). Historically it then
sent a "Welcome! You are now authenticated." message, which collides with
the command handler's own response (e.g. "Token revoked for user 123").

The fix: suppress the welcome message for /auth commands so the handler's
operation-specific response stands alone.
"""

from unittest.mock import AsyncMock, MagicMock

from src.bot.middleware.auth import auth_middleware


def _make_event(text: str, user_id: int = 123) -> MagicMock:
    event = MagicMock()
    event.effective_user = MagicMock()
    event.effective_user.id = user_id
    event.effective_user.username = "tester"
    event.effective_message = MagicMock()
    event.effective_message.text = text
    event.effective_message.reply_text = AsyncMock()
    return event


def _make_data(authenticated: bool = False) -> dict:
    auth_manager = MagicMock()
    auth_manager.is_authenticated.return_value = authenticated
    auth_manager.authenticate_user = AsyncMock(return_value=True)
    session = MagicMock()
    session.auth_provider = "WhitelistAuthProvider"
    auth_manager.get_session.return_value = session
    return {"auth_manager": auth_manager, "audit_logger": None}


async def _noop_handler(event, data):
    return None


class TestWelcomeSuppression:
    async def test_auth_command_suppresses_welcome(self):
        """/auth ... should NOT trigger the 'Welcome!' message."""
        event = _make_event("/auth revoke 123")
        data = _make_data(authenticated=False)

        await auth_middleware(_noop_handler, event, data)

        # reply_text should NOT have been called with "Welcome!"
        welcome_calls = [
            c
            for c in event.effective_message.reply_text.call_args_list
            if "Welcome" in str(c)
        ]
        assert welcome_calls == []

    async def test_auth_bare_command_suppresses_welcome(self):
        """Bare /auth should also suppress welcome."""
        event = _make_event("/auth")
        data = _make_data(authenticated=False)

        await auth_middleware(_noop_handler, event, data)

        welcome_calls = [
            c
            for c in event.effective_message.reply_text.call_args_list
            if "Welcome" in str(c)
        ]
        assert welcome_calls == []

    async def test_auth_token_subcommand_suppresses_welcome(self):
        """/auth <token> should suppress welcome — handler will respond."""
        event = _make_event("/auth some_token_here")
        data = _make_data(authenticated=False)

        await auth_middleware(_noop_handler, event, data)

        welcome_calls = [
            c
            for c in event.effective_message.reply_text.call_args_list
            if "Welcome" in str(c)
        ]
        assert welcome_calls == []

    async def test_regular_message_still_shows_welcome(self):
        """Non-/auth messages still get the 'Welcome!' on first auth."""
        event = _make_event("hello")
        data = _make_data(authenticated=False)

        await auth_middleware(_noop_handler, event, data)

        welcome_calls = [
            c
            for c in event.effective_message.reply_text.call_args_list
            if "Welcome" in str(c)
        ]
        assert len(welcome_calls) == 1

    async def test_auth_like_prefix_still_shows_welcome(self):
        """A message like '/authorize' (not an /auth command) still gets welcome."""
        event = _make_event("/authorize me")
        data = _make_data(authenticated=False)

        await auth_middleware(_noop_handler, event, data)

        welcome_calls = [
            c
            for c in event.effective_message.reply_text.call_args_list
            if "Welcome" in str(c)
        ]
        assert len(welcome_calls) == 1
