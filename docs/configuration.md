# Configuration Guide

This document provides comprehensive information about configuring the Claude Code Telegram Bot.

## Overview

The bot uses a sophisticated configuration system built with Pydantic Settings v2 that provides:

- **Type Safety**: All configuration values are validated and type-checked
- **Environment Support**: Automatic environment-specific overrides
- **Feature Flags**: Dynamic enabling/disabling of functionality
- **Validation**: Cross-field validation and runtime checks
- **Documentation**: Self-documenting configuration with descriptions

## Configuration Sources

Configuration is loaded in this order (later sources override earlier ones):

1. **Default values** defined in the Settings class
2. **Environment variables**
3. **`.env` file** (if present)
4. **Environment-specific overrides** (development/testing/production)

## Environment Variables

### Required Settings

These settings MUST be provided for the bot to start:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_BOT_USERNAME=your_bot_name

# Security
APPROVED_DIRECTORY=/path/to/your/projects
```

### Optional Settings

#### User Access Control

```bash
# Comma-separated list of allowed Telegram user IDs
ALLOWED_USERS=123456789,987654321

# Enable token-based authentication (requires AUTH_TOKEN_SECRET)
ENABLE_TOKEN_AUTH=false
AUTH_TOKEN_SECRET=your-secret-key-here
```

#### Claude Configuration

```bash
# Maximum conversation turns before requiring new session
CLAUDE_MAX_TURNS=10

# Timeout for Claude operations in seconds
CLAUDE_TIMEOUT_SECONDS=300

# Maximum cost per user in USD
CLAUDE_MAX_COST_PER_USER=10.0
```

#### Rate Limiting

```bash
# Number of requests allowed per window
RATE_LIMIT_REQUESTS=10

# Rate limit window in seconds
RATE_LIMIT_WINDOW=60

# Burst capacity for rate limiting
RATE_LIMIT_BURST=20
```

#### Storage & Database

```bash
# Database URL (SQLite by default)
DATABASE_URL=sqlite:///data/bot.db

# Session management
SESSION_TIMEOUT_HOURS=24           # Session timeout in hours
MAX_SESSIONS_PER_USER=5            # Max concurrent sessions per user

# Database connection
DATABASE_CONNECTION_POOL_SIZE=5    # Connection pool size
DATABASE_TIMEOUT_SECONDS=30       # Database operation timeout

# Data retention
DATA_RETENTION_DAYS=90            # Days to keep old data
AUDIT_LOG_RETENTION_DAYS=365     # Days to keep audit logs
```

#### Feature Flags

```bash
# Enable Model Context Protocol
ENABLE_MCP=false
MCP_CONFIG_PATH=/path/to/mcp/config.json

# Enable Git integration
ENABLE_GIT_INTEGRATION=true

# Enable file upload handling
ENABLE_FILE_UPLOADS=true

# Enable quick action buttons
ENABLE_QUICK_ACTIONS=true
```

#### Monitoring & Logging

```bash
# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# Enable anonymous telemetry
ENABLE_TELEMETRY=false

# Sentry DSN for error tracking
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project
```

#### Development

```bash
# Enable debug mode
DEBUG=false

# Enable development features
DEVELOPMENT_MODE=false

# Environment override (development, testing, production)
ENVIRONMENT=development
```

#### Webhook (Optional)

```bash
# Webhook URL for bot (leave empty for polling mode)
WEBHOOK_URL=https://your-domain.com/webhook

# Webhook port
WEBHOOK_PORT=8443

# Webhook path
WEBHOOK_PATH=/webhook
```

## Environment-Specific Configuration

The bot automatically applies different settings based on the environment:

### Development Environment

Activated when `ENVIRONMENT=development` or when `DEBUG=true`:

- `debug = true`
- `development_mode = true`
- `log_level = "DEBUG"`
- `rate_limit_requests = 100` (more lenient)
- `claude_timeout_seconds = 600` (longer timeout)
- `enable_telemetry = false`

### Testing Environment

Activated when `ENVIRONMENT=testing`:

- `debug = true`
- `development_mode = true`
- `database_url = "sqlite:///:memory:"` (in-memory database)
- `approved_directory = "/tmp/test_projects"`
- `enable_telemetry = false`
- `claude_timeout_seconds = 30` (faster timeout)
- `rate_limit_requests = 1000` (no effective rate limiting)
- `session_timeout_hours = 1` (short timeout)

### Production Environment

Activated when `ENVIRONMENT=production`:

- `debug = false`
- `development_mode = false`
- `log_level = "INFO"`
- `enable_telemetry = true`
- `claude_max_cost_per_user = 5.0` (stricter cost limit)
- `rate_limit_requests = 5` (stricter rate limiting)
- `session_timeout_hours = 12` (shorter session timeout)

## Feature Flags

Feature flags allow you to enable or disable functionality dynamically:

```python
from src.config import load_config, FeatureFlags

config = load_config()
features = FeatureFlags(config)

if features.git_enabled:
    # Enable git commands
    pass

if features.mcp_enabled:
    # Enable Model Context Protocol
    pass
```

Available feature flags:

- `mcp_enabled`: Model Context Protocol support
- `git_enabled`: Git integration commands
- `file_uploads_enabled`: File upload handling
- `quick_actions_enabled`: Quick action buttons
- `telemetry_enabled`: Anonymous usage telemetry
- `token_auth_enabled`: Token-based authentication
- `webhook_enabled`: Webhook mode (vs polling)
- `development_features_enabled`: Development-only features

## Validation

The configuration system performs extensive validation:

### Path Validation

- `APPROVED_DIRECTORY` must exist and be accessible
- `MCP_CONFIG_PATH` must exist if MCP is enabled

### Cross-Field Validation

- `AUTH_TOKEN_SECRET` is required when `ENABLE_TOKEN_AUTH=true`
- `MCP_CONFIG_PATH` is required when `ENABLE_MCP=true`

### Value Validation

- `LOG_LEVEL` must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Numeric values must be positive where appropriate
- User IDs in `ALLOWED_USERS` must be valid integers

## Configuration Loading in Code

### Basic Usage

```python
from src.config import load_config

# Load with automatic environment detection
config = load_config()

# Access configuration
bot_token = config.telegram_token_str
max_cost = config.claude_max_cost_per_user
```

### Environment-Specific Loading

```python
from src.config import load_config

# Explicitly load production config
config = load_config(env="production")

# Check if running in production
if config.is_production:
    # Production-specific behavior
    pass
```

### Testing Configuration

```python
from src.config import create_test_config

# Create test config with overrides
config = create_test_config(
    claude_max_turns=5,
    debug=True
)
```

## Troubleshooting

### Common Issues

1. **"Approved directory does not exist"**
   - Ensure the path in `APPROVED_DIRECTORY` exists
   - Use absolute paths, not relative paths
   - Check file permissions

2. **"auth_token_secret required"**
   - Set `AUTH_TOKEN_SECRET` when using `ENABLE_TOKEN_AUTH=true`
   - Generate a secure secret: `openssl rand -hex 32`

3. **"MCP config file does not exist"**
   - Ensure `MCP_CONFIG_PATH` points to an existing file
   - Or disable MCP with `ENABLE_MCP=false`

### Debug Configuration

To see what configuration is loaded:

```bash
export TELEGRAM_BOT_TOKEN=test
export TELEGRAM_BOT_USERNAME=test  
export APPROVED_DIRECTORY=/tmp
make run-debug
```

This will show detailed logging of configuration loading and validation.

## Security Considerations

- **Never commit secrets** to version control
- **Use environment variables** for sensitive data
- **Rotate tokens regularly** if using token-based auth
- **Restrict `APPROVED_DIRECTORY`** to only necessary paths
- **Monitor logs** for configuration errors and security events

## Example .env File

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_BOT_USERNAME=my_claude_bot

# Security
APPROVED_DIRECTORY=/home/user/projects
ALLOWED_USERS=123456789,987654321

# Optional: Token Authentication
ENABLE_TOKEN_AUTH=false
AUTH_TOKEN_SECRET=

# Rate Limiting
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=60

# Claude Settings
CLAUDE_MAX_COST_PER_USER=10.0
CLAUDE_TIMEOUT_SECONDS=300

# Storage & Database
DATABASE_URL=sqlite:///data/bot.db
SESSION_TIMEOUT_HOURS=24
MAX_SESSIONS_PER_USER=5
DATA_RETENTION_DAYS=90

# Features
ENABLE_GIT_INTEGRATION=true
ENABLE_FILE_UPLOADS=true
ENABLE_QUICK_ACTIONS=true

# Development
DEBUG=false
LOG_LEVEL=INFO
```