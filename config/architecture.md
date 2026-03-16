# Lockstep — Architecture

## What It Is

A personal prioritization coach powered by Claude Code as the agent runtime. Single-user prototype — built for the developer's own use. The user interacts via Telegram; the bot is a thin delivery layer that forwards messages to Claude Code and sends responses back.

## How the User Experiences It

The agent is **active, not passive**. It doesn't wait for the user to check in — it initiates contact based on the user's goals and progress.

```
Morning: Agent messages with today's 1-2 priorities + reasoning
         Also names what to skip today and why
Midday:  Agent checks in on progress (timed to the task)
         "How's the system design chapter going?"
Evening: Agent asks for outcome — done, partial, skipped? Why?
         Records result, optionally previews tomorrow

Weekly:  Sunday evening review — completion data, pattern analysis,
         goal adjustments, next week's plan

User can also message anytime:
  "I got pulled into a meeting, can't finish today"
  → Agent adjusts, no guilt, records the reason
```

The user never sees Claude Code, SDKs, databases, or tools. They see a coach who knows them, checks on them, and keeps them focused throughout the day.

## Technical Stack

```
Telegram (user interface)
    │
    ▼
Claude Code (agent runtime, via claude-agent-sdk)
    │
    ├── Agent Personality (config/agent.claude.md — static system prompt)
    ├── User Profile (profiles/user.md — agent-owned markdown)
    ├── Goal Tracking (SQLite via CLI — python -m src.lockstep.cli)
    └── Check-in Scheduler (SQLite + APScheduler polling)
```

Built on top of [claude-code-telegram](https://github.com/gx-ai-architect/claude-code-telegram), which provides: Claude Code integration (via `claude-agent-sdk`), Telegram bot infrastructure (auth, session resume, message routing, streaming), and APScheduler for proactive agent-initiated messages.

## Components

### 1. Agent Personality (`config/agent.claude.md`)

Static markdown file loaded as system prompt every session via `AGENT_CLAUDE_MD_PATH`. Defines:
- Who the agent is and its coaching philosophy
- Communication style (concise, direct, Telegram-friendly)
- How to use tools (always load profile + goals before responding)
- Profile update triggers and rules
- General principles (fewer is better, user always succeeds, no guilt)

Does **not** contain user-specific decision rules — those live in the user profile.

### 2. Claude Code (Runtime)

The agent brain. Handles all reasoning, conversation, and coaching logic.

What Claude Code gives us for free:
- Natural language understanding and generation
- Session resume (conversation continuity across messages)
- Auto Memory (learns project patterns across sessions in `~/.claude/projects/`)
- File tools (Read/Edit/Write for profile access)
- Bash tool (for CLI commands — goal tracking and scheduling)

Configuration:
- `AGENT_CLAUDE_MD_PATH=config/agent.claude.md`
- `LOAD_PROJECT_CLAUDE_MD=false` — prevents loading the repo's dev CLAUDE.md
- `AGENTIC_MODE=true`
- Session auto-resume via existing bot integration

### 3. User Profile (`profiles/user.md`)

A single markdown file the agent reads at session start and updates through conversation. Claude Code reads/writes it directly using its native file tools. No custom tooling needed.

**Three sections:**

**Soul & Motivation** — What drives this person
- Core values discovered through conversation
- What they care about deeply vs. what they think they should care about
- Updated when user states values or changes goals

**Decision Framework** — Learned prioritization rules
- Relative priorities (e.g., "health >= career growth")
- Constraints (e.g., "mornings are peak productive time", "Wednesdays packed with meetings")
- Scheduling preferences (e.g., "weekly review on Sunday evening")
- Anti-patterns (e.g., "over-commits at work when stressed")
- Updated from explicit user feedback and observed patterns

**Patterns** — Observed behavioral data (evidence-based, not self-reported)
- Completion tendencies by goal type, day of week, time of day
- Recurring skip/failure reasons
- Response to different coaching approaches
- Updated during evening check-ins and weekly reviews, backed by goal outcome data

**Bootstrap:** After onboarding, Soul & Motivation and Decision Framework are populated from conversation. Patterns starts empty — it fills from actual data over the first 1-2 weeks. Stated preferences ("I'm a morning person") go in Decision Framework; whether that's true goes in Patterns after evidence confirms it.

### 4. Goal Tracking CLI (`src/lockstep/cli.py`)

Structured data store for goals and daily outcomes. SQLite database, accessed via a synchronous CLI that Claude Code calls through its Bash tool. No MCP.

```bash
# Claude Code calls these via Bash tool:
python -m src.lockstep.cli set-goal --title "..." --why "..." --timeframe monthly --period 2026-03
python -m src.lockstep.cli list --timeframe monthly
python -m src.lockstep.cli record --goal-id <uuid> --status completed --reason "..."
python -m src.lockstep.cli history --days 7
python -m src.lockstep.cli summary --period 2026-W11
python -m src.lockstep.cli update-goal --goal-id <uuid> --status dropped
```

All commands output JSON to stdout. Errors go to stderr with exit code 1.

**Schema:**

`goals` table — goal definitions
- id (UUID), title, description, why, timeframe (yearly/monthly/weekly), parent_goal_id, period, status (active/completed/dropped), timestamps
- No user_id — single user

`goal_outcomes` table — daily completion records
- id (UUID), goal_id (FK), date, status (completed/partial/skipped/missed), reason, notes, timestamps
- Unique constraint on (goal_id, date); re-recording updates via upsert

**Implementation:** `src/lockstep/cli.py` (~200 lines), `src/lockstep/db.py` (~150 lines synchronous sqlite3 wrapper), `src/lockstep/__main__.py` (entry point). Tables created both by bot migration (migration 5 in `database.py`) and by CLI's own `CREATE TABLE IF NOT EXISTS` for standalone use.

### 5. Check-in Scheduler

The agent controls when it next reaches out. At the end of conversations, it calls a CLI command to schedule the next check-in.

**How it works:**

```bash
# Agent calls via Bash:
python -m src.lockstep.cli schedule-checkin --time "14:00" --context "Check on system design progress"
python -m src.lockstep.cli list-checkins
python -m src.lockstep.cli cancel-checkin --id <uuid>
```

1. CLI writes a row to `scheduled_checkins` table (status=pending, job_id=NULL)
2. `JobScheduler` polls every 30s for new pending check-ins without a job_id
3. Creates a `DateTrigger` APScheduler job for each
4. At fire time: publishes `ScheduledEvent` → `AgentHandler` → `ClaudeIntegration.run_command()` → `NotificationService` → Telegram

**Check-in prompt template:** When a check-in fires, Claude Code receives the stored context and instructions to read the profile and goals before responding. The `session_id` is passed for conversation resume when available.

**`scheduled_checkins` table:**
- id (UUID), fire_at (TIMESTAMP), context (TEXT), user_id, chat_id, session_id (optional), status (pending/fired/cancelled), job_id (set by scheduler), timestamps

**Weekly review:** A recurring cron job (`0 18 * * 0` — Sunday 6pm UTC) seeded at startup. Uses the existing `JobScheduler.add_job()` with cron expression. The prompt instructs Claude to load the profile, run `summary` and `history` commands, analyze patterns, update the profile, and send a concise review to the user.

## Data Flow

### Morning Priorities (Agent-Initiated)
```
Scheduler fires morning check-in
  → Claude Code starts with check-in prompt + context
  → Reads profiles/user.md (soul, framework, patterns)
  → Runs: python -m src.lockstep.cli list --timeframe monthly
  → Runs: python -m src.lockstep.cli history --days 3
  → Reasons about today's priority using profile + recent data
  → Sends 1-2 priorities with reasoning + what to skip
  → Schedules midday check-in via schedule-checkin CLI
  → Delivers to Telegram via NotificationService
```

### Midday Check-in (Agent-Initiated)
```
Scheduler fires midday check-in
  → Claude Code sees context: "Check on system design progress"
  → Resumes session (has conversation history)
  → Sends brief check-in: "How's chapter 4 going?"
  → User replies → normal conversation flow
```

### Evening Outcome (Agent-Initiated)
```
Scheduler fires evening check-in
  → Claude asks what happened: done / partial / skipped?
  → User responds with outcome + reason
  → Agent runs: python -m src.lockstep.cli record --goal-id <id> --status completed --reason "..."
  → Agent checks if outcome reveals new pattern
  → If yes: reads profiles/user.md, edits Patterns section
  → Optionally previews tomorrow
  → Schedules next morning check-in
```

### Weekly Review (Cron — Sunday Evening)
```
Cron fires weekly review job
  → Claude Code reads profiles/user.md
  → Runs: python -m src.lockstep.cli summary --period 2026-W11
  → Runs: python -m src.lockstep.cli history --days 7
  → Analyzes: completion rates, day-of-week patterns, recurring skip reasons
  → Updates all 3 profile sections based on evidence
  → Sends concise summary: wins, drops, next week's plan
  → Asks user for adjustments
  → Incorporates feedback, updates profile and goals
```

### Recording a Value (User-Initiated)
```
User says "actually health is more important to me than career right now"
  → Agent finishes conversational turn
  → Reads profiles/user.md
  → Edits Soul & Motivation and Decision Framework sections
  → Confirms: "Noted — I'll weight health over career in future recommendations"
  → Future daily recommendations shift accordingly
```

## User Experience Details

### Onboarding (First Interaction)

Conversational, not a questionnaire. One question at a time.

1. "What's the one thing you most want to be true by the end of this year?" — singular
2. Go deeper: "Why does this matter?" + "Where are you now vs. where you want to be?"
3. "Is there anything else at that level of importance?" — let user volunteer, cap at 3
4. Monthly breakdown per goal: "What would meaningful progress look like by end of this month?"
5. Close with summary and confirmation

Takes 10-15 minutes of texting. Can split across 2-3 sessions if interrupted. After onboarding, agent creates `profiles/user.md` with populated Soul & Motivation and Decision Framework, empty Patterns.

### Silence Handling

- Day 1: Normal messages, record "no response" not "missed"
- Day 2: Lighter morning message, acknowledge the gap without pressure
- Days 3-5: One message/day, morning only, shorter
- 5+ days: One final "I'm here when you're ready" message, then silence
- Re-engagement: Welcome back briefly, ask what matters today, offer recap only if gap was 5+ days

### Goal Evolution

- **User-driven:** User says "I don't care about X anymore" → agent confirms, updates goals and profile
- **Agent-initiated (pattern-driven):**
  - 3+ weeks of consistent skipping → suggest dropping
  - Consistent overperformance → suggest raising the bar
  - Conflict patterns → suggest explicit ranking
  - Monthly boundary → expanded review of yearly progress
- Goals are never silently deleted — dropped goals stay as historical data with status and reason

## What We Build vs. What Exists

| Concern | Who Handles It |
|---|---|
| Reasoning & coaching logic | Claude Code (existing) |
| Conversation continuity | Claude Code sessions (existing) |
| Message transport & auth | claude-code-telegram (existing) |
| Scheduler infrastructure | APScheduler + EventBus pipeline (existing) |
| Agent personality | `config/agent.claude.md` (**new** — static file) |
| User values & patterns | `profiles/user.md` (**new** — agent-owned markdown) |
| Goal definitions & outcomes | `src/lockstep/cli.py` (**new** — CLI + SQLite) |
| Check-in scheduling | `schedule-checkin` CLI + scheduler polling (**new**) |
| Weekly review cron | Seeded at startup (**new** — uses existing cron infra) |

## Files to Create

| File | Purpose | ~Lines |
|---|---|---|
| `src/lockstep/__init__.py` | Package init | 0 |
| `src/lockstep/__main__.py` | `python -m` entry point | 3 |
| `src/lockstep/db.py` | Sync SQLite wrapper | 150 |
| `src/lockstep/cli.py` | Argparse CLI, JSON output | 200 |
| `profiles/` | Directory for user profile | — |

## Files to Modify

| File | Change |
|---|---|
| `src/storage/database.py` | Add migration 5: goals + goal_outcomes + scheduled_checkins tables |
| `src/scheduler/scheduler.py` | Add `DateTrigger` import, `add_checkin_job()`, `_poll_new_checkins()` (30s interval), `_build_checkin_prompt()`, mark-as-fired logic |
| `src/events/types.py` | Add `user_id` and `session_id` fields to `ScheduledEvent` |
| `src/events/handlers.py` | Pass `user_id`/`session_id` from `ScheduledEvent` to `run_command()` |
| `src/main.py` | Seed weekly review cron job at startup |

## Deployment

```env
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_BOT_USERNAME=lockstep_bot
APPROVED_DIRECTORY=/path/to/workdir
AGENT_CLAUDE_MD_PATH=config/agent.claude.md
LOAD_PROJECT_CLAUDE_MD=false
AGENTIC_MODE=true
ALLOWED_USERS=<your_telegram_id>
NOTIFICATION_CHAT_IDS=<your_chat_id>
ENABLE_SCHEDULER=true
```

Claude Code must be installed and authenticated (`claude login`) on the host machine. No API keys required.
