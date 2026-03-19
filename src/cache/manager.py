"""Cache manager for initializing and managing cache backends.

Provides a single entry point for cache lifecycle and health checks.
"""

from typing import Any, Optional

import structlog

from .backend import CacheBackend, InMemoryCacheBackend, RedisCacheBackend
from .decorators import set_active_backend

logger = structlog.get_logger()


class CacheManager:
    """Initializes the appropriate cache backend and manages its lifecycle.

    Usage:
        manager = CacheManager(settings)
        await manager.initialize()
        # ... app runs, decorators use the active backend ...
        await manager.shutdown()
    """

    def __init__(
        self,
        enable_cache: bool = False,
        cache_backend: str = "memory",
        redis_url: Optional[str] = None,
        cache_default_ttl: int = 300,
        cache_max_size: int = 1000,
    ) -> None:
        self._enable_cache = enable_cache
        self._backend_type = cache_backend
        self._redis_url = redis_url
        self._default_ttl = cache_default_ttl
        self._max_size = cache_max_size
        self._backend: Optional[CacheBackend] = None

    @classmethod
    def from_settings(cls, settings: Any) -> "CacheManager":
        """Create a CacheManager from application Settings."""
        return cls(
            enable_cache=getattr(settings, "enable_cache", False),
            cache_backend=getattr(settings, "cache_backend", "memory"),
            redis_url=getattr(settings, "redis_url", None),
            cache_default_ttl=getattr(settings, "cache_default_ttl", 300),
            cache_max_size=getattr(settings, "cache_max_size", 1000),
        )

    async def initialize(self) -> None:
        """Create and start the configured cache backend."""
        if not self._enable_cache:
            logger.info("Cache disabled, skipping initialization")
            return

        if self._backend_type == "redis":
            if not self._redis_url:
                logger.warning(
                    "Redis cache selected but no redis_url configured, "
                    "falling back to memory"
                )
                self._backend_type = "memory"
            else:
                backend = RedisCacheBackend(
                    redis_url=self._redis_url,
                    default_ttl=self._default_ttl,
                )
                try:
                    await backend.connect()
                    self._backend = backend
                    logger.info("Redis cache backend initialized")
                except Exception as e:
                    logger.error(
                        "Redis connection failed, falling back to memory",
                        error=str(e),
                    )
                    self._backend_type = "memory"

        if self._backend_type == "memory":
            backend = InMemoryCacheBackend(
                max_size=self._max_size,
                default_ttl=self._default_ttl,
            )
            await backend.start()
            self._backend = backend
            logger.info(
                "In-memory cache backend initialized",
                max_size=self._max_size,
                default_ttl=self._default_ttl,
            )

        # Set as active backend for decorators
        if self._backend:
            set_active_backend(self._backend)

    async def shutdown(self) -> None:
        """Stop and clean up the cache backend."""
        if self._backend is None:
            return

        if isinstance(self._backend, InMemoryCacheBackend):
            await self._backend.stop()
        elif isinstance(self._backend, RedisCacheBackend):
            await self._backend.disconnect()

        set_active_backend(None)
        self._backend = None
        logger.info("Cache backend shut down")

    @property
    def backend(self) -> Optional[CacheBackend]:
        """Access the underlying cache backend (may be None)."""
        return self._backend

    @property
    def is_enabled(self) -> bool:
        """Whether caching is active."""
        return self._backend is not None

    async def get(self, key: str) -> Optional[Any]:
        """Convenience: get from cache."""
        if self._backend:
            return await self._backend.get(key)
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Convenience: set in cache."""
        if self._backend:
            await self._backend.set(key, value, ttl=ttl)

    async def delete(self, key: str) -> bool:
        """Convenience: delete from cache."""
        if self._backend:
            return await self._backend.delete(key)
        return False

    async def clear(self) -> None:
        """Convenience: clear all cache entries."""
        if self._backend:
            await self._backend.clear()

    async def health_check(self) -> bool:
        """Check cache backend health.

        Returns True if:
        - Cache is disabled (not a failure)
        - Memory backend is running
        - Redis backend responds to ping
        """
        if not self._enable_cache:
            return True

        if self._backend is None:
            return False

        if isinstance(self._backend, RedisCacheBackend):
            return await self._backend.health_check()

        # InMemory is always healthy if it exists
        return True
