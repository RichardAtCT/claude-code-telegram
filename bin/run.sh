#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/Users/jarvis/jarvis-hub/repos/tools/claude-code-telegram"
cd "$APP_DIR"

# LaunchAgent has a tiny default PATH; make Homebrew/npm tools visible.
export PATH="/Users/jarvis/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/jarvis"

ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "fatal: missing .env at $ENV_FILE" >&2
  exit 78
fi

# Load .env so shell-level validation sees the same values as pydantic/dotenv.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Token lives in macOS Keychain, not on disk. Fetch only if not already in env.
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  TELEGRAM_BOT_TOKEN="$(/usr/bin/security find-generic-password \
    -s 'claude-code-telegram::TELEGRAM_BOT_TOKEN' \
    -a "$USER" -w 2>/dev/null || true)"
  export TELEGRAM_BOT_TOKEN
fi

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "fatal: TELEGRAM_BOT_TOKEN missing (not in .env, not in Keychain item 'claude-code-telegram::TELEGRAM_BOT_TOKEN')" >&2
  exit 78
fi
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  echo "fatal: venv python not executable at $APP_DIR/.venv/bin/python" >&2
  exit 78
fi

# Production avoids development overrides that stretch Claude timeout to 600s.
# Force this after sourcing .env because the local checkout may keep ENVIRONMENT=development.
export ENVIRONMENT="production"
export CLAUDE_TIMEOUT_SECONDS="${CLAUDE_TIMEOUT_SECONDS:-300}"
export TELEGRAM_PROGRESS_EDIT_INTERVAL="${TELEGRAM_PROGRESS_EDIT_INTERVAL:-6}"
export TELEGRAM_PROGRESS_MAX_FAILURES="${TELEGRAM_PROGRESS_MAX_FAILURES:-1}"
export TELEGRAM_API_RETRY_ATTEMPTS="${TELEGRAM_API_RETRY_ATTEMPTS:-2}"
export STREAM_DRAFT_INTERVAL="${STREAM_DRAFT_INTERVAL:-1.5}"

# Hard guardrail: Ferd uses Claude via OAuth/Claude Code, not paid Anthropic API.
unset ANTHROPIC_API_KEY

echo "starting claude-code-telegram env=$ENVIRONMENT timeout=${CLAUDE_TIMEOUT_SECONDS}s progress_interval=${TELEGRAM_PROGRESS_EDIT_INTERVAL}s"
exec "$APP_DIR/.venv/bin/python" -m src.main
