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
    async def test_revoke_as_admin(self, settings, deps, token_provider):
        # Pre-generate a token
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

        # Verify token is actually revoked
        assert await token_provider.authenticate(999, {"token": "any"}) is False

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
    async def test_token_passthrough(self, settings, deps):
        """When /auth <token> reaches the handler, user is already authed."""
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(text="/auth some_random_token_value")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "Authenticated" in text


# ---------------------------------------------------------------------------
# Token auth disabled
# ---------------------------------------------------------------------------


class TestAuthDisabled:
    async def test_no_provider(self, settings, deps):
        deps["token_auth_provider"] = None
        orch = MessageOrchestrator(settings, deps)
        update = _make_update(text="/auth status")
        ctx = _make_context(deps, settings)

        await orch.agentic_auth(update, ctx)

        text = update.message.reply_text.call_args[0][0]
        assert "not enabled" in text.lower()
