"""Cache backend implementations.

Provides an ABC and two concrete backends:
- InMemoryCacheBackend: dict-based with TTL and LRU eviction
- RedisCacheBackend: redis.asyncio-based with pattern invalidation
"""

import asyncio
import fnmatch
import json
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key. Returns None on miss."""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with optional TTL in seconds."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if existed."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Remove all entries."""
        ...

    @abstractmethod
    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns count deleted."""
        ...


@dataclass
class _CacheEntry:
    """Internal entry with value and expiration."""

    value: Any
    expires_at: Optional[float]  # monotonic time, None = no expiry


class InMemoryCacheBackend(CacheBackend):
    """In-memory cache with TTL tracking and LRU eviction.

    Uses an OrderedDict for O(1) LRU tracking. Expired keys are
    lazily cleaned on access and periodically via a background task.
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
        cleanup_interval: float = 60.0,
    ) -> None:
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the periodic cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.debug("Cache cleanup task started")

    async def stop(self) -> None:
        """Stop the periodic cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.debug("Cache cleanup task stopped")

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key, returning None if missing or expired."""
        entry = self._store.get(key)
        if entry is None:
            return None

        # Check expiration
        if entry.expires_at is not None and time.monotonic() > entry.expires_at:
            del self._store[key]
            return None

        # Move to end (most recently used)
        self._store.move_to_end(key)
        return entry.value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with TTL. Evicts LRU if at capacity."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = (
            time.monotonic() + effective_ttl if effective_ttl > 0 else None
        )

        # If key exists, update in place
        if key in self._store:
            self._store.move_to_end(key)
            self._store[key] = _CacheEntry(value=value, expires_at=expires_at)
            return

        # Evict LRU entries if at capacity
        while len(self._store) >= self._max_size:
            evicted_key, _ = self._store.popitem(last=False)
            logger.debug("Cache LRU eviction", key=evicted_key)

        self._store[key] = _CacheEntry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def clear(self) -> None:
        """Remove all entries."""
        count = len(self._store)
        self._store.clear()
        logger.debug("Cache cleared", entries_removed=count)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern."""
        to_delete = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
        for key in to_delete:
            del self._store[key]
        if to_delete:
            logger.debug(
                "Cache pattern invalidation",
                pattern=pattern,
                deleted=len(to_delete),
            )
        return len(to_delete)

    @property
    def size(self) -> int:
        """Current number of entries (including expired)."""
        return len(self._store)

    async def _periodic_cleanup(self) -> None:
        """Background task that removes expired entries."""
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
        except asyncio.CancelledError:
            pass

    async def _cleanup_expired(self) -> None:
        """Remove all expired entries."""
        now = time.monotonic()
        expired = [
            k
            for k, entry in self._store.items()
            if entry.expires_at is not None and now > entry.expires_at
        ]
        for key in expired:
            del self._store[key]
        if expired:
            logger.debug("Cache expired entries cleaned", count=len(expired))


class RedisCacheBackend(CacheBackend):
    """Redis-based cache backend using redis.asyncio.

    Requires `redis` package: pip install redis
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_ttl: int = 300,
        key_prefix: str = "cctg:",
    ) -> None:
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._key_prefix = key_prefix
        self._redis: Any = None

    async def connect(self) -> None:
        """Initialize the Redis connection pool."""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "redis package required for RedisCacheBackend. "
                "Install with: pip install redis"
            )

        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=True,
        )
        # Avoid logging credentials in the Redis URL
        from urllib.parse import urlparse
        parsed = urlparse(self._redis_url)
        safe_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 6379}/{parsed.path.lstrip('/')}"
        logger.info("Redis cache connected", url=safe_url)

    async def disconnect(self) -> None:
        """Close the Redis connection pool."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            logger.info("Redis cache disconnected")

    def _prefixed(self, key: str) -> str:
        """Add prefix to key to namespace our cache entries."""
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis, deserializing from JSON."""
        if not self._redis:
            return None
        raw = await self._redis.get(self._prefixed(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in Redis as JSON with TTL."""
        if not self._redis:
            return
        effective_ttl = ttl if ttl is not None else self._default_ttl
        serialized = json.dumps(value, default=str)
        if effective_ttl > 0:
            await self._redis.setex(self._prefixed(key), effective_ttl, serialized)
        else:
            await self._redis.set(self._prefixed(key), serialized)

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self._redis:
            return False
        result = await self._redis.delete(self._prefixed(key))
        return result > 0

    async def clear(self) -> None:
        """Remove all keys with our prefix using SCAN."""
        if not self._redis:
            return
        pattern = f"{self._key_prefix}*"
        deleted = 0
        async for key in self._redis.scan_iter(match=pattern, count=100):
            await self._redis.delete(key)
            deleted += 1
        logger.debug("Redis cache cleared", entries_removed=deleted)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete keys matching a glob pattern using SCAN."""
        if not self._redis:
            return 0
        full_pattern = self._prefixed(pattern)
        deleted = 0
        async for key in self._redis.scan_iter(match=full_pattern, count=100):
            await self._redis.delete(key)
            deleted += 1
        if deleted:
            logger.debug(
                "Redis pattern invalidation",
                pattern=pattern,
                deleted=deleted,
            )
        return deleted

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        if not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False
