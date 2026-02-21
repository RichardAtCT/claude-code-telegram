#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# Docker entrypoint for Claude Code Telegram Bot
#
# 1. Remap APPROVED_DIRECTORY to the container mount path if needed
# 2. Auto-discover Claude CLI credentials
# ---------------------------------------------------------------------------

CONTAINER_PROJECT_DIR="/home/botuser/workspace/project"

# --- APPROVED_DIRECTORY remapping ---
# Users set APPROVED_DIRECTORY to their host path (e.g. /Users/me/projects).
# docker-compose mounts that host path at $CONTAINER_PROJECT_DIR.
# If the configured path doesn't exist in the container, remap it.
if [ -n "$APPROVED_DIRECTORY" ] && [ ! -d "$APPROVED_DIRECTORY" ]; then
    if [ -d "$CONTAINER_PROJECT_DIR" ]; then
        echo "Remapping APPROVED_DIRECTORY: $APPROVED_DIRECTORY -> $CONTAINER_PROJECT_DIR"
        export APPROVED_DIRECTORY="$CONTAINER_PROJECT_DIR"
    fi
elif [ -z "$APPROVED_DIRECTORY" ]; then
    export APPROVED_DIRECTORY="$CONTAINER_PROJECT_DIR"
fi

# --- Claude CLI credential discovery ---
# Lookup order (first match wins):
#   1. CLAUDE_CONFIG_DIR env var            (explicit override)
#   2. /host-claude-config                  (docker-compose bind mount)
#   3. ~/.claude                            (already in place)
# Entrypoint runs as root; credentials must land in botuser's home.
TARGET="/home/botuser/.claude"

resolve_config() {
    if [ -n "$CLAUDE_CONFIG_DIR" ] && [ -d "$CLAUDE_CONFIG_DIR" ]; then
        echo "$CLAUDE_CONFIG_DIR"
        return
    fi

    if [ -d "/host-claude-config" ] && [ "$(ls -A /host-claude-config 2>/dev/null)" ]; then
        echo "/host-claude-config"
        return
    fi

    if [ -d "$TARGET" ] && [ "$(ls -A "$TARGET" 2>/dev/null)" ]; then
        echo "$TARGET"
        return
    fi

    echo ""
}

SOURCE=$(resolve_config)

if [ -n "$SOURCE" ] && [ "$SOURCE" != "$TARGET" ]; then
    if [ -d "$TARGET" ] && [ ! -L "$TARGET" ] && [ -z "$(ls -A "$TARGET" 2>/dev/null)" ]; then
        rmdir "$TARGET" 2>/dev/null || true
    fi

    if [ ! -e "$TARGET" ]; then
        ln -s "$SOURCE" "$TARGET"
        echo "Linked Claude credentials: $SOURCE -> $TARGET"
    fi
elif [ -z "$SOURCE" ]; then
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        echo "WARNING: No Claude credentials found and ANTHROPIC_API_KEY is not set."
        echo "  Either set ANTHROPIC_API_KEY in .env, mount ~/.claude via docker-compose,"
        echo "  or set CLAUDE_CONFIG_DIR to the host credentials path."
    fi
fi

# Copy ~/.claude.json from the host-mounted config directory if available.
# The host's ~/.claude.json must be copied into ~/.claude/ first (the Makefile
# docker-run target handles this automatically).
if [ -f "/host-claude-config/.claude.json" ] && [ ! -e "/home/botuser/.claude.json" ]; then
    cp "/host-claude-config/.claude.json" "/home/botuser/.claude.json"
    chown botuser:botuser "/home/botuser/.claude.json"
    echo "Copied Claude config from /host-claude-config/.claude.json"
fi

# --- Fix volume permissions and drop to non-root ---
# Docker named volumes are root-owned on first creation.  Ensure botuser
# can write to the workspace (for the SQLite data dir, etc.).
# Only chown the volume root and data dir — NOT the bind-mounted project/.
mkdir -p /home/botuser/workspace/data
chown botuser:botuser /home/botuser/workspace /home/botuser/workspace/data

exec gosu botuser "$@"
