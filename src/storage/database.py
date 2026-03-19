"""Database connection and initialization.

Features:
- Connection pooling (SQLite + PostgreSQL)
- Automatic migrations
- Health checks
- Schema versioning
- Backend abstraction via DatabaseBackend
"""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional, Tuple

import aiosqlite
import structlog

from .backend import DatabaseBackend, SQLiteBackend, create_backend
from .compat import BackendType, adapt_sql

logger = structlog.get_logger()


# Python 3.12+: sqlite3's default datetime adapter is deprecated.
# Register explicit adapters/converters once at import time to avoid warnings
# and keep consistent ISO-8601 persistence for datetime values.
sqlite3.register_adapter(datetime, lambda value: value.isoformat())
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))
sqlite3.register_converter("DATETIME", lambda b: datetime.fromisoformat(b.decode()))
# Keep DATE columns as raw ISO strings (matches existing model expectations).
sqlite3.register_converter("DATE", lambda b: b.decode())

# ---------------------------------------------------------------------------
# SQLite migration scripts (kept as-is for backward compatibility)
# ---------------------------------------------------------------------------

# Initial schema migration
INITIAL_SCHEMA = """
-- Core Tables

-- Users table
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    telegram_username TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_allowed BOOLEAN DEFAULT FALSE,
    total_cost REAL DEFAULT 0.0,
    message_count INTEGER DEFAULT 0,
    session_count INTEGER DEFAULT 0
);

-- Sessions table
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    project_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_cost REAL DEFAULT 0.0,
    total_turns INTEGER DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Messages table
CREATE TABLE messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prompt TEXT NOT NULL,
    response TEXT,
    cost REAL DEFAULT 0.0,
    duration_ms INTEGER,
    error TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Tool usage table
CREATE TABLE tool_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id INTEGER,
    tool_name TEXT NOT NULL,
    tool_input JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (message_id) REFERENCES messages(message_id)
);

-- Audit log table
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data JSON,
    success BOOLEAN DEFAULT TRUE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- User tokens table (for token auth)
CREATE TABLE user_tokens (
    token_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    last_used TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Cost tracking table
CREATE TABLE cost_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,
    daily_cost REAL DEFAULT 0.0,
    request_count INTEGER DEFAULT 0,
    UNIQUE(user_id, date),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Indexes for performance
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_project_path ON sessions(project_path);
CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX idx_cost_tracking_user_date ON cost_tracking(user_id, date);
"""

# PostgreSQL-compatible initial schema
PG_INITIAL_SCHEMA = """
-- Core Tables

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    telegram_username TEXT,
    first_seen TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW(),
    is_allowed BOOLEAN DEFAULT FALSE,
    total_cost DOUBLE PRECISION DEFAULT 0.0,
    message_count INTEGER DEFAULT 0,
    session_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used TIMESTAMP DEFAULT NOW(),
    total_cost DOUBLE PRECISION DEFAULT 0.0,
    total_turns INTEGER DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    prompt TEXT NOT NULL,
    response TEXT,
    cost DOUBLE PRECISION DEFAULT 0.0,
    duration_ms INTEGER,
    error TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS tool_usage (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id INTEGER,
    tool_name TEXT NOT NULL,
    tool_input JSONB,
    timestamp TIMESTAMP DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (message_id) REFERENCES messages(message_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_data JSONB,
    success BOOLEAN DEFAULT TRUE,
    timestamp TIMESTAMP DEFAULT NOW(),
    ip_address TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS user_tokens (
    token_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    last_used TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS cost_tracking (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    date DATE NOT NULL,
    daily_cost DOUBLE PRECISION DEFAULT 0.0,
    request_count INTEGER DEFAULT 0,
    UNIQUE(user_id, date),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_project_path ON sessions(project_path);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_cost_tracking_user_date ON cost_tracking(user_id, date);
"""


class DatabaseManager:
    """Manage database connections and initialization.

    Supports both SQLite (default) and PostgreSQL backends.
    The ``database_url`` scheme determines the backend:

    * ``sqlite:///path``       -> SQLite via aiosqlite
    * ``postgresql://...``     -> PostgreSQL via asyncpg

    The public API (``get_connection``, ``health_check``, ``close``) is
    preserved so that existing repository code keeps working unchanged.
    """

    def __init__(
        self,
        database_url: str,
        *,
        pool_min_size: int = 2,
        pool_max_size: int = 10,
    ):
        """Initialize database manager."""
        self._database_url = database_url
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size

        # Determine backend type from URL
        url = database_url.strip()
        if url.startswith(("postgresql://", "postgres://")):
            self._backend_type: BackendType = "postgresql"
            self.database_path: Optional[Path] = None
        else:
            self._backend_type = "sqlite"
            self.database_path = self._parse_database_url(database_url)

        # Legacy SQLite pool (used when backend_type == "sqlite")
        self._connection_pool: list[aiosqlite.Connection] = []
        self._pool_size = 5
        self._pool_lock = asyncio.Lock()

        # Backend instance (created during initialize)
        self._backend: Optional[DatabaseBackend] = None

    @property
    def backend_type(self) -> BackendType:
        """Return the active backend type."""
        return self._backend_type

    @property
    def backend(self) -> Optional[DatabaseBackend]:
        """Return the underlying backend (available after ``initialize``)."""
        return self._backend

    def _parse_database_url(self, database_url: str) -> Path:
        """Parse database URL to path."""
        if database_url.startswith("sqlite:///"):
            return Path(database_url[10:])
        elif database_url.startswith("sqlite://"):
            return Path(database_url[9:])
        else:
            return Path(database_url)

    async def initialize(self) -> None:
        """Initialize database and run migrations."""
        if self._backend_type == "postgresql":
            await self._initialize_postgres()
        else:
            await self._initialize_sqlite()

    # ------------------------------------------------------------------
    # SQLite initialisation (preserved from original)
    # ------------------------------------------------------------------

    async def _initialize_sqlite(self) -> None:
        assert self.database_path is not None
        logger.info("Initializing SQLite database", path=str(self.database_path))

        # Ensure directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # Run migrations
        await self._run_sqlite_migrations()

        # Initialize connection pool
        await self._init_pool()

        logger.info("SQLite database initialization complete")

    async def _run_sqlite_migrations(self) -> None:
        assert self.database_path is not None
        async with aiosqlite.connect(
            self.database_path, detect_types=sqlite3.PARSE_DECLTYPES
        ) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON")

            current_version = await self._get_schema_version_sqlite(conn)
            logger.info("Current schema version", version=current_version)

            migrations = self._get_migrations()
            for version, migration in migrations:
                if version > current_version:
                    logger.info("Running migration", version=version)
                    await conn.executescript(migration)
                    await self._set_schema_version_sqlite(conn, version)

            await conn.commit()

    async def _get_schema_version_sqlite(self, conn: aiosqlite.Connection) -> int:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        cursor = await conn.execute("SELECT MAX(version) FROM schema_version")
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0

    async def _set_schema_version_sqlite(
        self, conn: aiosqlite.Connection, version: int
    ) -> None:
        await conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (version,)
        )

    # ------------------------------------------------------------------
    # PostgreSQL initialisation
    # ------------------------------------------------------------------

    async def _initialize_postgres(self) -> None:
        logger.info("Initializing PostgreSQL database")

        self._backend = create_backend(
            self._database_url,
            pool_min_size=self._pool_min_size,
            pool_max_size=self._pool_max_size,
        )
        await self._backend.initialize()

        # Run migrations
        await self._run_pg_migrations()

        logger.info("PostgreSQL database initialization complete")

    async def _run_pg_migrations(self) -> None:
        assert self._backend is not None

        async with self._backend.get_connection() as conn:
            # Ensure migration tracking table exists
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                "  version INTEGER PRIMARY KEY"
                ")"
            )

            row = await conn.fetchrow("SELECT MAX(version) AS v FROM schema_version")
            current_version = row["v"] if row and row["v"] else 0
            logger.info("Current PG schema version", version=current_version)

            pg_migrations = self._get_pg_migrations()
            for version, migration_sql in pg_migrations:
                if version > current_version:
                    logger.info("Running PG migration", version=version)
                    await conn.execute(migration_sql)
                    await conn.execute(
                        "INSERT INTO schema_version (version) VALUES ($1)",
                        version,
                    )

    def _get_pg_migrations(self) -> List[Tuple[int, str]]:
        """Return PostgreSQL migration scripts."""
        return [
            (1, PG_INITIAL_SCHEMA),
            (
                2,
                """
                -- Analytics views for PostgreSQL
                CREATE OR REPLACE VIEW daily_stats AS
                SELECT
                    DATE(timestamp) as date,
                    COUNT(DISTINCT user_id) as active_users,
                    COUNT(*) as total_messages,
                    SUM(cost) as total_cost,
                    AVG(duration_ms) as avg_duration
                FROM messages
                GROUP BY DATE(timestamp);

                CREATE OR REPLACE VIEW user_stats AS
                SELECT
                    u.user_id,
                    u.telegram_username,
                    COUNT(DISTINCT s.session_id) as total_sessions,
                    COUNT(m.message_id) as total_messages,
                    SUM(m.cost) as total_cost,
                    MAX(m.timestamp) as last_activity
                FROM users u
                LEFT JOIN sessions s ON u.user_id = s.user_id
                LEFT JOIN messages m ON u.user_id = m.user_id
                GROUP BY u.user_id, u.telegram_username;
                """,
            ),
            (
                3,
                """
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_name TEXT NOT NULL,
                    cron_expression TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    target_chat_ids TEXT DEFAULT '',
                    working_directory TEXT NOT NULL,
                    skill_name TEXT,
                    created_by BIGINT DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS webhook_events (
                    id SERIAL PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    delivery_id TEXT UNIQUE,
                    payload JSONB,
                    processed BOOLEAN DEFAULT FALSE,
                    received_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_webhook_events_delivery
                    ON webhook_events(delivery_id);
                CREATE INDEX IF NOT EXISTS idx_webhook_events_provider
                    ON webhook_events(provider, received_at);
                CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_active
                    ON scheduled_jobs(is_active);
                """,
            ),
            (
                4,
                """
                CREATE TABLE IF NOT EXISTS project_threads (
                    id SERIAL PRIMARY KEY,
                    project_slug TEXT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    message_thread_id BIGINT NOT NULL,
                    topic_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(chat_id, project_slug),
                    UNIQUE(chat_id, message_thread_id)
                );

                CREATE INDEX IF NOT EXISTS idx_project_threads_chat_active
                    ON project_threads(chat_id, is_active);
                CREATE INDEX IF NOT EXISTS idx_project_threads_slug
                    ON project_threads(project_slug);
                """,
            ),
            (
                5,
                """
                CREATE TABLE IF NOT EXISTS pending_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    prompt TEXT NOT NULL,
                    working_directory TEXT NOT NULL,
                    queued_at DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_pending_requests_status
                    ON pending_requests(status, queued_at);
                CREATE INDEX IF NOT EXISTS idx_pending_requests_user
                    ON pending_requests(user_id);
                """,
            ),
            (
                6,
                """
                CREATE TABLE IF NOT EXISTS teams (
                    team_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_by BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (created_by) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS team_members (
                    team_id TEXT NOT NULL,
                    user_id BIGINT NOT NULL,
                    role TEXT DEFAULT 'member',
                    joined_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (team_id, user_id),
                    FOREIGN KEY (team_id) REFERENCES teams(team_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS shared_projects (
                    team_id TEXT NOT NULL,
                    project_path TEXT NOT NULL,
                    shared_session_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (team_id) REFERENCES teams(team_id),
                    UNIQUE(team_id, project_path)
                );

                CREATE INDEX IF NOT EXISTS idx_team_members_user
                    ON team_members(user_id);
                CREATE INDEX IF NOT EXISTS idx_shared_projects_team
                    ON shared_projects(team_id);
                """,
            ),
        ]

    def _get_migrations(self) -> List[Tuple[int, str]]:
        """Get SQLite migration scripts."""
        return [
            (1, INITIAL_SCHEMA),
            (
                2,
                """
                -- Add analytics views
                CREATE VIEW IF NOT EXISTS daily_stats AS
                SELECT
                    date(timestamp) as date,
                    COUNT(DISTINCT user_id) as active_users,
                    COUNT(*) as total_messages,
                    SUM(cost) as total_cost,
                    AVG(duration_ms) as avg_duration
                FROM messages
                GROUP BY date(timestamp);

                CREATE VIEW IF NOT EXISTS user_stats AS
                SELECT
                    u.user_id,
                    u.telegram_username,
                    COUNT(DISTINCT s.session_id) as total_sessions,
                    COUNT(m.message_id) as total_messages,
                    SUM(m.cost) as total_cost,
                    MAX(m.timestamp) as last_activity
                FROM users u
                LEFT JOIN sessions s ON u.user_id = s.user_id
                LEFT JOIN messages m ON u.user_id = m.user_id
                GROUP BY u.user_id;
                """,
            ),
            (
                3,
                """
                -- Agentic platform tables

                -- Scheduled jobs for recurring agent tasks
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_name TEXT NOT NULL,
                    cron_expression TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    target_chat_ids TEXT DEFAULT '',
                    working_directory TEXT NOT NULL,
                    skill_name TEXT,
                    created_by INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Webhook events for deduplication and audit
                CREATE TABLE IF NOT EXISTS webhook_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    delivery_id TEXT UNIQUE,
                    payload JSON,
                    processed BOOLEAN DEFAULT FALSE,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_webhook_events_delivery
                    ON webhook_events(delivery_id);
                CREATE INDEX IF NOT EXISTS idx_webhook_events_provider
                    ON webhook_events(provider, received_at);
                CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_active
                    ON scheduled_jobs(is_active);

                -- Enable WAL mode for better concurrent write performance
                PRAGMA journal_mode=WAL;
                """,
            ),
            (
                4,
                """
                -- Project thread mapping for strict forum-topic routing
                CREATE TABLE IF NOT EXISTS project_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_slug TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_thread_id INTEGER NOT NULL,
                    topic_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, project_slug),
                    UNIQUE(chat_id, message_thread_id)
                );

                CREATE INDEX IF NOT EXISTS idx_project_threads_chat_active
                    ON project_threads(chat_id, is_active);
                CREATE INDEX IF NOT EXISTS idx_project_threads_slug
                    ON project_threads(project_slug);
                """,
            ),
            (
                5,
                """
                -- Pending requests queue for graceful degradation
                CREATE TABLE IF NOT EXISTS pending_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    working_directory TEXT NOT NULL,
                    queued_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_pending_requests_status
                    ON pending_requests(status, queued_at);
                CREATE INDEX IF NOT EXISTS idx_pending_requests_user
                    ON pending_requests(user_id);
                """,
            ),
            (
                6,
                """
                -- Multi-user collaboration tables

                CREATE TABLE IF NOT EXISTS teams (
                    team_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS team_members (
                    team_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT DEFAULT 'member',
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (team_id, user_id),
                    FOREIGN KEY (team_id) REFERENCES teams(team_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS shared_projects (
                    team_id TEXT NOT NULL,
                    project_path TEXT NOT NULL,
                    shared_session_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (team_id) REFERENCES teams(team_id),
                    UNIQUE(team_id, project_path)
                );

                CREATE INDEX IF NOT EXISTS idx_team_members_user
                    ON team_members(user_id);
                CREATE INDEX IF NOT EXISTS idx_shared_projects_team
                    ON shared_projects(team_id);
                """,
            ),
        ]

    async def _init_pool(self) -> None:
        """Initialize SQLite connection pool."""
        logger.info("Initializing connection pool", size=self._pool_size)

        async with self._pool_lock:
            for _ in range(self._pool_size):
                conn = await aiosqlite.connect(
                    self.database_path, detect_types=sqlite3.PARSE_DECLTYPES
                )
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA foreign_keys = ON")
                self._connection_pool.append(conn)

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[Any]:
        """Get database connection from pool.

        For SQLite, yields an ``aiosqlite.Connection``.
        For PostgreSQL, yields an ``asyncpg.Connection``.

        Callers that use only standard SQL (SELECT, INSERT, UPDATE) with
        ``?`` placeholders will work on SQLite.  Code that needs to work
        with both backends should use the ``compat`` module to translate
        queries.
        """
        if self._backend_type == "postgresql":
            assert self._backend is not None
            async with self._backend.get_connection() as conn:
                yield conn
        else:
            # SQLite path (original logic)
            async with self._pool_lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                else:
                    conn = await aiosqlite.connect(
                        self.database_path, detect_types=sqlite3.PARSE_DECLTYPES
                    )
                    conn.row_factory = aiosqlite.Row
                    await conn.execute("PRAGMA foreign_keys = ON")

            try:
                yield conn
            finally:
                async with self._pool_lock:
                    if len(self._connection_pool) < self._pool_size:
                        self._connection_pool.append(conn)
                    else:
                        await conn.close()

    async def close(self) -> None:
        """Close all connections in pool."""
        logger.info("Closing database connections")

        if self._backend_type == "postgresql" and self._backend:
            await self._backend.close()
        else:
            async with self._pool_lock:
                for conn in self._connection_pool:
                    await conn.close()
                self._connection_pool.clear()

    async def health_check(self) -> bool:
        """Check database health."""
        if self._backend_type == "postgresql" and self._backend:
            return await self._backend.health_check()

        try:
            async with self.get_connection() as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False
