"""Cache decorators for transparent caching of async functions.

Provides @cached and @invalidates decorators that work with
any CacheBackend instance.
"""

import functools
import hashlib
import json
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger()

# Module-level reference to the active cache backend.
# Set by CacheManager during initialization.
_active_backend: Any = None


def set_active_backend(backend: Any) -> None:
    """Set the module-level cache backend for decorators."""
    global _active_backend
    _active_backend = backend


def _make_cache_key(prefix: str, func: Callable[..., Any], args: tuple, kwargs: dict) -> str:
    """Generate a deterministic cache key from function signature and arguments.

    Serializable args are JSON-encoded and hashed. Non-serializable args
    (like `self`) are represented by their type and id.
    """
    parts = [prefix, func.__module__, func.__qualname__]

    for arg in args:
        try:
            parts.append(json.dumps(arg, sort_keys=True, default=str))
        except (TypeError, ValueError):
            parts.append(f"{type(arg).__name__}:{id(arg)}")

    for k, v in sorted(kwargs.items()):
        try:
            parts.append(f"{k}={json.dumps(v, sort_keys=True, default=str)}")
        except (TypeError, ValueError):
            parts.append(f"{k}={type(v).__name__}:{id(v)}")

    raw = "|".join(parts)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{prefix}:{func.__qualname__}:{key_hash}"


def cached(
    ttl: int = 300,
    key_prefix: str = "",
) -> Callable[..., Any]:
    """Decorator that caches async function results.

    On cache hit, returns the cached value without calling the function.
    On miss, calls the function, stores the result, and returns it.

    Args:
        ttl: Time-to-live in seconds. Default 300 (5 minutes).
        key_prefix: Optional prefix for cache keys.

    Usage:
        @cached(ttl=60, key_prefix="users")
        async def get_user(user_id: int) -> dict:
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            backend = _active_backend
            if backend is None:
                # No cache configured — call function directly
                return await func(*args, **kwargs)

            prefix = key_prefix or func.__qualname__
            cache_key = _make_cache_key(prefix, func, args, kwargs)

            # Try cache
            try:
                cached_value = await backend.get(cache_key)
                if cached_value is not None:
                    logger.debug("Cache hit", key=cache_key)
                    return cached_value
            except Exception:
                logger.debug("Cache get failed, falling through", key=cache_key)

            # Cache miss — compute
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                await backend.set(cache_key, result, ttl=ttl)
                logger.debug("Cache set", key=cache_key, ttl=ttl)
            except Exception:
                logger.debug("Cache set failed", key=cache_key)

            return result

        # Expose cache metadata on the wrapper
        wrapper._cache_prefix = key_prefix or func.__qualname__  # type: ignore[attr-defined]
        wrapper._cache_ttl = ttl  # type: ignore[attr-defined]
        return wrapper

    return decorator


def invalidates(key_pattern: str) -> Callable[..., Any]:
    """Decorator that invalidates cache entries matching a pattern after execution.

    Applied to write/mutation methods to ensure stale data is cleared.

    Args:
        key_pattern: Glob pattern of cache keys to invalidate.

    Usage:
        @invalidates("users:*")
        async def update_user(user_id: int, data: dict) -> None:
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)

            backend = _active_backend
            if backend is not None:
                try:
                    deleted = await backend.invalidate_pattern(key_pattern)
                    if deleted:
                        logger.debug(
                            "Cache invalidated",
                            pattern=key_pattern,
                            deleted=deleted,
                        )
                except Exception:
                    logger.debug(
                        "Cache invalidation failed",
                        pattern=key_pattern,
                    )

            return result

        return wrapper

    return decorator
