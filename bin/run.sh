#!/usr/bin/env bash
# Wrapper that loads the bot token from macOS Keychain and starts the bot.
# Used by both manual runs and the LaunchAgent.
set -euo pipefail

REPO_DIR="/Users/jarvis/jarvis-hub/repos/tools/claude-code-telegram"
cd "$REPO_DIR"

# Hard guard: never run with ANTHROPIC_API_KEY set (forces OAuth via claude CLI).
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY is set. This bot must run with OAuth via Claude CLI." >&2
  echo "Unset it before launching." >&2
  exit 2
fi

# Pull the Telegram bot token from Keychain.
TOKEN="$(security find-generic-password \
  -s "claude-code-telegram-bot" \
  -a "ferd" \
  -w 2>/dev/null || true)"

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: bot token not found in Keychain (service=claude-code-telegram-bot, account=ferd)." >&2
  echo "Run: security add-generic-password -U -s claude-code-telegram-bot -a ferd -w '<TOKEN>'" >&2
  exit 3
fi

export TELEGRAM_BOT_TOKEN="$TOKEN"

# Ensure ecosystem CLIs are on PATH: claude (homebrew), linearctl (~/.npm-global/bin),
# and other Jarvis tooling that skills may shell out to.
export PATH="/Users/jarvis/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

exec "$REPO_DIR/.venv/bin/python" -m src.main "$@"
