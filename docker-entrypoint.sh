#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# Auto-discover Claude CLI credentials and make them available to the bot.
#
# Lookup order (first match wins):
#   1. CLAUDE_CONFIG_DIR env var            (explicit override)
#   2. /host-claude-config                  (docker-compose bind mount)
#   3. ~/.claude                            (already in place)
#
# When a source is found outside ~/.claude we symlink it so the SDK and CLI
# always find credentials at the canonical path.
# ---------------------------------------------------------------------------

TARGET="$HOME/.claude"

resolve_config() {
    # 1. Explicit override via env var
    if [ -n "$CLAUDE_CONFIG_DIR" ] && [ -d "$CLAUDE_CONFIG_DIR" ]; then
        echo "$CLAUDE_CONFIG_DIR"
        return
    fi

    # 2. Dedicated mount point (set up in docker-compose)
    if [ -d "/host-claude-config" ] && [ "$(ls -A /host-claude-config 2>/dev/null)" ]; then
        echo "/host-claude-config"
        return
    fi

    # 3. Already present at canonical path
    if [ -d "$TARGET" ] && [ "$(ls -A "$TARGET" 2>/dev/null)" ]; then
        echo "$TARGET"
        return
    fi

    echo ""
}

SOURCE=$(resolve_config)

if [ -n "$SOURCE" ] && [ "$SOURCE" != "$TARGET" ]; then
    # Remove empty placeholder that Docker may have created
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

exec "$@"
