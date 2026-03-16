# Goal Tracking CLI — Interface Definition

## Overview

A synchronous CLI at `src/lockstep/cli.py` that Claude Code invokes via its Bash tool. It talks directly to the SQLite database (`data/bot.db`) using plain `sqlite3`. All commands output JSON to stdout. Errors go to stderr with exit code 1.

Single user — no user_id anywhere.

## Commands

### `set-goal` — Create a new goal

```bash
python -m src.lockstep.cli set-goal \
  --title "Ship v1 of Lockstep" \
  --why "Prove the concept works for personal use" \
  --timeframe monthly \
  --period 2026-03 \
  --parent-goal-id <uuid>       # optional
  --description "..."           # optional
```

Output: `{"id": "uuid", "title": "...", "status": "active", "created": true}`

### `update-goal` — Change status or fields

```bash
python -m src.lockstep.cli update-goal \
  --goal-id <uuid> \
  --status completed             # active / completed / dropped
  --title "new title"            # optional
```

### `record` — Record a daily outcome

```bash
python -m src.lockstep.cli record \
  --goal-id <uuid> \
  --status completed \
  --reason "Finished the chapter" \
  --date 2026-03-16              # optional, defaults to today
  --notes "Took longer than expected"  # optional
```

Uses `INSERT ... ON CONFLICT(goal_id, date) DO UPDATE` — re-recording the same day updates the existing row.

Output: `{"id": "uuid", "goal_id": "...", "date": "2026-03-16", "status": "completed", "updated": false}`

### `list` — List goals

```bash
python -m src.lockstep.cli list                          # all active goals
python -m src.lockstep.cli list --timeframe monthly      # monthly goals only
python -m src.lockstep.cli list --period 2026-03          # goals for March 2026
python -m src.lockstep.cli list --status all              # include completed/dropped
```

Output: JSON array of goal objects with id, title, description, why, timeframe, period, parent_goal_id, status.

### `history` — Get outcome records

```bash
python -m src.lockstep.cli history                        # last 30 days
python -m src.lockstep.cli history --goal-id <uuid>       # specific goal
python -m src.lockstep.cli history --days 7               # last 7 days
python -m src.lockstep.cli history --status skipped       # filter by outcome
```

Output: JSON array of outcome objects, each with the goal title joined in.

### `summary` — Aggregated stats for a period

```bash
python -m src.lockstep.cli summary --period 2026-03       # month summary
python -m src.lockstep.cli summary --period 2026-W11      # week summary
```

Output:
```json
{
  "period": "2026-03",
  "total_outcomes": 45,
  "completed": 30,
  "partial": 8,
  "skipped": 5,
  "missed": 2,
  "completion_rate": 0.67,
  "by_goal": [
    {"goal_id": "...", "title": "...", "completed": 10, "total": 15, "rate": 0.67,
     "top_skip_reasons": ["meetings ran long", "low energy"]}
  ],
  "current_streak": 3,
  "longest_streak": 7
}
```

### `schedule-checkin` — Schedule a proactive check-in

```bash
python -m src.lockstep.cli schedule-checkin \
  --time "14:00" \
  --context "Check on system design progress"
```

Writes to `scheduled_checkins` table. The bot's JobScheduler polls for new rows every 30s, creates a DateTrigger APScheduler job, and fires it through the existing EventBus → AgentHandler → NotificationService pipeline.

### `list-checkins` — List pending check-ins

```bash
python -m src.lockstep.cli list-checkins
```

### `cancel-checkin` — Cancel a pending check-in

```bash
python -m src.lockstep.cli cancel-checkin --id <uuid>
```

## Data Model (SQLite)

### `goals` table

| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID |
| title | TEXT NOT NULL | Short name |
| description | TEXT | What this goal means |
| why | TEXT | Why it matters |
| timeframe | TEXT NOT NULL | yearly / monthly / weekly |
| parent_goal_id | TEXT FK | Links to parent goal |
| period | TEXT NOT NULL | "2026", "2026-03", "2026-W11" |
| status | TEXT NOT NULL | active / completed / dropped (default: active) |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### `goal_outcomes` table

| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID |
| goal_id | TEXT FK NOT NULL | References goals.id |
| date | TEXT NOT NULL | ISO date |
| status | TEXT NOT NULL | completed / partial / skipped / missed |
| reason | TEXT | Why it succeeded or failed |
| notes | TEXT | Additional context |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**Unique constraint:** One outcome per (goal_id, date).

### `scheduled_checkins` table

| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID |
| fire_at | TIMESTAMP NOT NULL | When to fire (UTC) |
| context | TEXT NOT NULL | Free-text context for the prompt |
| user_id | INTEGER NOT NULL | Telegram user ID (from ALLOWED_USERS) |
| chat_id | INTEGER NOT NULL | Telegram chat ID (from NOTIFICATION_CHAT_IDS) |
| session_id | TEXT | Claude session ID to resume (optional) |
| status | TEXT | pending / fired / cancelled (default: pending) |
| job_id | TEXT | APScheduler job ID (set by scheduler when picked up) |
| created_at | TIMESTAMP | |
| fired_at | TIMESTAMP | |

## Implementation

### File Structure

```
src/lockstep/
    __init__.py          # empty
    __main__.py          # enables python -m src.lockstep.cli
    db.py                # sync SQLite wrapper (~150 lines)
    cli.py               # argparse CLI, JSON output (~200 lines)
```

### Database Path

Reads `DATABASE_URL` env var (default `sqlite:///data/bot.db`), same as the bot. Strips the `sqlite:///` prefix. Tables created both by bot migration (migration 5) and by CLI's `CREATE TABLE IF NOT EXISTS` for standalone use.

### No Over-Engineering

- No async code. Synchronous `sqlite3`.
- No models/dataclasses. Dicts from `sqlite3.Row`.
- No repository classes. Raw SQL in `db.py`.
- No MCP server or tool registration.
- No user_id columns (single user).
