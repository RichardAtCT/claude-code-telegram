"""Tests for the cache module: backend, decorators, manager."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.cache.backend import InMemoryCacheBackend
from src.cache.decorators import _make_cache_key, cached, invalidates, set_active_backend
from src.cache.manager import CacheManager


# ---------------------------------------------------------------------------
# InMemoryCacheBackend
# ---------------------------------------------------------------------------


@pytest.fixture
def backend():
    return InMemoryCacheBackend(max_size=5, default_ttl=300)


@pytest.mark.asyncio
async def test_set_and_get(backend):
    await backend.set("k1", "v1")
    assert await backend.get("k1") == "v1"


@pytest.mark.asyncio
async def test_get_missing_returns_none(backend):
    assert await backend.get("nonexistent") is None


@pytest.mark.asyncio
async def test_ttl_expiry(backend):
    """A key with a very short TTL should expire."""
    await backend.set("k", "val", ttl=0)  # ttl=0 => no expiry
    assert await backend.get("k") == "val"

    # Use a tiny TTL and patch monotonic to simulate time passing
    await backend.set("k2", "val2", ttl=1)
    with patch("src.cache.backend.time.monotonic", return_value=time.monotonic() + 10):
        assert await backend.get("k2") is None


@pytest.mark.asyncio
async def test_delete(backend):
    await backend.set("k", "v")
    assert await backend.delete("k") is True
    assert await backend.delete("k") is False
    assert await backend.get("k") is None


@pytest.mark.asyncio
async def test_clear(backend):
    await backend.set("a", 1)
    await backend.set("b", 2)
    await backend.clear()
    assert backend.size == 0


@pytest.mark.asyncio
async def test_max_size_lru_eviction(backend):
    """When at max_size, the LRU entry is evicted."""
    for i in range(5):
        await backend.set(f"k{i}", i)
    assert backend.size == 5

    # Adding a 6th key should evict k0 (oldest / LRU)
    await backend.set("k5", 5)
    assert backend.size == 5
    assert await backend.get("k0") is None
    assert await backend.get("k5") == 5


@pytest.mark.asyncio
async def test_invalidate_pattern(backend):
    await backend.set("user:1:name", "Alice")
    await backend.set("user:2:name", "Bob")
    await backend.set("session:1", "data")

    deleted = await backend.invalidate_pattern("user:*")
    assert deleted == 2
    assert await backend.get("session:1") == "data"


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_active_backend():
    """Ensure the module-level backend is cleaned up between tests."""
    set_active_backend(None)
    yield
    set_active_backend(None)


@pytest.mark.asyncio
async def test_cached_miss_and_hit():
    """First call computes; second call returns cached value."""
    be = InMemoryCacheBackend(max_size=100, default_ttl=300)
    set_active_backend(be)

    call_count = 0

    @cached(ttl=60, key_prefix="test")
    async def compute(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    assert await compute(5) == 10
    assert call_count == 1

    # Second call should hit cache
    assert await compute(5) == 10
    assert call_count == 1


@pytest.mark.asyncio
async def test_cached_no_backend_falls_through():
    """When no backend is set, the function is called directly."""
    @cached(ttl=60)
    async def compute(x):
        return x + 1

    assert await compute(3) == 4


@pytest.mark.asyncio
async def test_invalidates_clears_matching_keys():
    be = InMemoryCacheBackend(max_size=100, default_ttl=300)
    set_active_backend(be)

    await be.set("test:compute:abc123", "cached_value")

    @invalidates("test:*")
    async def mutate():
        return "done"

    result = await mutate()
    assert result == "done"
    # The key matching "test:*" should be gone
    assert await be.get("test:compute:abc123") is None


# ---------------------------------------------------------------------------
# CacheManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_manager_memory_backend():
    mgr = CacheManager(enable_cache=True, cache_backend="memory", cache_max_size=50)
    await mgr.initialize()

    assert mgr.is_enabled is True
    assert mgr.backend is not None

    await mgr.set("hello", "world")
    assert await mgr.get("hello") == "world"

    await mgr.shutdown()
    assert mgr.is_enabled is False


@pytest.mark.asyncio
async def test_cache_manager_disabled():
    mgr = CacheManager(enable_cache=False)
    await mgr.initialize()
    assert mgr.is_enabled is False
    assert await mgr.get("anything") is None
