# Overachiever — Architecture

## What It Is

A personal prioritization coach powered by Claude Code as the agent runtime. The user interacts via Telegram — the bot is just a thin delivery layer that forwards messages to Claude Code and sends responses back.

## How the User Experiences It

```
User opens Telegram → sends "morning" →
Agent loads user profile + goal history →
Agent proposes today's 1-2 priorities with reasoning →
User confirms or pushes back →
Agent records the plan →
...later...
User says "done with the system design chapter" →
Agent records completion, asks about the next day
```

The user never sees Claude Code, SDKs, databases, or tools. They see a coach who knows them, remembers their goals, and helps them focus.

## Technical Stack

```
Telegram (user interface)
    │
    ▼
Claude Code (agent runtime, via claude-agent-sdk)
    │
    ├── Agent Personality (static markdown, system prompt)
    ├── User Profile (per-user markdown file, read/written by agent)
    └── Goal Tracking (SQLite, structured outcome data)
```

This project is built on top of [claude-code-telegram](https://github.com/gx-ai-architect/claude-code-telegram), which already provides Claude Code integration (via `claude-agent-sdk`) and Telegram bot infrastructure (auth, session resume, message routing, streaming progress). We build the agent personality and goal tracking tools on top of that existing foundation.

## Components

### 1. Agent Personality (`config/agent.claude.md`)

Static markdown file loaded as system prompt every session. Defines:
- Who the agent is and its coaching philosophy
- Communication style (concise, direct, Telegram-friendly)
- How to use the tools (always load profile + history before responding)
- General principles (fewer is better, user always succeeds, no guilt)

Does **not** contain user-specific decision rules — those live in the user profile.

### 2. Claude Code (Runtime)

The agent brain. Handles all reasoning, conversation, and coaching logic. We don't build any of this.

What Claude Code gives us for free:
- Natural language understanding and generation
- Session resume (conversation continuity across messages)
- Native memory features
- Tool calling (reads/writes structured data via goal tools)

Configuration:
- `AGENT_CLAUDE_MD_PATH` — points to the personality file
- `LOAD_PROJECT_CLAUDE_MD=false` — prevents loading the repo's dev docs as agent context
- Session auto-resume via the existing bot integration

### 3. User Profile (Per-User Markdown File)

A markdown file per user (e.g., `profiles/{user_id}.md`) that the agent reads at session start and updates through conversation. Claude Code reads and writes it directly using its native file tools.

**Three sections:**

**Soul/Motivation** — What drives this person
- Core values discovered through conversation
- What they care about deeply vs. what they think they should care about
- Updated when user expresses preferences ("A matters to me, B doesn't")

**Decision Framework** — Learned prioritization rules for this user
- Relative priorities (e.g., "family > fitness", "career growth is the current focus")
- Constraints (e.g., "mornings are productive", "Wednesdays are packed with meetings")
- Anti-patterns (e.g., "over-commits at work", "avoids health goals when stressed")
- Updated when the agent observes patterns or user gives explicit feedback

**Patterns** — Observed behavioral data
- Completion tendencies (which goal types stick, which get skipped)
- Time patterns (productive days, low-energy periods)
- Response to different coaching approaches
- Updated automatically as the agent notices trends in goal outcomes

This is a living document. The agent owns it. It grows and changes as the agent learns the user.

### 4. Goal Tracking Tool

Structured data store for goals and daily outcomes. SQLite — because this is relational data that needs querying (completion rates, date ranges, aggregations).

**`goals`** — What the user is working toward
- Yearly goals, monthly sub-goals, weekly focus areas
- Each has a title, description, and "why" (user-articulated reasoning)
- Status: active / completed / dropped
- Parent linkage (monthly goal → yearly goal)

**`goal_outcomes`** — What happened each day
- Date, goal reference, status (completed / partial / skipped / missed)
- Reason for success or failure
- One record per goal per day

**Operations:** `set_goal`, `record_outcome`, `get_goals`, `get_history`, `get_summary`

## Data Flow

### Daily Check-in
```
User sends message
  → Agent reads user profile markdown (soul, framework, patterns)
  → Agent reads active goals + recent outcomes from goal tool
  → Agent reasons about today's priority using profile + data
  → Agent responds with recommendation + reasoning
```

### Recording an Outcome
```
User says "done" or "skipped because..."
  → Agent calls record_outcome tool (SQLite)
  → Agent checks if outcome reveals new pattern
  → If yes: updates user profile markdown (patterns or framework section)
  → Agent acknowledges and optionally adjusts tomorrow's plan
```

### Learning a Value
```
User says "actually health is more important to me than career right now"
  → Agent updates user profile markdown (soul/motivation section)
  → Agent updates decision framework section
  → Future daily recommendations shift accordingly
```

## What We Build vs. What Claude Code Provides

| Concern | Who Handles It |
|---|---|
| Reasoning & coaching | Claude Code |
| Conversation memory | Claude Code sessions |
| Personality & philosophy | Agent CLAUDE.md (static file) |
| User values & decision rules | User profile (per-user markdown, read/written by agent) |
| Goal definitions & outcomes | Goal tracking tool (SQLite) |
| Message transport & auth | claude-code-telegram (existing) |

## Deployment

```env
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_BOT_USERNAME=overachiever_bot
APPROVED_DIRECTORY=/path/to/workdir
AGENT_CLAUDE_MD_PATH=config/agent.claude.md
LOAD_PROJECT_CLAUDE_MD=false
AGENTIC_MODE=true
```

Claude Code must be installed and authenticated (`claude login`) on the host machine. No API keys required.
