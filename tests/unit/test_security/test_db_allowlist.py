"""Tests for DatabaseAllowlistAuthProvider."""

import tempfile
from datetime import UTC, datetime

import pytest

from src.security.auth import (
    AuthenticationManager,
    DatabaseAllowlistAuthProvider,
    WhitelistAuthProvider,
)
from src.storage.database import DatabaseManager
from src.storage.models import UserModel
from src.storage.repositories import UserRepository


@pytest.fixture
async def db_manager():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        mgr = DatabaseManager(f"sqlite:///{f.name}")
        await mgr.initialize()
        yield mgr
        await mgr.close()


@pytest.fixture
async def user_repo(db_manager):
    return UserRepository(db_manager)


@pytest.fixture
async def provider(user_repo):
    return DatabaseAllowlistAuthProvider(user_repo)


async def _create_user(
    user_repo: UserRepository, user_id: int, is_allowed: bool
) -> None:
    now = datetime.now(UTC)
    await user_repo.create_user(
        UserModel(
            user_id=user_id,
            first_seen=now,
            last_active=now,
            is_allowed=is_allowed,
        )
    )


class TestDatabaseAllowlistAuthProvider:
    async def test_allowed_user_authenticates(self, provider, user_repo):
        await _create_user(user_repo, 42, is_allowed=True)
        assert await provider.authenticate(42, {}) is True

    async def test_not_allowed_user_rejected(self, provider, user_repo):
        await _create_user(user_repo, 42, is_allowed=False)
        assert await provider.authenticate(42, {}) is False

    async def test_unknown_user_rejected(self, provider):
        assert await provider.authenticate(999, {}) is False

    async def test_get_user_info_for_allowed(self, provider, user_repo):
        await _create_user(user_repo, 42, is_allowed=True)
        info = await provider.get_user_info(42)
        assert info is not None
        assert info["user_id"] == 42
        assert info["auth_type"] == "db_allowlist"

    async def test_get_user_info_for_not_allowed(self, provider, user_repo):
        await _create_user(user_repo, 42, is_allowed=False)
        assert await provider.get_user_info(42) is None

    async def test_credentials_ignored(self, provider, user_repo):
        """Allowlist doesn't care about credentials — just checks the flag."""
        await _create_user(user_repo, 42, is_allowed=True)
        # Any credentials should work (or no credentials)
        assert await provider.authenticate(42, {"token": "garbage"}) is True
        assert await provider.authenticate(42, {}) is True


class TestAllowlistIntegration:
    async def test_whitelist_takes_priority(self, user_repo):
        """When both providers accept, the first one in the chain wins."""
        # User is in both env whitelist AND DB allowlist
        await _create_user(user_repo, 1, is_allowed=True)

        mgr = AuthenticationManager(
            [
                WhitelistAuthProvider([1]),
                DatabaseAllowlistAuthProvider(user_repo),
            ]
        )

        assert await mgr.authenticate_user(1, {}) is True
        session = mgr.get_session(1)
        assert session.auth_provider == "WhitelistAuthProvider"

    async def test_db_allowlist_kicks_in_when_whitelist_fails(self, user_repo):
        """User not in env whitelist but in DB allowlist — should be authed via DB."""
        await _create_user(user_repo, 99, is_allowed=True)

        mgr = AuthenticationManager(
            [
                WhitelistAuthProvider([1]),  # 99 not in env whitelist
                DatabaseAllowlistAuthProvider(user_repo),
            ]
        )

        assert await mgr.authenticate_user(99, {}) is True
        session = mgr.get_session(99)
        assert session.auth_provider == "DatabaseAllowlistAuthProvider"

    async def test_both_fail_for_unknown_user(self, user_repo):
        mgr = AuthenticationManager(
            [
                WhitelistAuthProvider([1]),
                DatabaseAllowlistAuthProvider(user_repo),
            ]
        )
        assert await mgr.authenticate_user(999, {}) is False
