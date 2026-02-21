# Setup and Installation Guide

## Quick Start

### 1. Prerequisites

- **Telegram Bot Token** -- Get one from [@BotFather](https://t.me/botfather)
- **Claude Authentication** -- Choose one method below
- **For source installs:** Python 3.11+ and Poetry
- **For Docker:** Docker and Docker Compose

### 2. Claude Authentication Setup

The bot uses the Claude Code Python SDK. Choose your authentication method:

#### Option A: CLI Authentication (Recommended)

Uses the SDK with your existing Claude CLI credentials.

```bash
# 1. Install Claude CLI (https://claude.ai/code)
# 2. Authenticate
claude auth login

# 3. Verify
claude auth status
# Should show: "You are authenticated"

# No ANTHROPIC_API_KEY needed — SDK uses CLI credentials
```

#### Option B: Direct API Key

Uses the SDK with a direct API key, no CLI auth needed.

```bash
# 1. Get your API key from https://console.anthropic.com/
# 2. Configure bot
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

### 3. Install the Bot

Choose your preferred installation method:

#### Option A: Docker (Recommended)

```bash
git clone --branch latest https://github.com/RichardAtCT/claude-code-telegram.git
cd claude-code-telegram
```

Or pull the pre-built image:
```bash
docker pull ghcr.io/richardatct/claude-code-telegram:latest
```

#### Option B: pip from a release tag

```bash
# Specific version
pip install git+https://github.com/RichardAtCT/claude-code-telegram@v1.2.0

# Latest stable
pip install git+https://github.com/RichardAtCT/claude-code-telegram@latest
```

#### Option C: From source (for development)

```bash
git clone https://github.com/RichardAtCT/claude-code-telegram.git
cd claude-code-telegram
make dev
```

> **Important:** Always install from a [tagged release](https://github.com/RichardAtCT/claude-code-telegram/releases), not `main`, for stability.

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
```

### 5. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID number
3. Add this number to your `ALLOWED_USERS` setting

### 6. Run the Bot

```bash
# Docker
make docker-run       # Start detached
make docker-logs      # Follow output

# From source
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

| Feature | SDK + CLI Auth | SDK + API Key |
|---------|----------------|---------------|
| Performance | Best | Best |
| CLI Required | Yes | No |
| Streaming | Yes | Yes |

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

## Running on a Remote Mac (SSH)

If you're running the bot on a remote Mac Mini (or any Mac accessed via SSH), Claude Code's OAuth tokens stored in the macOS keychain will be inaccessible because the keychain is locked in SSH sessions. This causes Claude invocations to fail silently or with authentication errors.

### Quick Start: `make run-remote`

The simplest fix is to unlock the keychain before starting the bot:

```bash
make run-remote
```

This prompts for your keychain password, then starts the bot in a detached tmux session that persists after SSH disconnect. Manage the session with:

```bash
make remote-attach   # View logs
make remote-stop     # Kill the bot
```

### Alternative: Unlock Keychain in Shell Profile

Add this to your `~/.zshrc` or `~/.bash_profile` so the keychain unlocks automatically on SSH login:

```bash
if [ -n "$SSH_CONNECTION" ] && [ -z "$KEYCHAIN_UNLOCKED" ]; then
  security unlock-keychain ~/Library/Keychains/login.keychain-db
  export KEYCHAIN_UNLOCKED=true
fi
```

### Extend Keychain Lock Timeout

By default the keychain re-locks after a short idle period. Set it to 8 hours:

```bash
security set-keychain-settings -t 28800 ~/Library/Keychains/login.keychain-db
```

### Alternative: Use an API Key Instead

Bypass the keychain entirely by using a direct API key (Option B in the authentication section above). Set `ANTHROPIC_API_KEY` in your `.env` and the keychain is never consulted.

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

## Docker Deployment

The bot ships with a `Dockerfile` and `docker-compose.yml` for containerized deployment.

### Running with Docker

```bash
make docker-build     # Build the image
make docker-run       # Start the bot (detached)
make docker-logs      # Follow logs
make docker-stop      # Stop the bot

# Rebuild after updating
make docker-build && make docker-run
```

The compose file reads your `.env` file automatically, persists the SQLite database in a named volume (`bot-data`), and bind-mounts your `APPROVED_DIRECTORY` into the container. The entrypoint automatically remaps the path so your existing `.env` works without changes:

```bash
# Same .env works for both source and Docker installs
APPROVED_DIRECTORY=/Users/yourname/projects
```

### Using a specific version

Pin to a release tag instead of `:latest`:

```yaml
services:
  bot:
    image: ghcr.io/richardatct/claude-code-telegram:1.2.0
```

### Building locally

```bash
make docker-build
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
