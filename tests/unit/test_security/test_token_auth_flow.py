"""End-to-end integration tests for token auth flow.

Simulates the exact sequence a user would experience:
  1. Admin (whitelisted) runs ``/auth generate <user_id>``.
  2. Target user (NOT whitelisted, NOT in users table) sends
     ``/auth <token>`` — goes through ``auth_middleware``.
  3. Target user sends a follow-up message — should be recognised as
     authenticated without re-presenting the token.
  4. Admin re-runs ``/auth generate <user_id>`` — should succeed
     (regression against an earlier FK-constraint bug).
"""

import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.middleware.auth import auth_middleware
from src.security.auth import (
    AuthenticationManager,
    SqliteTokenStorage,
    TokenAuthProvider,
    WhitelistAuthProvider,
)
from src.storage.database import DatabaseManager
from src.storage.repositories import TokenRepository


@pytest.fixture
async def db_manager():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        mgr = DatabaseManager(f"sqlite:///{f.name}")
        await mgr.initialize()
        # Only the admin exists up front — target user is brand-new.
        async with mgr.get_connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (405,)
            )
            await conn.commit()
        yield mgr
        await mgr.close()


@pytest.fixture
async def auth_setup(db_manager):
    """Build a realistic auth_manager with both providers."""
    repo = TokenRepository(db_manager)
    storage = SqliteTokenStorage(repo)
    token_provider = TokenAuthProvider("test_secret", storage)
    auth_manager = AuthenticationManager([WhitelistAuthProvider([405]), token_provider])
    return auth_manager, token_provider


def _make_event(user_id: int, text: str) -> MagicMock:
    event = MagicMock()
    event.effective_user.id = user_id
    event.effective_user.username = "test"
    event.effective_user.is_bot = False
    event.effective_message.text = text
    event.effective_message.reply_text = AsyncMock()
    return event


# ---------------------------------------------------------------------------
# End-to-end flow
# ---------------------------------------------------------------------------


class TestTokenAuthEndToEnd:
    async def test_full_flow_new_user(self, auth_setup):
        """The scenario the user reported: brand-new target, full round trip."""
        auth_manager, token_provider = auth_setup

        # 1. Admin generates a token for user 123 (who has never touched the bot).
        token = await token_provider.generate_token(123)
        assert token

        # 2. User 123 sends ``/auth <token>`` through the middleware.
        data = {"auth_manager": auth_manager, "audit_logger": None}
        handler_called = [False]

        async def handler(event, data):
            handler_called[0] = True

        auth_event = _make_event(123, f"/auth {token}")
        await auth_middleware(handler, auth_event, data)

        assert handler_called[0], "Middleware should have let /auth <token> through"
        assert auth_manager.is_authenticated(123), "Session must be created"

        # 3. User 123 sends a plain follow-up message. It must pass auth.
        handler_called[0] = False
        followup = _make_event(123, "hello world")
        await auth_middleware(handler, followup, data)

        assert handler_called[
            0
        ], "Authenticated user should be allowed through on subsequent messages"
        assert auth_manager.is_authenticated(123)

        # 4. Admin regenerates the token for the same user — no error.
        token2 = await token_provider.generate_token(123)
        assert token2 != token
        # Old token no longer authenticates.
        assert await token_provider.authenticate(123, {"token": token}) is False
        # New token does.
        assert await token_provider.authenticate(123, {"token": token2}) is True

    async def test_wrong_token_rejects(self, auth_setup):
        auth_manager, token_provider = auth_setup
        await token_provider.generate_token(123)

        data = {"auth_manager": auth_manager, "audit_logger": None}
        handler_called = [False]

        async def handler(event, data):
            handler_called[0] = True

        event = _make_event(123, "/auth totally-wrong-token")
        await auth_middleware(handler, event, data)

        assert not handler_called[0]
        assert not auth_manager.is_authenticated(123)

    async def test_subcommand_not_treated_as_token(self, auth_setup):
        """``/auth generate 999`` from admin must not be passed as a token."""
        auth_manager, token_provider = auth_setup

        data = {"auth_manager": auth_manager, "audit_logger": None}
        handler_called = [False]

        async def handler(event, data):
            handler_called[0] = True

        # Admin is whitelisted, so middleware should let them through.
        event = _make_event(405, "/auth generate 999")
        await auth_middleware(handler, event, data)

        assert handler_called[0]
        assert auth_manager.is_authenticated(405)

    async def test_bare_auth_no_token_rejects_new_user(self, auth_setup):
        """``/auth`` alone (no token) from a new user must not authenticate."""
        auth_manager, _ = auth_setup

        data = {"auth_manager": auth_manager, "audit_logger": None}
        handler_called = [False]

        async def handler(event, data):
            handler_called[0] = True

        event = _make_event(999, "/auth")
        await auth_middleware(handler, event, data)

        assert not handler_called[0]
        assert not auth_manager.is_authenticated(999)
