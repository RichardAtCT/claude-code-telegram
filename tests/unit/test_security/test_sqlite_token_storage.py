"""Tests for SqliteTokenStorage and TokenRepository."""

import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from src.security.auth import SqliteTokenStorage, TokenAuthProvider
from src.storage.database import DatabaseManager
from src.storage.repositories import TokenRepository


@pytest.fixture
async def db_manager():
    """Create a fresh in-memory database with schema."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        mgr = DatabaseManager(f"sqlite:///{f.name}")
        await mgr.initialize()
        # Pre-create test users so FK constraints pass.
        async with mgr.get_connection() as conn:
            for uid in (1, 42, 100, 999):
                await conn.execute(
                    "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                    (uid,),
                )
            await conn.commit()
        yield mgr
        await mgr.close()


@pytest.fixture
async def repo(db_manager):
    return TokenRepository(db_manager)


@pytest.fixture
async def storage(repo):
    return SqliteTokenStorage(repo)


# ---------------------------------------------------------------------------
# TokenRepository
# ---------------------------------------------------------------------------


class TestTokenRepository:
    async def test_store_and_get(self, repo):
        expires = datetime.now(UTC) + timedelta(days=30)
        await repo.store_token(42, "hash_abc", expires)

        model = await repo.get_active_token(42)
        assert model is not None
        assert model.user_id == 42
        assert model.token_hash == "hash_abc"
        assert model.is_active

    async def test_get_missing_user(self, repo):
        assert await repo.get_active_token(999) is None

    async def test_revoke(self, repo):
        expires = datetime.now(UTC) + timedelta(days=30)
        await repo.store_token(42, "hash_abc", expires)
        await repo.revoke_token(42)

        assert await repo.get_active_token(42) is None

    async def test_expired_token_not_returned(self, repo):
        past = datetime.now(UTC) - timedelta(seconds=1)
        await repo.store_token(42, "hash_old", past)

        assert await repo.get_active_token(42) is None

    async def test_store_replaces_old_token(self, repo):
        expires = datetime.now(UTC) + timedelta(days=30)
        await repo.store_token(42, "hash_v1", expires)
        await repo.store_token(42, "hash_v2", expires)

        model = await repo.get_active_token(42)
        assert model is not None
        assert model.token_hash == "hash_v2"

    async def test_update_last_used(self, repo):
        expires = datetime.now(UTC) + timedelta(days=30)
        await repo.store_token(42, "hash_abc", expires)
        await repo.update_last_used(42)

        model = await repo.get_active_token(42)
        assert model is not None
        assert model.last_used is not None


# ---------------------------------------------------------------------------
# SqliteTokenStorage (adapter layer)
# ---------------------------------------------------------------------------


class TestSqliteTokenStorage:
    async def test_store_and_get(self, storage):
        expires = datetime.now(UTC) + timedelta(days=7)
        await storage.store_token(1, "hash_x", expires)

        data = await storage.get_user_token(1)
        assert data is not None
        assert data["hash"] == "hash_x"
        assert "expires_at" in data
        assert "created_at" in data

    async def test_get_missing(self, storage):
        assert await storage.get_user_token(999) is None

    async def test_revoke(self, storage):
        expires = datetime.now(UTC) + timedelta(days=7)
        await storage.store_token(1, "hash_x", expires)
        await storage.revoke_token(1)

        assert await storage.get_user_token(1) is None


# ---------------------------------------------------------------------------
# End-to-end: TokenAuthProvider + SqliteTokenStorage
# ---------------------------------------------------------------------------


class TestTokenAuthE2E:
    async def test_generate_and_authenticate(self, storage):
        provider = TokenAuthProvider("secret", storage)
        token = await provider.generate_token(100)

        assert await provider.authenticate(100, {"token": token}) is True
        assert await provider.authenticate(100, {"token": "wrong"}) is False

    async def test_revoke_prevents_auth(self, storage):
        provider = TokenAuthProvider("secret", storage)
        token = await provider.generate_token(100)

        await provider.revoke_token(100)

        assert await provider.authenticate(100, {"token": token}) is False
