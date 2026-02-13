# Setup and Installation Guide

## Quick Start

### 1. Prerequisites

- **Python 3.10+** -- [Download here](https://www.python.org/downloads/)
- **Poetry** -- Modern Python dependency management
- **Telegram Bot Token** -- Get one from [@BotFather](https://t.me/botfather)
- **Claude Authentication** -- Choose one method below

### 2. Claude Authentication Setup

The bot supports two Claude integration modes. Choose the one that fits your needs:

#### Option A: SDK with CLI Authentication (Recommended)

Uses the Python SDK with your existing Claude CLI credentials.

```bash
# 1. Install Claude CLI (https://claude.ai/code)
# 2. Authenticate
claude auth login

# 3. Verify
claude auth status
# Should show: "You are authenticated"

# 4. Configure bot
USE_SDK=true
# Leave ANTHROPIC_API_KEY empty
```

#### Option B: SDK with Direct API Key

Uses the Python SDK with a direct API key, no CLI needed.

```bash
# 1. Get your API key from https://console.anthropic.com/
# 2. Configure bot
USE_SDK=true
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

#### Option C: CLI Subprocess Mode (Legacy)

Uses the Claude CLI as a subprocess. Only use for compatibility with older setups.

```bash
# 1. Install and authenticate Claude CLI
claude auth login

# 2. Configure bot
USE_SDK=false
```

### 3. Install the Bot

```bash
git clone https://github.com/RichardAtCT/claude-code-telegram.git
cd claude-code-telegram
make dev
```

### 4. Configure Environment

```bash
cp .env.example .env
nano .env
```

**Required Configuration:**

```bash
TELEGRAM_BOT_TOKEN=1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_BOT_USERNAME=your_bot_username
APPROVED_DIRECTORY=/path/to/your/projects
ALLOWED_USERS=123456789  # Your Telegram user ID
USE_SDK=true
```

### 5. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID number
3. Add this number to your `ALLOWED_USERS` setting

### 6. Run the Bot

```bash
make run-debug    # Recommended for first run
make run          # Production
```

### 7. Test the Bot

1. Find your bot on Telegram (search for your bot username)
2. Send `/start` to begin
3. Try asking Claude a question about your project
4. Use `/status` to check session info

## Agentic Platform Setup

The bot includes an event-driven platform for webhooks, scheduled jobs, and proactive notifications. All features are disabled by default.

### Webhook API Server

Enable to receive external webhooks (GitHub, etc.) and route them through Claude:

```bash
ENABLE_API_SERVER=true
API_SERVER_PORT=8080
```

#### GitHub Webhook Setup

1. Generate a webhook secret:
   ```bash
   openssl rand -hex 32
   ```

2. Add to your `.env`:
   ```bash
   GITHUB_WEBHOOK_SECRET=your-generated-secret
   NOTIFICATION_CHAT_IDS=123456789  # Your Telegram chat ID for notifications
   ```

3. In your GitHub repository, go to **Settings > Webhooks > Add webhook**:
   - **Payload URL**: `https://your-server:8080/webhooks/github`
   - **Content type**: `application/json`
   - **Secret**: The secret you generated
   - **Events**: Choose which events to receive (push, pull_request, issues, etc.)

4. Test with curl:
   ```bash
   curl -X POST http://localhost:8080/webhooks/github \
     -H "Content-Type: application/json" \
     -H "X-GitHub-Event: ping" \
     -H "X-GitHub-Delivery: test-123" \
     -H "X-Hub-Signature-256: sha256=$(echo -n '{"zen":"test"}' | openssl dgst -sha256 -hmac 'your-secret' | awk '{print $2}')" \
     -d '{"zen":"test"}'
   ```

#### Generic Webhook Setup

For non-GitHub providers, use Bearer token authentication:

```bash
WEBHOOK_API_SECRET=your-api-secret
```

Send webhooks with:
```bash
curl -X POST http://localhost:8080/webhooks/custom \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-secret" \
  -H "X-Event-Type: deployment" \
  -H "X-Delivery-ID: unique-id-123" \
  -d '{"status": "success", "environment": "production"}'
```

### Job Scheduler

Enable to run recurring Claude tasks on a cron schedule:

```bash
ENABLE_SCHEDULER=true
NOTIFICATION_CHAT_IDS=123456789  # Where to deliver results
```

Jobs are managed programmatically and persist in the SQLite database.

### Notification Recipients

Configure which Telegram chats receive proactive notifications from webhooks and scheduled jobs:

```bash
NOTIFICATION_CHAT_IDS=123456789,987654321
```

## Advanced Configuration

### Authentication Methods Comparison

| Feature | SDK + CLI Auth | SDK + API Key | CLI Subprocess |
|---------|----------------|---------------|----------------|
| Performance | Best | Best | Slower |
| CLI Required | Yes | No | Yes |
| Streaming | Yes | Yes | Limited |
| Error Handling | Best | Best | Basic |

### Security Configuration

#### Directory Isolation
```bash
# Set to a specific project directory, not your home directory
APPROVED_DIRECTORY=/Users/yourname/projects
```

#### User Access Control
```bash
# Whitelist specific users (recommended)
ALLOWED_USERS=123456789,987654321

# Optional: Token-based authentication
ENABLE_TOKEN_AUTH=true
AUTH_TOKEN_SECRET=your-secret-key-here
```

### Rate Limiting

```bash
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=60
RATE_LIMIT_BURST=20
CLAUDE_MAX_COST_PER_USER=10.0
```

### Development Setup

```bash
DEBUG=true
DEVELOPMENT_MODE=true
LOG_LEVEL=DEBUG
ENVIRONMENT=development
RATE_LIMIT_REQUESTS=100
CLAUDE_TIMEOUT_SECONDS=600
```

## Troubleshooting

### Bot doesn't respond
```bash
# Check your bot token
echo $TELEGRAM_BOT_TOKEN

# Verify user ID (message @userinfobot)
# Check bot logs
make run-debug
```

### Claude authentication issues

**SDK + CLI Auth:**
```bash
claude auth status
# If not authenticated: claude auth login
```

**SDK + API Key:**
```bash
# Verify key starts with: sk-ant-api03-
echo $ANTHROPIC_API_KEY
```

### Permission errors
```bash
# Check approved directory exists and is accessible
ls -la /path/to/your/projects
```

## Production Deployment

```bash
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
RATE_LIMIT_REQUESTS=5
CLAUDE_MAX_COST_PER_USER=5.0
SESSION_TIMEOUT_HOURS=12
ENABLE_TELEMETRY=true
```

## Getting Help

- **Documentation**: Check the main [README.md](../README.md)
- **Configuration**: See [configuration.md](configuration.md) for all options
- **Security**: See [SECURITY.md](../SECURITY.md) for security concerns
- **Issues**: [Open an issue](https://github.com/RichardAtCT/claude-code-telegram/issues)
