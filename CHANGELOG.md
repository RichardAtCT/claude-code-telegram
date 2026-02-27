# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-02-27

### Added
- **Outbound image support**: Claude can now auto-detect and send images to Telegram, plus MCP `send_image_to_user` tool (#99)
- **CLAUDE.md loading**: Project-level CLAUDE.md files are loaded from the working directory and appended to the system prompt
- **Configurable reply quoting**: `REPLY_QUOTE` setting controls message quoting behavior, centralized via PTB Defaults (#111)
- **`max_budget_usd` cost cap**: Per-request cost limit passed to SDK via `ClaudeAgentOptions` (#95)
- **`Skill` and `AskUserQuestion`** added to default allowed tools (#85, #87)
- **Documentation site**: Docs index and README linking (#92)

### Changed
- **ToolMonitor replaced with SDK `can_use_tool` callback**: Security validation now uses the native SDK hook instead of a custom wrapper. `SecurityValidator` wired directly into `ClaudeAgentOptions.can_use_tool` (#62)
- **`DISABLE_TOOL_VALIDATION=true`** now passes `allowed_tools=None` to the SDK, fully bypassing tool name validation
- **Phase 5 cleanup**: `src/claude/` reduced from 2,774 to 1,316 lines (#96)
- **PTB `AIORateLimiter`** replaces manual sync-local `RetryAfter` retry (#86)
- **Project thread sync throttling**: Configurable `PROJECT_THREADS_SYNC_ACTION_INTERVAL_SECONDS` to avoid Telegram API rate limits (#84)
- **GitHub Actions upgraded** to latest versions for Node 24 compatibility (#67, #68)

### Fixed
- **Empty `CLAUDE_CLI_PATH` causing Permission denied**: Empty string coerced to `None` so SDK auto-discovers the CLI
- **Session resume failing** with generic exit code 1 (#94)
- **Progress message deletion crash**: Bot no longer stops mid-response when progress message deletion fails (#107)
- **General topic routing**: Messages in the General topic of forum supergroups now route correctly (#110)
- **Session ownership enforcement**: `load_session` and `get_or_create_session` now validate ownership (#83)
- **Bash boundary enforcement**: `cd` and chained commands checked against directory boundary (#69)
- **Handler robustness**: Potential `UnboundLocalError` resolved in message handlers (#66)
- **Claude Code internal paths**: `~/.claude/plans/` and `todos/` allowed in tool validation (#89)
- **`Topic_not_modified` treated as success** in topic sync instead of raising an error
- **Test fixes**: `is_forum=False` set on MagicMock chats to prevent test failures (#110)

### Previously Added
- **Agentic Mode** (default interaction model):
  - `MessageOrchestrator` routes messages to agentic (3 commands) or classic (13 commands) handlers based on `AGENTIC_MODE` setting
  - Natural language conversation with Claude -- no terminal commands needed
  - Automatic session persistence per user/project directory
- **Event-Driven Platform**:
  - `EventBus` -- async pub/sub system with typed event subscriptions (UserMessage, Webhook, Scheduled, AgentResponse)
  - `AgentHandler` -- bridges events to `ClaudeIntegration.run_command()` for webhook and scheduled event processing
  - `EventSecurityMiddleware` -- validates events before handler processing
- **Webhook API Server** (FastAPI):
  - `POST /webhooks/{provider}` endpoint for GitHub, Notion, and generic providers
  - GitHub HMAC-SHA256 signature verification
  - Generic Bearer token authentication
  - Atomic deduplication via `webhook_events` table
  - Health check at `GET /health`
- **Job Scheduler** (APScheduler):
  - Cron-based job scheduling with persistent storage in `scheduled_jobs` table
  - Jobs publish `ScheduledEvent` to event bus on trigger
  - Add, remove, and list jobs programmatically
- **Notification Service**:
  - Subscribes to `AgentResponseEvent` for Telegram delivery
  - Per-chat rate limiting (1 msg/sec) to respect Telegram limits
  - Message splitting at 4096 char boundary
  - Broadcast to configurable default chat IDs
- **Database Migration 3**: `scheduled_jobs` and `webhook_events` tables, WAL mode enabled
- **Automatic Session Resumption**: Sessions are now automatically resumed per user+directory
  - SDK integration passes `resume` parameter to Claude Code for real session continuity
  - Session IDs extracted from Claude's `ResultMessage` instead of generated locally
  - `/cd` looks up and resumes existing sessions for the target directory
  - Auto-resume from SQLite database survives bot restarts
  - Graceful fallback to fresh session when resume fails
  - `/new` and `/end` are the only ways to explicitly clear session context

### Recently Completed

#### Storage Layer Implementation (TODO-6) - 2025-06-06
- **SQLite Database with Complete Schema**:
  - 7 core tables: users, sessions, messages, tool_usage, audit_log, user_tokens, cost_tracking
  - Foreign key relationships and proper indexing for performance
  - Migration system with schema versioning and automatic upgrades
  - Connection pooling for efficient database resource management
- **Repository Pattern Data Access Layer**:
  - UserRepository, SessionRepository, MessageRepository, ToolUsageRepository
  - AuditLogRepository, CostTrackingRepository, AnalyticsRepository
- **Persistent Session Management**:
  - SQLiteSessionStorage replacing in-memory storage
  - Session persistence across bot restarts and deployments
- **Analytics and Reporting System**:
  - User dashboards with usage statistics and cost tracking
  - Admin dashboards with system-wide analytics

#### Telegram Bot Core (TODO-4) - 2025-06-06
- Complete Telegram bot with command routing, message parsing, inline keyboards
- Navigation commands: /cd, /ls, /pwd for directory management
- Session commands: /new, /continue, /status for Claude sessions
- File upload support, progress indicators, response formatting

#### Claude Code Integration (TODO-5) - 2025-06-06
- Async process execution with timeout handling
- Session state management and cross-conversation continuity
- Streaming JSON output parsing, tool call extraction
- Cost tracking and usage monitoring

#### Authentication & Security Framework (TODO-3) - 2025-06-05
- Multi-provider authentication (whitelist + token)
- Rate limiting with token bucket algorithm
- Input validation, path traversal prevention
- Security audit logging with risk assessment
- Bot middleware framework (auth, rate limit, security, burst protection)

## [0.1.0] - 2025-06-05

### Added

#### Project Foundation (TODO-1)
- Complete project structure with Poetry dependency management
- Exception hierarchy, structured logging, testing framework
- Code quality tools: Black, isort, flake8, mypy with strict settings

#### Configuration System (TODO-2)
- Pydantic Settings v2 with environment variable loading
- Environment-specific overrides (development, testing, production)
- Feature flags system for dynamic functionality control
- Comprehensive validation with cross-field dependencies

## Development Status

- **TODO-1**: Project Structure & Core Setup -- Complete
- **TODO-2**: Configuration Management -- Complete
- **TODO-3**: Authentication & Security Framework -- Complete
- **TODO-4**: Telegram Bot Core -- Complete
- **TODO-5**: Claude Code Integration -- Complete
- **TODO-6**: Storage & Persistence -- Complete
- **TODO-7**: Advanced Features -- Complete (agentic platform, webhooks, scheduler, notifications)
- **TODO-8**: Complete Testing Suite -- In progress
- **TODO-9**: Deployment & Documentation -- In progress
