# Dynamic Command Menu & Plugin Manager

**Date:** 2026-02-28
**Status:** Approved

## Summary

Add a `/menu` command (wired to Telegram's persistent menu button) that dynamically discovers all Claude Code skills, commands, and plugins from the filesystem and presents them as a navigable inline keyboard. Includes full plugin management (browse, enable/disable, install/update).

## Requirements

1. **Dynamic discovery** — Scan `~/.claude/` on each menu open (no caching)
2. **Unified menu** — Bot commands + Claude Code skills/commands + custom skills in one place
3. **Natural categories** — Plugin names as groupings (not hardcoded taxonomy)
4. **Plugin management** — Browse, enable/disable, install new, update existing
5. **Persistent menu button** — Always-visible access via Telegram's menu button
6. **In-place navigation** — Edit existing message, don't spam new ones

## Architecture

### Navigation Model

```
/menu (top level)
├── 🤖 Bot (5)                  → /new, /status, /repo, /verbose, /stop
├── ⚡ superpowers (14)          → brainstorming, TDD, debugging, ...
├── 📝 commit-commands (3)       → /commit, /commit-push-pr, /clean_gone
├── 🔍 code-review (2)          → /code-review, /review-pr
├── 🚀 feature-dev (1)          → executes directly (single item)
├── 🎨 frontend-design (1)      → executes directly
├── 📋 claude-md-management (2)  → /revise-claude-md, /claude-md-improver
├── ⚙️ obsidian-cli (1)          → executes directly (custom skill)
├── ⚙️ defuddle (1)              → executes directly
├── ...more custom skills...
└── 📦 Plugin Store              → Search & install new plugins
```

Single-item plugins/skills execute directly on tap (no sub-menu).

### Callback Data Convention

```
Format: "menu:{action}:{argument}"

Navigation:
  "menu:cat:{plugin_name}"     → show plugin's skills/commands
  "menu:back"                  → return to top level
  "menu:back:{plugin_name}"    → return to plugin from detail view

Execution:
  "menu:run:{item_id}"         → execute a bot command or inject a skill

Plugin management:
  "menu:plug:{plugin_name}"    → show plugin detail (info, toggle, skills list)
  "menu:tog:{plugin_name}"     → toggle plugin enable/disable
  "menu:inst:{plugin_name}"    → install plugin from store
  "menu:upd:{plugin_name}"     → update plugin to latest version

Store:
  "menu:store"                 → show plugin store
  "menu:store:p{page}"         → paginate store results
```

Note: Telegram limits callback_data to 64 bytes. Plugin/skill names may need truncation + lookup table.

### Data Model

```python
@dataclass
class PaletteItem:
    id: str                    # unique ID, e.g. "superpowers:brainstorming"
    name: str                  # display name from SKILL.md frontmatter
    description: str           # from SKILL.md frontmatter
    action_type: ActionType    # DIRECT_COMMAND | INJECT_SKILL
    action_value: str          # "/status" or "/commit" or "brainstorming"
    icon: str                  # emoji (derived or default)
    source: str                # plugin name or "bot" or "custom"
    enabled: bool              # cross-referenced with settings.json

class ActionType(Enum):
    DIRECT_COMMAND = "direct"   # bot handles directly (e.g. /status)
    INJECT_SKILL = "inject"     # send as text to Claude session

@dataclass
class PluginInfo:
    name: str
    version: str
    enabled: bool
    items: list[PaletteItem]   # skills + commands in this plugin
    path: str                  # filesystem path
```

### Scanner Implementation

```python
class CommandPaletteScanner:
    CLAUDE_DIR = Path.home() / ".claude"

    def scan(self) -> tuple[list[PaletteItem], list[PluginInfo]]:
        items = []
        plugins = []

        # 1. Bot commands (hardcoded, always present)
        items.extend(self._get_bot_commands())

        # 2. Plugin skills: ~/.claude/plugins/cache/claude-plugins-official/*/skills/*/SKILL.md
        # 3. Plugin commands: ~/.claude/plugins/cache/claude-plugins-official/*/commands/*.md
        for plugin_dir in self._get_plugin_dirs():
            plugin_info = self._scan_plugin(plugin_dir)
            plugins.append(plugin_info)
            items.extend(plugin_info.items)

        # 4. Custom skills: ~/.claude/skills/*/SKILL.md
        for skill_dir in self._get_custom_skill_dirs():
            items.append(self._scan_custom_skill(skill_dir))

        # 5. Cross-reference with settings.json + blocklist.json
        self._apply_enabled_state(items, plugins)

        return items, plugins

    def _parse_skill_frontmatter(self, path: Path) -> dict:
        """Parse YAML frontmatter from SKILL.md or command .md file."""
        # Extract name, description from --- delimited YAML block
        ...
```

### Filesystem Paths Scanned

| Path | What | Category |
|------|------|----------|
| (hardcoded) | Bot commands: /new, /status, /repo, /verbose, /stop | bot |
| `~/.claude/plugins/cache/claude-plugins-official/{plugin}/{version}/skills/*/SKILL.md` | Official plugin skills | plugin name |
| `~/.claude/plugins/cache/claude-plugins-official/{plugin}/{version}/commands/*.md` | Official plugin commands | plugin name |
| `~/.claude/skills/*/SKILL.md` | Custom skills | custom |
| `~/.claude/settings.json` | Enabled plugins list | (config) |
| `~/.claude/plugins/installed_plugins.json` | Plugin versions & metadata | (config) |
| `~/.claude/plugins/blocklist.json` | Disabled plugins | (config) |

### Action Execution

| Action Type | Behavior |
|-------------|----------|
| `DIRECT_COMMAND` | Call the bot's own command handler function directly (e.g., `agentic_status()`) |
| `INJECT_SKILL` | Send skill name as user text to active Claude session via `ClaudeIntegration.run_command()` |

For skill injection, the bot constructs a message like `/commit` or `/feature-dev` and feeds it to Claude as if the user typed it. This leverages Claude's existing skill invocation mechanism.

### Plugin Management

**Enable/Disable:**
- Read `~/.claude/plugins/blocklist.json`
- Add/remove plugin name from blocklist array
- Write back to file
- Display confirmation with note: "Takes effect on next /new session"

**Install (Plugin Store):**
- Query available plugins (TBD: either scrape Claude Code plugin registry or maintain a known-plugins list)
- Run `claude plugins install {name}` via shell if CLI supports it
- Otherwise, manual download + write to `installed_plugins.json`
- Notify user of success/failure

**Update:**
- Compare installed version (from `installed_plugins.json`) with latest available
- Run update command or re-download

### Persistent Menu Button

On bot startup, call:
```python
await bot.set_chat_menu_button(
    menu_button=MenuButtonCommands()  # shows / command list
)
```

Register `/menu` in `get_bot_commands()` so it appears in Telegram's command autocomplete. The menu button in Telegram opens the command list where `/menu` is the first entry.

Alternative: Use `MenuButtonWebApp` if we ever migrate to a WebApp approach.

## New Files

| File | Purpose |
|------|---------|
| `src/bot/features/command_palette.py` | `CommandPaletteScanner`, `PaletteItem`, `PluginInfo`, `ActionType` |
| `src/bot/handlers/menu.py` | `/menu` command handler, callback handler for menu navigation, plugin management actions |

## Modified Files

| File | Change |
|------|--------|
| `src/bot/orchestrator.py` | Register `/menu` handler + menu callback handler in `_register_agentic_handlers()` |
| `src/bot/orchestrator.py` | Add `/menu` to `get_bot_commands()` |
| `src/bot/core.py` | Set persistent menu button on startup |

## Callback Data Size Constraint

Telegram limits `callback_data` to 64 bytes. Plugin/skill names can be long (e.g., "claude-md-management:claude-md-improver" = 40 chars + "menu:run:" prefix = 49 chars). Strategy:

- Use short numeric IDs in callback data: `"menu:run:7"`, `"menu:cat:3"`
- Maintain a per-message mapping dict `{short_id: full_item_id}` stored in `context.user_data`
- Mapping refreshed on each menu render

## Error Handling

- If `~/.claude/` doesn't exist: show only Bot commands, display note
- If a SKILL.md has invalid frontmatter: skip it, log warning
- If plugin toggle fails (permission error): show error inline
- If skill injection fails (no active session): prompt user to start a session first

## Testing Strategy

- Unit tests for `CommandPaletteScanner` with mock filesystem
- Unit tests for callback data routing
- Unit tests for frontmatter parsing (valid, invalid, missing)
- Integration test for menu navigation flow (mock Telegram API)
