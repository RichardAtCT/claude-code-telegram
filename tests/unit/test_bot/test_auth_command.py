"""Tests for the /auth command handler."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.orchestrator import MessageOrchestrator
from src.config import create_test_config
from src.security.auth import InMemoryTokenStorage, TokenAuthProvider


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def token_provider():
    storage = InMemoryTokenStorage()
    return TokenAuthProvider("test_secret", storage)


@pytest.fixture
def settings(tmp_dir):
    return create_test_config(
        approved_directory=str(tmp_dir),
        agentic_mode=True,
        enable_token_auth=True,
        auth_token_secret="test_secret",
    )


@pytest.fixture
def deps(token_provider):
    return {
        "claude_integration": MagicMock(),
        "storage": MagicMock(),
        "security_validator": MagicMock(),
        "rate_limiter": MagicMock(),
        "audit_logger": None,
        "token_auth_provider": token_provider,
        "auth_manager": MagicMock(),
    }


def _make_update(user_id: int = 123, text: str = "/auth") -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _make_context(deps: dict, settings: object) -> MagicMock:
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.bot_data = {**deps, "settings": settings}
    return ctx


# ---------------------------------------------------------------------------
# /auth status
# ---------------------------------------------------------------------------


class TestAuthStatus:
    async def test_status_not_authenticated(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(text="/auth status")
        deps["auth_manager"].is_authenticated.return_value = False
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Not authenticated" in text

    async def test_status_authenticated(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(text="/auth status")
        deps["auth_manager"].is_authenticated.return_value = True
        session = MagicMock()
        session.auth_provider = "token"
        deps["auth_manager"].get_session.return_value = session
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Authenticated" in text

    async def test_bare_auth_shows_status(self, settings, deps):
        """'/auth' with no args shows status."""
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(text="/auth")
        deps["auth_manager"].is_authenticated.return_value = False
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Not authenticated" in text


# ---------------------------------------------------------------------------
# /auth generate
# ---------------------------------------------------------------------------


class TestAuthGenerate:
    async def test_generate_as_admin(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        # The test config has allowed_users=[12345] by default
        update = _make_update(
            user_id=settings.allowed_users[0],
            text="/auth generate 999",
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Token generated" in text
        assert "999" in text

    async def test_generate_rejected_for_non_admin(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=77777, text="/auth generate 999")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Admin" in text

    async def test_generate_missing_user_id(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0],
            text="/auth generate",
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text


# ---------------------------------------------------------------------------
# /auth revoke
# ---------------------------------------------------------------------------


class TestAuthRevoke:
    async def test_revoke_as_admin_with_active_token(
        self, settings, deps, token_provider
    ):
        """Revoke when the target actually has an active token."""
        await token_provider.generate_token(999)

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0],
            text="/auth revoke 999",
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "revoked" in text.lower()
        assert "no active token" not in text.lower()

        # Verify token is actually revoked
        assert await token_provider.authenticate(999, {"token": "any"}) is False

    async def test_revoke_user_without_token(self, settings, deps, token_provider):
        """Revoke for a user who has no token should report it clearly."""
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0],
            text="/auth revoke 12345",  # Never had a token
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "no active token" in text.lower()
        # Must NOT claim it was revoked
        assert "revoked" not in text.lower()

    async def test_revoke_rejected_for_non_admin(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=77777, text="/auth revoke 999")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Admin" in text


# ---------------------------------------------------------------------------
# /auth <token> (passthrough — middleware handles actual auth)
# ---------------------------------------------------------------------------


class TestAuthToken:
    async def test_token_user_gets_token_specific_message(self, settings, deps):
        """External user authenticated via token sees a token-specific message."""
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=99999, text="/auth some_random_token_value")

        session = MagicMock()
        session.auth_provider = "TokenAuthProvider"
        deps["auth_manager"].get_session.return_value = session

        ctx = _make_context(deps, settings)
        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "token" in text.lower()
        assert "Welcome" in text or "Authenticated" in text

    async def test_admin_garbage_shows_help_not_success(self, settings, deps):
        """Admin typing an unknown subcommand sees help, not a misleading success."""
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0],
            text="/auth xyz 123",  # "xyz" is not a known subcommand
        )

        session = MagicMock()
        session.auth_provider = "WhitelistAuthProvider"
        deps["auth_manager"].get_session.return_value = session

        ctx = _make_context(deps, settings)
        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        # Should NOT claim success
        assert "Authenticated successfully" not in text
        # Should hint at known subcommands — primary ones (add/remove) always listed
        assert "add" in text
        assert "remove" in text
        # Token commands listed because token_provider is enabled in this test
        assert "generate" in text
        assert "revoke" in text


# ---------------------------------------------------------------------------
# Token auth disabled
# ---------------------------------------------------------------------------


class TestAuthDisabled:
    async def test_no_provider_for_generate(self, settings, deps):
        """Generate should fail clearly when token auth is disabled."""
        deps["token_auth_provider"] = None
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0], text="/auth generate 123"
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not enabled" in text.lower()

    async def test_status_still_works_without_token_auth(self, settings, deps):
        """Status must work even if token auth is disabled."""
        deps["token_auth_provider"] = None
        deps["auth_manager"].is_authenticated.return_value = False
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(text="/auth status")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        # Should be status message, not "not enabled"
        assert "not enabled" not in text.lower()
        assert "Not authenticated" in text


# ---------------------------------------------------------------------------
# /auth add / /auth remove
# ---------------------------------------------------------------------------


class TestAuthAdd:
    async def test_add_as_admin(self, settings, deps):
        storage = MagicMock()
        user = MagicMock()
        user.is_allowed = False
        storage.get_or_create_user = AsyncMock(return_value=user)
        storage.users.set_user_allowed = AsyncMock()
        deps["storage"] = storage

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=settings.allowed_users[0], text="/auth add 555")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        storage.get_or_create_user.assert_awaited_once_with(555)
        storage.users.set_user_allowed.assert_awaited_once_with(555, True)
        text = update.message.reply_text.call_args[0][0]
        assert "added" in text.lower() or "allow" in text.lower()

    async def test_add_already_allowed(self, settings, deps):
        """Allowing an already-allowed user should say so, not double-add."""
        storage = MagicMock()
        user = MagicMock()
        user.is_allowed = True
        storage.get_or_create_user = AsyncMock(return_value=user)
        storage.users.set_user_allowed = AsyncMock()
        deps["storage"] = storage

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=settings.allowed_users[0], text="/auth add 555")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        storage.users.set_user_allowed.assert_not_called()
        text = update.message.reply_text.call_args[0][0]
        assert "already" in text.lower()

    async def test_add_rejected_for_non_admin(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=77777, text="/auth add 555")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Admin" in text

    async def test_add_missing_user_id(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=settings.allowed_users[0], text="/auth add")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text

    async def test_add_works_without_token_auth(self, settings, deps):
        """allow/deny must work even when token auth is disabled."""
        deps["token_auth_provider"] = None
        storage = MagicMock()
        user = MagicMock()
        user.is_allowed = False
        storage.get_or_create_user = AsyncMock(return_value=user)
        storage.users.set_user_allowed = AsyncMock()
        deps["storage"] = storage

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=settings.allowed_users[0], text="/auth add 555")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        storage.users.set_user_allowed.assert_awaited_once_with(555, True)


class TestAuthRemove:
    async def test_remove_as_admin(self, settings, deps):
        storage = MagicMock()
        user = MagicMock()
        user.is_allowed = True
        storage.users.get_user = AsyncMock(return_value=user)
        storage.users.set_user_allowed = AsyncMock()
        deps["storage"] = storage

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0], text="/auth remove 555"
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        storage.users.set_user_allowed.assert_awaited_once_with(555, False)
        text = update.message.reply_text.call_args[0][0]
        assert "removed" in text.lower()

    async def test_remove_user_not_in_allowlist(self, settings, deps):
        storage = MagicMock()
        user = MagicMock()
        user.is_allowed = False
        storage.users.get_user = AsyncMock(return_value=user)
        storage.users.set_user_allowed = AsyncMock()
        deps["storage"] = storage

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0], text="/auth remove 555"
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        storage.users.set_user_allowed.assert_not_called()
        text = update.message.reply_text.call_args[0][0]
        assert "not in" in text.lower() or "nothing" in text.lower()

    async def test_remove_unknown_user(self, settings, deps):
        """Deny for a user that doesn't exist in DB at all."""
        storage = MagicMock()
        storage.users.get_user = AsyncMock(return_value=None)
        storage.users.set_user_allowed = AsyncMock()
        deps["storage"] = storage

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0], text="/auth remove 999"
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        storage.users.set_user_allowed.assert_not_called()
        text = update.message.reply_text.call_args[0][0]
        assert "not in" in text.lower() or "nothing" in text.lower()

    async def test_remove_ends_session(self, settings, deps):
        """Denying a user must end their active session."""
        storage = MagicMock()
        user = MagicMock()
        user.is_allowed = True
        storage.users.get_user = AsyncMock(return_value=user)
        storage.users.set_user_allowed = AsyncMock()
        deps["storage"] = storage

        orch = MessageOrchestrator(settings, deps)
        update = _make_update(
            user_id=settings.allowed_users[0], text="/auth remove 555"
        )
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        deps["auth_manager"].end_session.assert_called_once_with(555)

    async def test_remove_rejected_for_non_admin(self, settings, deps):
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(user_id=77777, text="/auth remove 555")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Admin" in text
