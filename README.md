# Claude Code Telegram Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A Telegram bot that gives you remote access to [Claude Code](https://claude.ai/code). Chat naturally with Claude about your projects from anywhere -- no terminal commands needed.

## What is this?

This bot connects Telegram to Claude Code, providing a conversational AI interface for your codebase:

- **Chat naturally** -- ask Claude to analyze, edit, or explain your code in plain language
- **Maintain context** across conversations with automatic session persistence per project
- **Code on the go** from any device with Telegram
- **Receive proactive notifications** from webhooks, scheduled jobs, and CI/CD events
- **Stay secure** with built-in authentication, directory sandboxing, and audit logging

## Quick Start

### Demo

```
You: Can you help me add error handling to src/api.py?

Bot: I'll analyze src/api.py and add error handling...
     [Claude reads your code, suggests improvements, and can apply changes directly]

You: Looks good. Now run the tests to make sure nothing broke.

Bot: Running pytest...
     All 47 tests passed. The error handling changes are working correctly.
```

### 1. Prerequisites

- **Python 3.11+** -- [Download here](https://www.python.org/downloads/)
- **Claude Code CLI** -- [Install from here](https://claude.ai/code)
- **Telegram Bot Token** -- Get one from [@BotFather](https://t.me/botfather)

### 2. Install

Choose your preferred method:

#### Option A: Install from a release tag (Recommended)

```bash
# Using uv (recommended — installs in an isolated environment)
uv tool install git+https://github.com/RichardAtCT/claude-code-telegram@v2.0.0

# Or using pip
pip install git+https://github.com/RichardAtCT/claude-code-telegram@v2.0.0

# Track the latest stable release
pip install git+https://github.com/RichardAtCT/claude-code-telegram@latest
```

#### Optional Extras

```bash
# PostgreSQL support (alternative to SQLite)
pip install claude-code-telegram[postgres]

# Redis cache layer
pip install claude-code-telegram[cache]

# Voice message transcription (Mistral Voxtral / OpenAI Whisper)
pip install claude-code-telegram[voice]

# Multiple extras
pip install claude-code-telegram[postgres,cache,voice]
```

#### Option B: From source (for development)

```bash
git clone https://github.com/RichardAtCT/claude-code-telegram.git
cd claude-code-telegram
make dev  # requires Poetry
```

> **Note:** Always install from a tagged release (not `main`) for stability. See [Releases](https://github.com/RichardAtCT/claude-code-telegram/releases) for available versions.

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your settings:
```

**Minimum required:**
```bash
TELEGRAM_BOT_TOKEN=1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_BOT_USERNAME=my_claude_bot
APPROVED_DIRECTORY=/Users/yourname/projects
ALLOWED_USERS=123456789  # Your Telegram user ID
```

### 4. Run

```bash
make run          # Production
make run-debug    # With debug logging
```

Message your bot on Telegram to get started.

> **Detailed setup:** See [docs/setup.md](docs/setup.md) for Claude authentication options and troubleshooting.

## Modes

The bot supports two interaction modes:

### Agentic Mode (Default)

The default conversational mode. Just talk to Claude naturally -- no special commands required.

**Commands:** `/start`, `/new`, `/status`, `/verbose`, `/repo`, `/lang`, `/search`, `/team`, `/review`
If `ENABLE_PROJECT_THREADS=true`: `/sync_threads`

```
You: What files are in this project?
Bot: Working... (3s)
     📖 Read
     📂 LS
     💬 Let me describe the project structure
Bot: [Claude describes the project structure]

You: Add a retry decorator to the HTTP client
Bot: Working... (8s)
     📖 Read: http_client.py
     💬 I'll add a retry decorator with exponential backoff
     ✏️ Edit: http_client.py
     💻 Bash: poetry run pytest tests/ -v
Bot: [Claude shows the changes and test results]

You: /verbose 0
Bot: Verbosity set to 0 (quiet)
```

Use `/verbose 0|1|2` to control how much background activity is shown:

| Level | Shows |
|-------|-------|
| **0** (quiet) | Final response only (typing indicator stays active) |
| **1** (normal, default) | Tool names + reasoning snippets in real-time |
| **2** (detailed) | Tool names with inputs + longer reasoning text |

#### GitHub Workflow

Claude Code already knows how to use `gh` CLI and `git`. Authenticate on your server with `gh auth login`, then work with repos conversationally:

```
You: List my repos related to monitoring
Bot: [Claude runs gh repo list, shows results]

You: Clone the uptime one
Bot: [Claude runs gh repo clone, clones into workspace]

You: /repo
Bot: 📦 uptime-monitor/  ◀
     📁 other-project/

You: Show me the open issues
Bot: [Claude runs gh issue list]

You: Create a fix branch and push it
Bot: [Claude creates branch, commits, pushes]
```

Use `/repo` to list cloned repos in your workspace, or `/repo <name>` to switch directories (sessions auto-resume).

### Classic Mode

Set `AGENTIC_MODE=false` to enable the full 13-command terminal-like interface with directory navigation, inline keyboards, quick actions, git integration, and session export.

**Commands:** `/start`, `/help`, `/new`, `/continue`, `/end`, `/status`, `/cd`, `/ls`, `/pwd`, `/projects`, `/export`, `/actions`, `/git`  
If `ENABLE_PROJECT_THREADS=true`: `/sync_threads`

```
You: /cd my-web-app
Bot: Directory changed to my-web-app/

You: /ls
Bot: src/  tests/  package.json  README.md

You: /actions
Bot: [Run Tests] [Install Deps] [Format Code] [Run Linter]
```

## Commands Reference

### Agentic Mode Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot / show welcome message |
| `/new` | Start a new conversation session |
| `/status` | Show current session, usage, and cost stats |
| `/verbose 0\|1\|2` | Set output verbosity level |
| `/repo [name]` | List repos or switch to a specific project |
| `/lang [code]` | Set bot language (`en`, `zh`) |
| `/search <query>` | Search past conversations by keyword |
| `/team <action>` | Team collaboration (create, invite, list) |
| `/review [file]` | Request a code review of changes or a file |
| `/sync_threads` | Sync project topics (requires `ENABLE_PROJECT_THREADS=true`) |

### Classic Mode Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show available commands |
| `/new` | Start a new session |
| `/continue` | Resume a previous session |
| `/end` | End the current session |
| `/status` | Show session status |
| `/cd <dir>` | Change directory |
| `/ls [dir]` | List directory contents |
| `/pwd` | Show current directory |
| `/projects` | List available projects |
| `/export` | Export session (Markdown/HTML/JSON) |
| `/actions` | Show quick action buttons |
| `/git` | Git operations menu |

## Event-Driven Automation

Beyond direct chat, the bot can respond to external triggers:

- **Webhooks** -- Receive GitHub events (push, PR, issues) and route them through Claude for automated summaries or code review
- **Scheduler** -- Run recurring Claude tasks on a cron schedule (e.g., daily code health checks)
- **Notifications** -- Deliver agent responses to configured Telegram chats

Enable with `ENABLE_API_SERVER=true` and `ENABLE_SCHEDULER=true`. See [docs/setup.md](docs/setup.md) for configuration.

## Features

### Core

- Conversational agentic mode (default) with natural language interaction
- Classic terminal-like mode with 13 commands and inline keyboards
- Full Claude Code integration with SDK (primary) and CLI (fallback)
- Automatic session persistence per user/project directory
- Multi-layer authentication (whitelist + optional token-based)
- Rate limiting with token bucket algorithm
- Directory sandboxing with path traversal prevention
- File upload handling with archive extraction
- Image/screenshot upload with analysis
- Voice message transcription (Mistral Voxtral / OpenAI Whisper)
- Git integration with safe repository operations
- Quick actions system with context-aware buttons
- Session export in Markdown, HTML, and JSON formats
- Usage and cost tracking
- Audit logging and security event tracking
- Event bus for decoupled message routing
- Webhook API server (GitHub HMAC-SHA256, generic Bearer token auth)
- Job scheduler with cron expressions and persistent storage
- Notification service with per-chat rate limiting
- Tunable verbose output showing Claude's tool usage and reasoning in real-time
- Persistent typing indicator so users always know the bot is working
- 16 configurable tools with allowlist/disallowlist control (see [docs/tools.md](docs/tools.md))

### New in v2.0.0

#### Multi-language Support (i18n)

Use `/lang` to switch the bot interface between supported languages. Currently supports **English** and **Chinese**. All bot messages, prompts, and responses adapt to the selected language.

#### Plugin System

Extensible architecture with a hook-based plugin system. Third-party plugins can register lifecycle hooks to intercept and extend bot behavior -- message preprocessing, response postprocessing, custom command registration, and more.

#### Cache Layer

In-memory LRU cache with optional **Redis** backend for multi-instance deployments. Reduces redundant Claude API calls by caching frequent lookups, session metadata, and configuration. Install the `cache` extra to enable Redis support.

#### Graceful Degradation

Built-in resilience primitives to keep the bot responsive under pressure:

- **Circuit breaker** -- temporarily stops calling a failing upstream service and auto-recovers
- **Retry with backoff** -- retries transient failures with exponential backoff
- **Request queue** -- buffers bursts and processes them at a sustainable rate

#### Web Dashboard

Real-time monitoring dashboard served at `/dashboard` when the API server is enabled. View active sessions, request throughput, error rates, cost breakdown, and system health at a glance.

#### Code Review

Use `/review` to request a structured code review of staged changes or a specific file. When connected to a Git hosting provider, the bot can also **auto-review pull requests** triggered by webhooks.

#### Interactive Confirmation

Safety net for dangerous operations. When Claude is about to execute a destructive command (e.g., `rm -rf`, force push, database migration), the bot pauses and asks for explicit user approval via inline buttons before proceeding.

#### History Search

Use `/search <query>` to search past conversations by keyword. Results are ranked by relevance and grouped by session, making it easy to find previous solutions and discussions.

#### Team Collaboration

Use `/team` commands to manage shared projects across multiple users:

- `/team create <name>` -- create a shared project workspace
- `/team invite <user_id>` -- invite a team member
- `/team list` -- list your teams and shared projects

Team members share project context, conversation history, and can hand off sessions.

#### CI/CD Integration

Native webhook receivers for **GitHub**, **GitLab**, and **Bitbucket**. Push events, pull request updates, pipeline failures, and deployment statuses are routed through Claude for automated analysis, summaries, and actionable notifications.

#### Alert System

Configurable alerts for operational events:

- **Cost alerts** -- notify when spending exceeds configured thresholds
- **Error alerts** -- notify on repeated failures or circuit breaker trips
- **Security alerts** -- notify on authentication failures, suspicious patterns, or blocked operations

Alerts are delivered to configured Telegram chats via the notification service.

#### Prometheus Metrics

Expose metrics at the `/metrics` endpoint in Prometheus exposition format. Track request latency, token usage, error rates, active sessions, and queue depth. A sample **Grafana dashboard** JSON is included for quick setup.

#### PostgreSQL Support

Optional alternative to SQLite for production deployments. Install the `postgres` extra and set `DATABASE_URL=postgresql://...` to use PostgreSQL. Supports the same migration system and schema as SQLite.

#### Database Persistence

Token usage records, audit logs, and authentication tokens are now persisted in the database. Enables historical usage analysis, compliance auditing, and survives bot restarts without data loss.

#### Progress Tracking

Visual 6-stage progress feedback during long-running Claude operations:

1. Queued
2. Starting
3. Reading/Analyzing
4. Thinking
5. Writing/Executing
6. Complete

Each stage updates the Telegram message in-place so users always know exactly where their request stands.

## Configuration

### Required

```bash
TELEGRAM_BOT_TOKEN=...           # From @BotFather
TELEGRAM_BOT_USERNAME=...        # Your bot's username
APPROVED_DIRECTORY=...           # Base directory for project access
ALLOWED_USERS=123456789          # Comma-separated Telegram user IDs
```

### Common Options

```bash
# Claude
ANTHROPIC_API_KEY=sk-ant-...     # API key (optional if using CLI auth)
CLAUDE_MAX_COST_PER_USER=10.0    # Spending limit per user (USD)
CLAUDE_TIMEOUT_SECONDS=300       # Operation timeout

# Mode
AGENTIC_MODE=true                # Agentic (default) or classic mode
VERBOSE_LEVEL=1                  # 0=quiet, 1=normal (default), 2=detailed

# Rate Limiting
RATE_LIMIT_REQUESTS=10           # Requests per window
RATE_LIMIT_WINDOW=60             # Window in seconds

# Features (classic mode)
ENABLE_GIT_INTEGRATION=true
ENABLE_FILE_UPLOADS=true
ENABLE_QUICK_ACTIONS=true
```

### Agentic Platform

```bash
# Webhook API Server
ENABLE_API_SERVER=false          # Enable FastAPI webhook server
API_SERVER_PORT=8080             # Server port

# Webhook Authentication
GITHUB_WEBHOOK_SECRET=...        # GitHub HMAC-SHA256 secret
WEBHOOK_API_SECRET=...           # Bearer token for generic providers

# Scheduler
ENABLE_SCHEDULER=false           # Enable cron job scheduler

# Notifications
NOTIFICATION_CHAT_IDS=123,456    # Default chat IDs for proactive notifications
```

### v2.0.0 Features

```bash
# Internationalization
BOT_LANGUAGE=en                  # Default language (en, zh)

# Plugin System
ENABLE_PLUGINS=false             # Enable plugin system
PLUGINS_DIR=plugins              # Directory for plugin modules

# Cache Layer
ENABLE_CACHE=false               # Enable caching layer
CACHE_BACKEND=memory             # memory (LRU) or redis
CACHE_TTL_SECONDS=300            # Cache entry TTL
REDIS_URL=redis://localhost:6379 # Redis connection URL (when CACHE_BACKEND=redis)

# Graceful Degradation
CIRCUIT_BREAKER_THRESHOLD=5      # Failures before circuit opens
CIRCUIT_BREAKER_TIMEOUT=60       # Seconds before retry after circuit opens
REQUEST_QUEUE_SIZE=100           # Max queued requests
RETRY_MAX_ATTEMPTS=3             # Max retry attempts for transient failures

# Web Dashboard
ENABLE_DASHBOARD=false           # Enable /dashboard web UI

# Code Review
ENABLE_CODE_REVIEW=false         # Enable /review command and auto PR review

# Interactive Confirmation
ENABLE_CONFIRMATION=true         # Require approval for dangerous operations

# History Search
ENABLE_HISTORY_SEARCH=true       # Enable /search command

# Team Collaboration
ENABLE_TEAMS=false               # Enable /team commands

# CI/CD Integration
GITLAB_WEBHOOK_SECRET=...        # GitLab webhook secret
BITBUCKET_WEBHOOK_SECRET=...     # Bitbucket webhook secret

# Alert System
ENABLE_ALERTS=false              # Enable cost/error/security alerts
ALERT_COST_THRESHOLDS=5,10,25   # Cost alert thresholds in USD
ALERT_CHAT_IDS=123,456           # Chat IDs for alert delivery

# Prometheus Metrics
ENABLE_METRICS=false             # Enable /metrics endpoint

# PostgreSQL (alternative to SQLite)
DATABASE_URL=postgresql://user:pass@localhost:5432/botdb
```

### Project Threads Mode

```bash
# Enable strict topic routing by project
ENABLE_PROJECT_THREADS=true

# Mode: private (default) or group
PROJECT_THREADS_MODE=private

# YAML registry file (see config/projects.example.yaml)
PROJECTS_CONFIG_PATH=config/projects.yaml

# Required only when PROJECT_THREADS_MODE=group
PROJECT_THREADS_CHAT_ID=-1001234567890

# Minimum delay (seconds) between Telegram API calls during topic sync
# Set 0 to disable pacing
PROJECT_THREADS_SYNC_ACTION_INTERVAL_SECONDS=1.1
```

In strict mode, only `/start` and `/sync_threads` work outside mapped project topics.
In private mode, `/start` auto-syncs project topics for your private bot chat.
To use topics with your bot, enable them in BotFather:
`Bot Settings -> Threaded mode`.

> **Full reference:** See [docs/configuration.md](docs/configuration.md) and [`.env.example`](.env.example).

### Finding Your Telegram User ID

Message [@userinfobot](https://t.me/userinfobot) on Telegram -- it will reply with your user ID number.

## Troubleshooting

**Bot doesn't respond:**
- Check your `TELEGRAM_BOT_TOKEN` is correct
- Verify your user ID is in `ALLOWED_USERS`
- Ensure Claude Code CLI is installed and accessible
- Check bot logs with `make run-debug`

**Claude integration not working:**
- SDK mode (default): Check `claude auth status` or verify `ANTHROPIC_API_KEY`
- CLI mode: Verify `claude --version` and `claude auth status`
- Check `CLAUDE_ALLOWED_TOOLS` includes necessary tools (see [docs/tools.md](docs/tools.md) for the full reference)

**High usage costs:**
- Adjust `CLAUDE_MAX_COST_PER_USER` to set spending limits
- Monitor usage with `/status`
- Use shorter, more focused requests

## Security

This bot implements defense-in-depth security:

- **Access Control** -- Whitelist-based user authentication
- **Directory Isolation** -- Sandboxing to approved directories
- **Rate Limiting** -- Request and cost-based limits
- **Input Validation** -- Injection and path traversal protection
- **Webhook Authentication** -- GitHub HMAC-SHA256 and Bearer token verification
- **Audit Logging** -- Complete tracking of all user actions
- **Interactive Confirmation** -- Approval required for dangerous operations (v2.0.0)
- **Security Alerts** -- Real-time notifications on suspicious activity (v2.0.0)
- **Circuit Breaker** -- Automatic isolation of failing services (v2.0.0)

See [SECURITY.md](SECURITY.md) for details.

## Development

```bash
make dev           # Install all dependencies
make test          # Run tests with coverage
make lint          # Black + isort + flake8 + mypy
make format        # Auto-format code
make run-debug     # Run with debug logging
```

> **Full documentation:** See the [docs index](docs/README.md) for all guides and references.

### Version Management

The version is defined once in `pyproject.toml` and read at runtime via `importlib.metadata`. To cut a release:

```bash
make bump-patch    # 1.2.0 -> 1.2.1 (bug fixes)
make bump-minor    # 1.2.0 -> 1.3.0 (new features)
make bump-major    # 1.2.0 -> 2.0.0 (breaking changes)
```

Each command commits, tags, and pushes automatically, triggering CI tests and a GitHub Release with auto-generated notes.

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make changes with tests: `make test && make lint`
4. Submit a Pull Request

**Code standards:** Python 3.11+, Black formatting (88 chars), type hints required, pytest with >85% coverage.

## License

MIT License -- see [LICENSE](LICENSE).

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=RichardAtCT/claude-code-telegram&type=Date)](https://star-history.com/#RichardAtCT/claude-code-telegram&Date)

## Acknowledgments

- [Claude](https://claude.ai) by Anthropic
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
