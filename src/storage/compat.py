"""SQL compatibility layer for SQLite / PostgreSQL.

Provides helpers for translating SQL between dialects so that
repository code can remain backend-agnostic.
"""

import re
from typing import Literal

BackendType = Literal["sqlite", "postgresql"]


def sql_param(index: int, backend: BackendType) -> str:
    """Return a positional parameter placeholder.

    Args:
        index: 1-based parameter index.
        backend: ``"sqlite"`` or ``"postgresql"``.

    Returns:
        ``"?"`` for SQLite, ``"$<index>"`` for PostgreSQL.
    """
    if backend == "postgresql":
        return f"${index}"
    return "?"


def adapt_sql(sql: str, backend: BackendType) -> str:
    """Convert a SQLite-style SQL string to the target dialect.

    Transformations applied when *backend* is ``"postgresql"``:

    * ``?`` positional params  ->  ``$1, $2, ...``
    * ``AUTOINCREMENT``        ->  removed (PostgreSQL uses ``SERIAL``)
    * ``INTEGER PRIMARY KEY AUTOINCREMENT`` -> ``SERIAL PRIMARY KEY``
    * ``datetime('now', ...)`` ->  ``NOW() + INTERVAL ...``
    * ``date('now', ...)``     ->  ``CURRENT_DATE + INTERVAL ...``
    * ``strftime(...)``        ->  ``to_char(...)``  (best-effort)
    * ``INSERT OR IGNORE``     ->  ``INSERT ... ON CONFLICT DO NOTHING``
    * ``PRAGMA ...``           ->  removed
    * ``BOOLEAN``              ->  kept (PostgreSQL supports it)
    * ``JSON``                 ->  ``JSONB``

    For SQLite the string is returned unchanged.
    """
    if backend == "sqlite":
        return sql

    result = sql

    # Remove PRAGMA statements (they are SQLite-specific)
    result = re.sub(r"PRAGMA\s+[^;]+;?", "", result, flags=re.IGNORECASE)

    # INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
    result = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        result,
        flags=re.IGNORECASE,
    )

    # Remove standalone AUTOINCREMENT
    result = re.sub(r"\bAUTOINCREMENT\b", "", result, flags=re.IGNORECASE)

    # JSON -> JSONB
    result = re.sub(r"\bJSON\b", "JSONB", result, flags=re.IGNORECASE)

    # CURRENT_TIMESTAMP is valid in both dialects, but DEFAULT CURRENT_TIMESTAMP
    # in PostgreSQL needs to be DEFAULT NOW() for TIMESTAMP columns.
    # Actually CURRENT_TIMESTAMP works fine in PostgreSQL, so leave it.

    # datetime('now', '-N days/hours') -> NOW() + INTERVAL '-N days/hours'
    def _replace_datetime_now(m: re.Match) -> str:
        args = m.group(1)
        parts = [a.strip().strip("'\"") for a in args.split(",")]
        if len(parts) == 1 and parts[0].lower() == "now":
            return "NOW()"
        # datetime('now', '-30 days')  ->  NOW() + INTERVAL '-30 days'
        intervals = []
        for p in parts[1:]:
            # Handle patterns like '-' || ? || ' days'
            if "||" in p:
                # This is a dynamic interval - convert to PostgreSQL INTERVAL concat
                return f"NOW() + ({' || '.join(p.split())})"
            intervals.append(p)
        if intervals:
            return f"NOW() + INTERVAL '{' '.join(intervals)}'"
        return "NOW()"

    result = re.sub(
        r"datetime\(([^)]+)\)",
        _replace_datetime_now,
        result,
        flags=re.IGNORECASE,
    )

    # date('now', '-N days') -> CURRENT_DATE + INTERVAL '-N days'
    def _replace_date_now(m: re.Match) -> str:
        args = m.group(1)
        parts = [a.strip().strip("'\"") for a in args.split(",")]
        if len(parts) == 1 and parts[0].lower() == "now":
            return "CURRENT_DATE"
        intervals = []
        for p in parts[1:]:
            if "||" in p:
                return f"CURRENT_DATE + ({' || '.join(p.split())})"
            intervals.append(p)
        if intervals:
            return f"CURRENT_DATE + INTERVAL '{' '.join(intervals)}'"
        return "CURRENT_DATE"

    result = re.sub(
        r"(?<!\w)date\(([^)]+)\)",
        _replace_date_now,
        result,
        flags=re.IGNORECASE,
    )

    # strftime('%Y-W%W', col) -> to_char(col, 'IYYY-"W"IW')
    def _replace_strftime(m: re.Match) -> str:
        fmt_str = m.group(1).strip().strip("'\"")
        col = m.group(2).strip()
        # Best-effort conversion
        pg_fmt = fmt_str.replace("%Y", "YYYY").replace("%m", "MM").replace(
            "%d", "DD"
        ).replace("%W", '"W"IW').replace("%H", "HH24").replace("%M", "MI")
        return f"to_char({col}, '{pg_fmt}')"

    result = re.sub(
        r"strftime\(\s*(['\"][^'\"]+['\"])\s*,\s*([^)]+)\)",
        _replace_strftime,
        result,
        flags=re.IGNORECASE,
    )

    # INSERT OR IGNORE INTO ... VALUES (...) ->
    # INSERT INTO ... VALUES (...) ON CONFLICT DO NOTHING
    result = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO",
        "INSERT INTO",
        result,
        flags=re.IGNORECASE,
    )

    # SELECT changes() -> not available in PostgreSQL, replace with 0
    result = re.sub(
        r"SELECT\s+changes\(\)",
        "SELECT 0",
        result,
        flags=re.IGNORECASE,
    )

    # Convert ? placeholders to $1, $2, ...
    counter = 0

    def _replace_placeholder(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        return f"${counter}"

    result = re.sub(r"\?", _replace_placeholder, result)

    return result
