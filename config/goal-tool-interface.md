# Goal Tracking Tool — Interface Definition

## Overview

A structured data store for goal definitions and completion records. Claude reads from it to make informed recommendations and writes to it to record outcomes. This is a factual ledger — not a context management system.

## Operations

### 1. `set_goal`

Create or update a goal definition.

**Input:**
- `title` (string) — short name
- `description` (string) — what this goal means, in the user's words
- `why` (string) — why this matters, articulated reasoning
- `timeframe` (enum: `yearly` | `monthly` | `weekly`)
- `parent_goal_id` (optional string) — links a monthly goal to its yearly parent
- `period` (string) — e.g. "2026", "2026-03", "2026-W11"

**Behavior:** Creates new or updates existing. A goal can be marked `active`, `completed`, `dropped`.

---

### 2. `record_outcome`

Record what happened with a daily priority.

**Input:**
- `date` (string) — ISO date, e.g. "2026-03-15"
- `goal_id` (string) — which goal this relates to
- `status` (enum: `completed` | `partial` | `skipped` | `missed`)
- `reason` (string) — why it succeeded or failed, in the user's words or agent-summarized
- `notes` (optional string) — any additional context

**Behavior:** One record per goal per day. Can be updated if the user revises.

---

### 3. `get_goals`

Retrieve active goal definitions.

**Input:**
- `timeframe` (optional enum: `yearly` | `monthly` | `weekly`) — filter by type
- `period` (optional string) — filter by period
- `include_dropped` (optional bool, default false)

**Returns:** List of goals with their definitions, why, status, and parent linkage.

---

### 4. `get_history`

Retrieve completion records for analysis.

**Input:**
- `goal_id` (optional string) — filter to specific goal
- `date_from` (optional string) — start date
- `date_to` (optional string) — end date
- `status` (optional enum) — filter by outcome

**Returns:** List of outcome records with dates, statuses, and reasons.

---

### 5. `get_summary`

Aggregated view for periodic reviews.

**Input:**
- `period` (string) — e.g. "2026-03" for March, "2026-W11" for a week
- `goal_id` (optional string) — specific goal or all

**Returns:**
- Total days with goals set
- Completion rate (completed / total)
- Most common skip/failure reasons
- Streak information (consecutive completions)

---

## Data Model (SQLite)

### `goals` table
| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID |
| user_id | INTEGER | Telegram user ID |
| title | TEXT | Short name |
| description | TEXT | What this goal means |
| why | TEXT | Why it matters |
| timeframe | TEXT | yearly / monthly / weekly |
| parent_goal_id | TEXT FK | Links to parent goal |
| period | TEXT | "2026", "2026-03", etc. |
| status | TEXT | active / completed / dropped |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### `goal_outcomes` table
| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID |
| user_id | INTEGER | Telegram user ID |
| goal_id | TEXT FK | References goals.id |
| date | TEXT | ISO date |
| status | TEXT | completed / partial / skipped / missed |
| reason | TEXT | Why it succeeded or failed |
| notes | TEXT | Additional context |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**Unique constraint:** One outcome per (user_id, goal_id, date).

## Implementation Options

**Option A: MCP Server**
- Standalone MCP server that the bot connects to via existing MCP support
- Claude calls it like any other tool
- Clean separation, no changes to bot core code

**Option B: Built-in tool via SDK**
- Add tables to existing SQLite database
- Expose as tools via the SDK's tool system
- Tighter integration, simpler deployment

Both use the same interface above. The choice is architectural.
