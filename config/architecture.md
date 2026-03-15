# Overachiever — Architecture

## What It Is

A personal prioritization coach delivered through Telegram, powered by Claude Code as the agent runtime.

The user chats with a Telegram bot. The bot forwards messages to a locally running Claude Code instance. Claude Code — guided by an agent personality file and equipped with goal tracking tools — coaches the user on prioritization, records outcomes, and learns their values over time.

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
┌─────────────┐
│  Telegram   │  User interface (phone/desktop)
└──────┬──────┘
       │
┌──────▼──────┐
│  Telegram   │  python-telegram-bot
│  Bot Layer  │  Auth, rate limiting, message routing
└──────┬──────┘
       │
┌──────▼──────┐
│ Claude Code │  claude-agent-sdk
│   (Agent)   │  Reasoning, coaching, tool calls
└──────┬──────┘
       │
┌──────▼──────┐
│   Tools     │  Goal tracking, user profile
│  (SQLite)   │  Structured data store
└─────────────┘
```

## Components

### 1. Agent Personality (`config/agent.claude.md`)

Static markdown file loaded as system prompt every session. Defines:
- Who the agent is and its coaching philosophy
- Communication style (concise, direct, Telegram-friendly)
- How to use the tools (always load profile + history before responding)
- General principles (fewer is better, user always succeeds, no guilt)

Does **not** contain user-specific decision rules — those live in the user profile.

### 2. Claude Code (Runtime)

The agent brain. Handles all reasoning, conversation, and coaching logic. We don't build any of this — Claude Code provides it.

What Claude Code gives us for free:
- Natural language understanding and generation
- Session resume (conversation continuity across messages)
- Native memory features
- Tool calling (reads/writes structured data via goal tools)

Configuration:
- `AGENT_CLAUDE_MD_PATH` — points to the personality file
- `LOAD_PROJECT_CLAUDE_MD=false` — prevents loading the repo's dev docs as agent context
- Session auto-resume via the existing bot integration

### 3. Goal Tracking Tool

Structured data store for goals and outcomes. Two tables in SQLite.

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

### 4. User Profile Store

The agent's learned understanding of each user. A living document that evolves through interactions.

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
- Updated automatically from goal outcome data

**Storage:** `user_values` table in SQLite — key-value pairs with categories, timestamps, and source attribution (user-stated vs. agent-inferred).

### 5. Telegram Bot Layer (Existing)

The existing `claude-code-telegram` bot, configured for agent mode:
- Authenticates users
- Forwards messages to Claude Code via the SDK
- Streams progress back (typing indicator while agent thinks)
- Sends final response
- Manages session continuity (auto-resume)

No changes to the bot's core architecture. The agent behavior is entirely defined by the CLAUDE.md personality file and the tools available to Claude Code.

## Data Flow

### Daily Check-in
```
User sends message
  → Bot forwards to Claude Code
    → Agent reads user profile (soul, framework, patterns)
    → Agent reads active goals + recent history
    → Agent reasons about today's priority
    → Agent responds with recommendation + reasoning
  → Bot sends response to Telegram
```

### Recording an Outcome
```
User says "done" or "skipped because..."
  → Agent calls record_outcome tool
  → Agent checks if outcome reveals new pattern
  → If yes: updates user profile (decision framework or patterns)
  → Agent acknowledges and optionally adjusts tomorrow's plan
```

### Learning a Value
```
User says "actually health is more important to me than career right now"
  → Agent updates user profile (soul/motivation section)
  → Agent updates decision framework ("health > career for current period")
  → Future daily recommendations shift accordingly
```

## What We Build vs. What Claude Code Provides

| Concern | Who Handles It |
|---|---|
| Reasoning & coaching | Claude Code |
| Conversation memory | Claude Code sessions |
| Personality & philosophy | Agent CLAUDE.md (static file) |
| Goal definitions & outcomes | Goal tracking tool (SQLite) |
| User values & learned rules | User profile store (SQLite) |
| Message transport | Telegram bot (existing) |
| Auth & rate limiting | Telegram bot (existing) |

## Deployment

Minimal config for a working deployment:

```env
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_BOT_USERNAME=overachiever_bot
APPROVED_DIRECTORY=/path/to/workdir
AGENT_CLAUDE_MD_PATH=config/agent.claude.md
LOAD_PROJECT_CLAUDE_MD=false
AGENTIC_MODE=true
```

Claude Code must be installed and authenticated (`claude login`) on the host machine. No API keys required.
