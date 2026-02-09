# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot providing remote access to Claude Code. Python 3.10+, built with Poetry, using `python-telegram-bot` for Telegram and `claude-agent-sdk` for Claude Code integration.

## Commands

```bash
make dev              # Install all deps (including dev)
make install          # Production deps only
make run              # Run the bot
make run-debug        # Run with debug logging
make test             # Run tests with coverage
make lint             # Black + isort + flake8 + mypy
make format           # Auto-format with black + isort

# Run a single test
poetry run pytest tests/unit/test_config.py -k test_name -v

# Type checking only
poetry run mypy src
```

## Architecture

### Dual Claude Integration (SDK primary, CLI fallback)

`ClaudeIntegration` (facade in `src/claude/facade.py`) wraps two backends:
- **`ClaudeSDKManager`** (`src/claude/sdk_integration.py`) — Primary. Uses `claude-agent-sdk` async `query()` with streaming. Session IDs come from Claude's `ResultMessage`, not generated locally.
- **`ClaudeProcessManager`** (`src/claude/integration.py`) — Legacy CLI subprocess fallback. Used when SDK fails with JSON decode or TaskGroup errors.

Sessions auto-resume: per user+directory, persisted in SQLite, temporary IDs (`temp_*`) are never sent to Claude for resume.

### Request Flow

```
Telegram message → Security middleware (group -3) → Auth middleware (group -2)
→ Rate limit (group -1) → Command/Message handler (group 10)
→ ClaudeIntegration.run_command() → SDK (with CLI fallback)
→ Response parsed → Stored in SQLite → Sent back to Telegram
```

### Dependency Injection

Bot handlers access dependencies via `context.bot_data`:
```python
context.bot_data["auth_manager"]
context.bot_data["claude_integration"]
context.bot_data["storage"]
context.bot_data["security_validator"]
```

### Key Directories

- `src/config/` — Pydantic Settings v2 config with env detection, feature flags (`features.py`)
- `src/bot/handlers/` — Telegram command, message, and callback handlers
- `src/bot/middleware/` — Auth, rate limit, security input validation
- `src/bot/features/` — Git integration, file handling, quick actions, session export
- `src/claude/` — Claude integration facade, SDK/CLI managers, session management, tool monitoring
- `src/storage/` — SQLite via aiosqlite, repository pattern (users, sessions, messages, tool_usage, audit_log, cost_tracking)
- `src/security/` — Multi-provider auth (whitelist + token), input validators, rate limiter, audit logging

### Security Model

5-layer defense: authentication (whitelist/token) → directory isolation (APPROVED_DIRECTORY + path traversal prevention) → input validation (blocks `..`, `;`, `&&`, `$()`, etc.) → rate limiting (token bucket) → audit logging.

`SecurityValidator` blocks access to secrets (`.env`, `.ssh`, `id_rsa`, `.pem`) and dangerous shell patterns.

### Configuration

Settings loaded from environment variables via Pydantic Settings. Required: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `APPROVED_DIRECTORY`. Key optional: `ALLOWED_USERS` (comma-separated Telegram IDs), `USE_SDK` (default true), `ANTHROPIC_API_KEY`, `ENABLE_MCP`, `MCP_CONFIG_PATH`.

Feature flags in `src/config/features.py` control: MCP, git integration, file uploads, quick actions, session export, image uploads, conversation mode.

## Code Style

- Black (88 char line length), isort (black profile), flake8, mypy strict
- pytest-asyncio with `asyncio_mode = "auto"`
- structlog for all logging (JSON in prod, console in dev)
- Type hints required on all functions (`disallow_untyped_defs = true`)

## Adding a New Bot Command

1. Add handler function in `src/bot/handlers/command.py`
2. Register in `src/bot/core.py` `_register_handlers()`
3. Add to `_set_bot_commands()` for Telegram's command menu
4. Add audit logging for the command
