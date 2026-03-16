from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone


def get_db() -> sqlite3.Connection:
    """Open connection. Read DATABASE_URL env var, strip sqlite:/// prefix, default data/bot.db."""
    db_url = os.environ.get("DATABASE_URL", "sqlite:///data/bot.db")
    if db_url.startswith("sqlite:///"):
        db_path = db_url[len("sqlite:///") :]
    else:
        db_path = db_url
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_tables(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS for goals, goal_outcomes, scheduled_checkins."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            why TEXT,
            timeframe TEXT NOT NULL CHECK(timeframe IN ('yearly', 'monthly', 'weekly')),
            parent_goal_id TEXT,
            period TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active', 'completed', 'dropped')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_goal_id) REFERENCES goals(id)
        );

        CREATE TABLE IF NOT EXISTS goal_outcomes (
            id TEXT PRIMARY KEY,
            goal_id TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('completed', 'partial', 'skipped', 'missed')),
            reason TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (goal_id) REFERENCES goals(id),
            UNIQUE(goal_id, date)
        );

        CREATE TABLE IF NOT EXISTS scheduled_checkins (
            id TEXT PRIMARY KEY,
            fire_at TIMESTAMP NOT NULL,
            context TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            session_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'fired', 'cancelled')),
            job_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fired_at TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_goals_status
            ON goals(status);
        CREATE INDEX IF NOT EXISTS idx_goals_timeframe_period
            ON goals(timeframe, period);
        CREATE INDEX IF NOT EXISTS idx_goal_outcomes_goal_date
            ON goal_outcomes(goal_id, date);
        CREATE INDEX IF NOT EXISTS idx_goal_outcomes_date
            ON goal_outcomes(date);
        CREATE INDEX IF NOT EXISTS idx_scheduled_checkins_status
            ON scheduled_checkins(status);
        CREATE INDEX IF NOT EXISTS idx_scheduled_checkins_fire_at
            ON scheduled_checkins(fire_at);
        """)


def create_goal(
    conn: sqlite3.Connection,
    title: str,
    why: str,
    timeframe: str,
    period: str,
    parent_goal_id: str | None = None,
    description: str | None = None,
) -> dict:
    """Insert a new goal. Returns the created goal as dict."""
    goal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO goals (id, title, description, why, timeframe,
           parent_goal_id, period, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
        (goal_id, title, description, why, timeframe, parent_goal_id, period, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return dict(row)


def update_goal(
    conn: sqlite3.Connection,
    goal_id: str,
    status: str | None = None,
    title: str | None = None,
) -> dict:
    """Update goal fields. Returns updated goal."""
    now = datetime.now(timezone.utc).isoformat()
    sets: list[str] = ["updated_at = ?"]
    params: list[str | None] = [now]
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if title is not None:
        sets.append("title = ?")
        params.append(title)
    params.append(goal_id)
    conn.execute(
        f"UPDATE goals SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if row is None:
        raise ValueError(f"Goal not found: {goal_id}")
    return dict(row)


def list_goals(
    conn: sqlite3.Connection,
    timeframe: str | None = None,
    period: str | None = None,
    status: str = "active",
) -> list[dict]:
    """List goals with optional filters. status='all' returns everything."""
    clauses: list[str] = []
    params: list[str] = []
    if status != "all":
        clauses.append("status = ?")
        params.append(status)
    if timeframe is not None:
        clauses.append("timeframe = ?")
        params.append(timeframe)
    if period is not None:
        clauses.append("period = ?")
        params.append(period)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM goals{where} ORDER BY created_at DESC", params
    ).fetchall()
    return [dict(r) for r in rows]


def record_outcome(
    conn: sqlite3.Connection,
    goal_id: str,
    status: str,
    reason: str | None = None,
    date: str | None = None,
    notes: str | None = None,
) -> dict:
    """Record daily outcome. UPSERT on (goal_id, date). date defaults to today ISO."""
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outcome_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO goal_outcomes (id, goal_id, date, status, reason, notes,
           created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(goal_id, date) DO UPDATE SET
               status = excluded.status,
               reason = excluded.reason,
               notes = excluded.notes,
               updated_at = excluded.updated_at""",
        (outcome_id, goal_id, date, status, reason, notes, now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM goal_outcomes WHERE goal_id = ? AND date = ?",
        (goal_id, date),
    ).fetchone()
    return dict(row)


def get_history(
    conn: sqlite3.Connection,
    goal_id: str | None = None,
    days: int = 30,
    status: str | None = None,
) -> list[dict]:
    """Get outcome history. JOIN goal title. Order by date DESC."""
    clauses: list[str] = [
        "o.date >= date('now', ?)",
    ]
    params: list[str | int] = [f"-{days} days"]
    if goal_id is not None:
        clauses.append("o.goal_id = ?")
        params.append(goal_id)
    if status is not None:
        clauses.append("o.status = ?")
        params.append(status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT o.*, g.title AS goal_title
            FROM goal_outcomes o
            JOIN goals g ON g.id = o.goal_id
            {where}
            ORDER BY o.date DESC""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def _week_date_range(period: str) -> tuple[str, str]:
    """Given '2026-W11', return (monday_iso, sunday_iso)."""
    monday = datetime.strptime(period + "-1", "%G-W%V-%u").date()
    sunday = datetime.strptime(period + "-7", "%G-W%V-%u").date()
    return monday.isoformat(), sunday.isoformat()


def get_summary(conn: sqlite3.Connection, period: str) -> dict:
    """Aggregated stats for a period (month like '2026-03' or week like '2026-W11')."""
    if "-W" in period:
        start_date, end_date = _week_date_range(period)
        date_filter = "o.date >= ? AND o.date <= ?"
        date_params: list[str] = [start_date, end_date]
        year = period.split("-W")[0]
        goal_filter = (
            "(g.status = 'active' OR g.updated_at >= ?) "
            "AND (g.period = ? OR (g.timeframe = 'yearly' AND g.period = ?))"
        )
        goal_params: list[str] = [start_date, period, year]
    else:
        date_filter = "o.date LIKE ?"
        date_params = [period + "-%"]
        year = period.split("-")[0]
        goal_filter = (
            "(g.status = 'active' OR g.updated_at >= ?) "
            "AND (g.period = ? OR (g.timeframe = 'yearly' AND g.period = ?))"
        )
        goal_params = [period + "-01", period, year]

    # Total goals matching the period
    goal_rows = conn.execute(
        f"SELECT id, title FROM goals g WHERE {goal_filter}",
        goal_params,
    ).fetchall()
    total_goals = len(goal_rows)
    goal_ids = [r["id"] for r in goal_rows]

    if not goal_ids:
        return {
            "period": period,
            "total_goals": 0,
            "total_outcomes": 0,
            "completion_rate": 0.0,
            "by_goal": [],
            "top_skip_reasons": [],
        }

    placeholders = ",".join("?" * len(goal_ids))

    # Total outcomes
    outcome_rows = conn.execute(
        f"""SELECT o.goal_id, o.status, o.reason
            FROM goal_outcomes o
            WHERE o.goal_id IN ({placeholders}) AND {date_filter}""",
        goal_ids + date_params,
    ).fetchall()

    total_outcomes = len(outcome_rows)
    completed_count = sum(1 for r in outcome_rows if r["status"] == "completed")
    completion_rate = (
        round(completed_count / total_outcomes * 100, 1) if total_outcomes else 0.0
    )

    # By goal breakdown
    by_goal: list[dict] = []
    goal_title_map = {r["id"]: r["title"] for r in goal_rows}
    for gid in goal_ids:
        g_outcomes = [r for r in outcome_rows if r["goal_id"] == gid]
        g_total = len(g_outcomes)
        g_completed = sum(1 for r in g_outcomes if r["status"] == "completed")
        g_partial = sum(1 for r in g_outcomes if r["status"] == "partial")
        g_skipped = sum(1 for r in g_outcomes if r["status"] == "skipped")
        g_missed = sum(1 for r in g_outcomes if r["status"] == "missed")
        g_rate = round(g_completed / g_total * 100, 1) if g_total else 0.0
        by_goal.append(
            {
                "title": goal_title_map[gid],
                "total": g_total,
                "completed": g_completed,
                "partial": g_partial,
                "skipped": g_skipped,
                "missed": g_missed,
                "completion_rate": g_rate,
            }
        )

    # Top skip reasons
    reasons: dict[str, int] = {}
    for r in outcome_rows:
        if r["status"] in ("skipped", "missed") and r["reason"]:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    reason_list: list[dict[str, str | int]] = [
        {"reason": k, "count": v} for k, v in reasons.items()
    ]
    reason_list.sort(key=lambda x: -int(x["count"]))  # type: ignore[arg-type]
    top_skip_reasons = reason_list[:5]

    return {
        "period": period,
        "total_goals": total_goals,
        "total_outcomes": total_outcomes,
        "completion_rate": completion_rate,
        "by_goal": by_goal,
        "top_skip_reasons": top_skip_reasons,
    }


def schedule_checkin(
    conn: sqlite3.Connection,
    fire_at_str: str,
    context: str,
    user_id: int,
    chat_id: int,
    session_id: str | None = None,
) -> dict:
    """Create a pending checkin. fire_at_str is ISO timestamp."""
    checkin_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO scheduled_checkins
           (id, fire_at, context, user_id, chat_id, session_id, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (checkin_id, fire_at_str, context, user_id, chat_id, session_id, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM scheduled_checkins WHERE id = ?", (checkin_id,)
    ).fetchone()
    return dict(row)


def list_checkins(
    conn: sqlite3.Connection,
    status: str = "pending",
) -> list[dict]:
    """List checkins by status."""
    rows = conn.execute(
        "SELECT * FROM scheduled_checkins WHERE status = ? ORDER BY fire_at ASC",
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]


def cancel_checkin(conn: sqlite3.Connection, checkin_id: str) -> dict:
    """Set status=cancelled. Returns updated checkin."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE scheduled_checkins SET status = 'cancelled', fired_at = ? WHERE id = ?",
        (now, checkin_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM scheduled_checkins WHERE id = ?", (checkin_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Checkin not found: {checkin_id}")
    return dict(row)


def get_pending_checkins_without_job(conn: sqlite3.Connection) -> list[dict]:
    """For scheduler polling: pending checkins where job_id IS NULL."""
    rows = conn.execute(
        """SELECT * FROM scheduled_checkins
           WHERE status = 'pending' AND job_id IS NULL
           ORDER BY fire_at ASC""",
    ).fetchall()
    return [dict(r) for r in rows]


def mark_checkin_picked_up(
    conn: sqlite3.Connection, checkin_id: str, job_id: str
) -> None:
    """Set job_id on a checkin (scheduler claimed it)."""
    conn.execute(
        "UPDATE scheduled_checkins SET job_id = ? WHERE id = ?",
        (job_id, checkin_id),
    )
    conn.commit()


def mark_checkin_fired(conn: sqlite3.Connection, checkin_id: str) -> None:
    """Set status=fired, fired_at=now."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE scheduled_checkins SET status = 'fired', fired_at = ? WHERE id = ?",
        (now, checkin_id),
    )
    conn.commit()
