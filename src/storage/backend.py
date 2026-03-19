"""Database backend abstraction for SQLite and PostgreSQL.

Provides a unified async interface so that the rest of the storage
layer does not need to know which database engine is in use.
"""

from __future__ import annotations

import asyncio
import sqlite3
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple

import aiosqlite
import structlog

from .compat import BackendType

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class DatabaseBackend(ABC):
    """Abstract database backend."""

    @property
    @abstractmethod
    def backend_type(self) -> BackendType:
        """Return ``'sqlite'`` or ``'postgresql'``."""

    @property
    def placeholder(self) -> str:
        """Return the positional-parameter placeholder character."""
        return "?" if self.backend_type == "sqlite" else "$1"

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables, run migrations, warm up pools."""

    @abstractmethod
    async def get_connection(self) -> AsyncIterator[Any]:
        """Yield a connection-like object (context manager)."""

    @abstractmethod
    async def close(self) -> None:
        """Shut down pools / close connections."""

    @abstractmethod
    async def execute(
        self, sql: str, params: Sequence[Any] = ()
    ) -> List[Dict[str, Any]]:
        """Execute *sql* and return all rows as dicts."""

    @abstractmethod
    async def executemany(
        self, sql: str, params_list: Sequence[Sequence[Any]]
    ) -> None:
        """Execute *sql* for each set of params."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the backend is responsive."""


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------


class SQLiteBackend(DatabaseBackend):
    """Backend powered by :mod:`aiosqlite`."""

    def __init__(self, database_path: str, pool_size: int = 5):
        self.database_path = Path(database_path)
        self._pool_size = pool_size
        self._pool: list[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()

        # Register adapters/converters (idempotent)
        sqlite3.register_adapter(datetime, lambda v: v.isoformat())
        sqlite3.register_converter(
            "TIMESTAMP", lambda b: datetime.fromisoformat(b.decode())
        )
        sqlite3.register_converter(
            "DATETIME", lambda b: datetime.fromisoformat(b.decode())
        )
        sqlite3.register_converter("DATE", lambda b: b.decode())

    @property
    def backend_type(self) -> BackendType:
        return "sqlite"

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        # Warm the pool
        async with self._pool_lock:
            for _ in range(self._pool_size):
                conn = await self._make_conn()
                self._pool.append(conn)
        logger.info(
            "SQLiteBackend initialised",
            path=str(self.database_path),
            pool_size=self._pool_size,
        )

    async def _make_conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(
            self.database_path, detect_types=sqlite3.PARSE_DECLTYPES
        )
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._pool_lock:
            if self._pool:
                conn = self._pool.pop()
            else:
                conn = await self._make_conn()
        try:
            yield conn
        finally:
            async with self._pool_lock:
                if len(self._pool) < self._pool_size:
                    self._pool.append(conn)
                else:
                    await conn.close()

    async def execute(
        self, sql: str, params: Sequence[Any] = ()
    ) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            await conn.commit()
            return [dict(r) for r in rows]

    async def executemany(
        self, sql: str, params_list: Sequence[Sequence[Any]]
    ) -> None:
        async with self.get_connection() as conn:
            await conn.executemany(sql, params_list)
            await conn.commit()

    async def health_check(self) -> bool:
        try:
            async with self.get_connection() as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error("SQLite health check failed", error=str(e))
            return False

    async def close(self) -> None:
        async with self._pool_lock:
            for conn in self._pool:
                await conn.close()
            self._pool.clear()
        logger.info("SQLiteBackend closed")


# ---------------------------------------------------------------------------
# PostgreSQL backend
# ---------------------------------------------------------------------------


class PostgresBackend(DatabaseBackend):
    """Backend powered by :mod:`asyncpg`.

    ``asyncpg`` is imported lazily so the bot can run without it when
    only SQLite is used.
    """

    def __init__(
        self,
        dsn: str,
        min_size: int = 2,
        max_size: int = 10,
    ):
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None  # asyncpg.Pool

    @property
    def backend_type(self) -> BackendType:
        return "postgresql"

    async def initialize(self) -> None:
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "asyncpg is required for PostgreSQL support. "
                "Install it with: pip install asyncpg"
            )

        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
        )
        logger.info(
            "PostgresBackend initialised",
            min_size=self._min_size,
            max_size=self._max_size,
        )

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[Any]:
        """Yield an ``asyncpg.Connection`` from the pool.

        The connection is a *raw asyncpg connection*, **not** an aiosqlite
        one.  Code that interacts directly via ``get_connection`` must be
        backend-aware (the ``DatabaseManager`` handles this).
        """
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(
        self, sql: str, params: Sequence[Any] = ()
    ) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]

    async def executemany(
        self, sql: str, params_list: Sequence[Sequence[Any]]
    ) -> None:
        async with self.get_connection() as conn:
            # asyncpg executemany expects list of tuples
            await conn.executemany(sql, [tuple(p) for p in params_list])

    async def health_check(self) -> bool:
        try:
            async with self.get_connection() as conn:
                await conn.fetchval("SELECT 1")
                return True
        except Exception as e:
            logger.error("PostgreSQL health check failed", error=str(e))
            return False

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
        logger.info("PostgresBackend closed")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_backend(
    database_url: str,
    *,
    pool_min_size: int = 2,
    pool_max_size: int = 10,
    sqlite_pool_size: int = 5,
) -> DatabaseBackend:
    """Detect the database URL scheme and return the right backend.

    Supported schemes:
    * ``sqlite:///path/to/db`` or ``sqlite://path``
    * ``postgresql://...`` or ``postgres://...``
    """
    url = database_url.strip()

    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        return SQLiteBackend(path, pool_size=sqlite_pool_size)
    elif url.startswith("sqlite://"):
        path = url[len("sqlite://"):]
        return SQLiteBackend(path, pool_size=sqlite_pool_size)
    elif url.startswith(("postgresql://", "postgres://")):
        return PostgresBackend(
            dsn=url,
            min_size=pool_min_size,
            max_size=pool_max_size,
        )
    else:
        # Treat as a bare file path (legacy)
        return SQLiteBackend(url, pool_size=sqlite_pool_size)
