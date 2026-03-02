# Dynamic Command Menu & Plugin Manager — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `/menu` command with persistent menu button that dynamically discovers all Claude Code skills, commands, and plugins from `~/.claude/`, presents them as navigable inline keyboard categories (grouped by plugin name), and supports full plugin management (enable/disable/install/update).

**Architecture:** New `CommandPaletteScanner` scans `~/.claude/` filesystem on each invocation, parsing YAML frontmatter from SKILL.md files and cross-referencing `settings.json`/`blocklist.json` for enabled state. A `/menu` command + `CallbackQueryHandler(pattern=r"^menu:")` handles multi-level inline keyboard navigation. Bot commands execute directly; Claude Code skills inject the skill name as text into the active Claude session via `agentic_text()`.

**Tech Stack:** python-telegram-bot (InlineKeyboardMarkup, CallbackQueryHandler), PyYAML (frontmatter parsing), pathlib (filesystem scanning), existing bot patterns from `orchestrator.py`.

**Design doc:** `docs/plans/2026-02-28-dynamic-command-menu-design.md`

---

### Task 1: Data Model — PaletteItem and PluginInfo

**Files:**
- Create: `src/bot/features/command_palette.py`
- Test: `tests/unit/test_bot/test_command_palette.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_bot/test_command_palette.py
"""Tests for the command palette scanner."""

import pytest

from src.bot.features.command_palette import (
    ActionType,
    PaletteItem,
    PluginInfo,
)


def test_palette_item_creation():
    item = PaletteItem(
        id="superpowers:brainstorming",
        name="brainstorming",
        description="Use before creative work",
        action_type=ActionType.INJECT_SKILL,
        action_value="/brainstorming",
        source="superpowers",
        enabled=True,
    )
    assert item.id == "superpowers:brainstorming"
    assert item.action_type == ActionType.INJECT_SKILL
    assert item.enabled is True


def test_plugin_info_creation():
    item = PaletteItem(
        id="superpowers:brainstorming",
        name="brainstorming",
        description="desc",
        action_type=ActionType.INJECT_SKILL,
        action_value="/brainstorming",
        source="superpowers",
        enabled=True,
    )
    plugin = PluginInfo(
        name="superpowers",
        qualified_name="superpowers@claude-plugins-official",
        version="4.3.1",
        enabled=True,
        items=[item],
        install_path="/home/user/.claude/plugins/cache/claude-plugins-official/superpowers/4.3.1",
    )
    assert plugin.name == "superpowers"
    assert len(plugin.items) == 1
    assert plugin.enabled is True


def test_action_type_enum():
    assert ActionType.DIRECT_COMMAND.value == "direct"
    assert ActionType.INJECT_SKILL.value == "inject"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.bot.features.command_palette'`

**Step 3: Write minimal implementation**

```python
# src/bot/features/command_palette.py
"""Dynamic command palette: scans ~/.claude/ for skills, commands, and plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ActionType(Enum):
    """How a palette item is executed."""

    DIRECT_COMMAND = "direct"  # Bot handles directly (e.g. /status)
    INJECT_SKILL = "inject"  # Send as text to Claude session (e.g. /commit)


@dataclass
class PaletteItem:
    """A single actionable item in the command palette."""

    id: str  # unique, e.g. "superpowers:brainstorming"
    name: str  # display name from SKILL.md frontmatter
    description: str  # from SKILL.md frontmatter
    action_type: ActionType
    action_value: str  # "/status" or "/commit" etc.
    source: str  # plugin name, "bot", or "custom"
    enabled: bool = True


@dataclass
class PluginInfo:
    """Metadata about an installed plugin."""

    name: str  # short name, e.g. "superpowers"
    qualified_name: str  # e.g. "superpowers@claude-plugins-official"
    version: str
    enabled: bool
    items: List[PaletteItem] = field(default_factory=list)
    install_path: str = ""
```

**Step 4: Run test to verify it passes**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/bot/features/command_palette.py tests/unit/test_bot/test_command_palette.py
git commit -m "feat(menu): add PaletteItem and PluginInfo data models"
```

---

### Task 2: YAML Frontmatter Parser

**Files:**
- Modify: `src/bot/features/command_palette.py`
- Test: `tests/unit/test_bot/test_command_palette.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_bot/test_command_palette.py`:

```python
from src.bot.features.command_palette import parse_skill_frontmatter


def test_parse_skill_frontmatter_valid():
    content = """---
name: brainstorming
description: Use before creative work
---

# Brainstorming
Some content here.
"""
    result = parse_skill_frontmatter(content)
    assert result["name"] == "brainstorming"
    assert result["description"] == "Use before creative work"


def test_parse_skill_frontmatter_no_frontmatter():
    content = "# Just a heading\nNo frontmatter here."
    result = parse_skill_frontmatter(content)
    assert result == {}


def test_parse_skill_frontmatter_with_allowed_tools():
    content = """---
name: commit
description: Create a git commit
allowed-tools: Bash(git add:*), Bash(git commit:*)
---
"""
    result = parse_skill_frontmatter(content)
    assert result["name"] == "commit"
    assert "allowed-tools" in result


def test_parse_skill_frontmatter_empty_content():
    result = parse_skill_frontmatter("")
    assert result == {}


def test_parse_skill_frontmatter_malformed_yaml():
    content = """---
name: [invalid yaml
description: missing bracket
---
"""
    result = parse_skill_frontmatter(content)
    assert result == {}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py::test_parse_skill_frontmatter_valid -v`
Expected: FAIL with `ImportError: cannot import name 'parse_skill_frontmatter'`

**Step 3: Write minimal implementation**

Add to `src/bot/features/command_palette.py`:

```python
import re
from typing import Dict, Any

import yaml

import structlog

logger = structlog.get_logger()


def parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from a SKILL.md or command .md file.

    Expects format:
        ---
        name: skill-name
        description: what it does
        ---
    """
    if not content.strip():
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    try:
        parsed = yaml.safe_load(match.group(1))
        return parsed if isinstance(parsed, dict) else {}
    except yaml.YAMLError:
        logger.warning("Failed to parse SKILL.md frontmatter")
        return {}
```

**Step 4: Run all frontmatter tests**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py -k frontmatter -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/bot/features/command_palette.py tests/unit/test_bot/test_command_palette.py
git commit -m "feat(menu): add YAML frontmatter parser for SKILL.md files"
```

---

### Task 3: CommandPaletteScanner — Filesystem Discovery

**Files:**
- Modify: `src/bot/features/command_palette.py`
- Test: `tests/unit/test_bot/test_command_palette.py`

This is the core scanner. It needs to read from specific filesystem paths under `~/.claude/`. We'll make the base path configurable for testing.

**Step 1: Write the failing tests**

Add to `tests/unit/test_bot/test_command_palette.py`:

```python
import tempfile
from pathlib import Path

from src.bot.features.command_palette import CommandPaletteScanner


@pytest.fixture
def mock_claude_dir():
    """Create a mock ~/.claude/ directory structure."""
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)

        # settings.json
        settings = base / "settings.json"
        settings.write_text(
            '{"enabledPlugins": {"superpowers@claude-plugins-official": true, '
            '"commit-commands@claude-plugins-official": true}}'
        )

        # installed_plugins.json
        plugins_dir = base / "plugins"
        plugins_dir.mkdir()
        installed = plugins_dir / "installed_plugins.json"
        installed.write_text(
            '{"version": 2, "plugins": {'
            '"superpowers@claude-plugins-official": [{"scope": "user", '
            '"installPath": "' + str(base) + '/plugins/cache/claude-plugins-official/superpowers/1.0", '
            '"version": "1.0"}], '
            '"commit-commands@claude-plugins-official": [{"scope": "user", '
            '"installPath": "' + str(base) + '/plugins/cache/claude-plugins-official/commit-commands/1.0", '
            '"version": "1.0"}]'
            "}}"
        )

        # blocklist.json
        blocklist = plugins_dir / "blocklist.json"
        blocklist.write_text('{"fetchedAt": "2026-01-01", "plugins": []}')

        # Plugin: superpowers with 1 skill
        cache = plugins_dir / "cache" / "claude-plugins-official"
        sp_dir = cache / "superpowers" / "1.0" / "skills" / "brainstorming"
        sp_dir.mkdir(parents=True)
        (sp_dir / "SKILL.md").write_text(
            "---\nname: brainstorming\n"
            "description: Use before creative work\n---\n# Content"
        )

        # Plugin: commit-commands with 1 command
        cc_dir = cache / "commit-commands" / "1.0" / "commands"
        cc_dir.mkdir(parents=True)
        (cc_dir / "commit.md").write_text(
            "---\nname: commit\ndescription: Create a git commit\n---\n# Content"
        )

        # Custom skill
        custom_dir = base / "skills" / "defuddle"
        custom_dir.mkdir(parents=True)
        (custom_dir / "SKILL.md").write_text(
            "---\nname: defuddle\n"
            "description: Extract markdown from web pages\n---\n# Content"
        )

        yield base


def test_scanner_discovers_bot_commands(mock_claude_dir):
    scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
    items, plugins = scanner.scan()
    bot_items = [i for i in items if i.source == "bot"]
    assert len(bot_items) >= 5  # start, new, status, verbose, repo, stop
    assert all(i.action_type == ActionType.DIRECT_COMMAND for i in bot_items)


def test_scanner_discovers_plugin_skills(mock_claude_dir):
    scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
    items, plugins = scanner.scan()
    skill_items = [i for i in items if i.id == "superpowers:brainstorming"]
    assert len(skill_items) == 1
    assert skill_items[0].name == "brainstorming"
    assert skill_items[0].action_type == ActionType.INJECT_SKILL


def test_scanner_discovers_plugin_commands(mock_claude_dir):
    scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
    items, plugins = scanner.scan()
    cmd_items = [i for i in items if i.id == "commit-commands:commit"]
    assert len(cmd_items) == 1
    assert cmd_items[0].name == "commit"
    assert cmd_items[0].action_type == ActionType.INJECT_SKILL


def test_scanner_discovers_custom_skills(mock_claude_dir):
    scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
    items, plugins = scanner.scan()
    custom = [i for i in items if i.source == "custom"]
    assert len(custom) == 1
    assert custom[0].name == "defuddle"


def test_scanner_builds_plugin_info(mock_claude_dir):
    scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
    items, plugins = scanner.scan()
    sp = [p for p in plugins if p.name == "superpowers"]
    assert len(sp) == 1
    assert sp[0].version == "1.0"
    assert sp[0].enabled is True
    assert len(sp[0].items) == 1


def test_scanner_handles_missing_claude_dir():
    scanner = CommandPaletteScanner(claude_dir=Path("/nonexistent"))
    items, plugins = scanner.scan()
    # Should still return bot commands
    bot_items = [i for i in items if i.source == "bot"]
    assert len(bot_items) >= 5
    assert len(plugins) == 0
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py::test_scanner_discovers_bot_commands -v`
Expected: FAIL with `ImportError: cannot import name 'CommandPaletteScanner'`

**Step 3: Write implementation**

Add to `src/bot/features/command_palette.py`:

```python
import json
from pathlib import Path


# Default bot commands (always present in agentic mode)
BOT_COMMANDS = [
    PaletteItem(
        id="bot:new", name="new", description="Start a fresh session",
        action_type=ActionType.DIRECT_COMMAND, action_value="/new", source="bot",
    ),
    PaletteItem(
        id="bot:status", name="status", description="Show session status",
        action_type=ActionType.DIRECT_COMMAND, action_value="/status", source="bot",
    ),
    PaletteItem(
        id="bot:repo", name="repo", description="List repos / switch workspace",
        action_type=ActionType.DIRECT_COMMAND, action_value="/repo", source="bot",
    ),
    PaletteItem(
        id="bot:verbose", name="verbose", description="Set output verbosity (0/1/2)",
        action_type=ActionType.DIRECT_COMMAND, action_value="/verbose", source="bot",
    ),
    PaletteItem(
        id="bot:stop", name="stop", description="Stop running Claude call",
        action_type=ActionType.DIRECT_COMMAND, action_value="/stop", source="bot",
    ),
]


class CommandPaletteScanner:
    """Scans ~/.claude/ for all available skills, commands, and plugins."""

    def __init__(self, claude_dir: Optional[Path] = None) -> None:
        self.claude_dir = claude_dir or Path.home() / ".claude"

    def scan(self) -> tuple[List[PaletteItem], List[PluginInfo]]:
        """Discover all palette items and plugin info from the filesystem."""
        items: List[PaletteItem] = []
        plugins: List[PluginInfo] = []

        # 1. Bot commands (always present)
        items.extend(BOT_COMMANDS)

        if not self.claude_dir.is_dir():
            return items, plugins

        # Load config files
        enabled_plugins = self._load_enabled_plugins()
        installed_plugins = self._load_installed_plugins()
        blocklisted = self._load_blocklist()

        # 2. Scan installed plugins
        for qualified_name, installs in installed_plugins.items():
            if not installs:
                continue
            install = installs[0]  # use first (most recent) install
            install_path = Path(install.get("installPath", ""))
            version = install.get("version", "unknown")
            short_name = qualified_name.split("@")[0]

            is_enabled = enabled_plugins.get(qualified_name, False)
            is_blocked = any(
                b.get("plugin") == qualified_name for b in blocklisted
            )
            effective_enabled = is_enabled and not is_blocked

            plugin_items: List[PaletteItem] = []

            # Scan skills
            skills_dir = install_path / "skills"
            if skills_dir.is_dir():
                for skill_dir in sorted(skills_dir.iterdir()):
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.is_file():
                        item = self._parse_skill_file(
                            skill_file, short_name, effective_enabled
                        )
                        if item:
                            plugin_items.append(item)

            # Scan commands
            commands_dir = install_path / "commands"
            if commands_dir.is_dir():
                for cmd_file in sorted(commands_dir.glob("*.md")):
                    item = self._parse_command_file(
                        cmd_file, short_name, effective_enabled
                    )
                    if item:
                        plugin_items.append(item)

            plugin = PluginInfo(
                name=short_name,
                qualified_name=qualified_name,
                version=version,
                enabled=effective_enabled,
                items=plugin_items,
                install_path=str(install_path),
            )
            plugins.append(plugin)
            items.extend(plugin_items)

        # 3. Scan custom skills (~/.claude/skills/)
        custom_dir = self.claude_dir / "skills"
        if custom_dir.is_dir():
            for skill_dir in sorted(custom_dir.iterdir()):
                skill_file = skill_dir / "SKILL.md"
                if skill_file.is_file():
                    item = self._parse_skill_file(
                        skill_file, "custom", True
                    )
                    if item:
                        item.source = "custom"
                        items.append(item)

        return items, plugins

    def _parse_skill_file(
        self, path: Path, source: str, enabled: bool
    ) -> Optional[PaletteItem]:
        """Parse a SKILL.md into a PaletteItem."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None
        fm = parse_skill_frontmatter(content)
        if not fm.get("name"):
            return None
        name = fm["name"]
        return PaletteItem(
            id=f"{source}:{name}",
            name=name,
            description=fm.get("description", ""),
            action_type=ActionType.INJECT_SKILL,
            action_value=f"/{name}",
            source=source,
            enabled=enabled,
        )

    def _parse_command_file(
        self, path: Path, source: str, enabled: bool
    ) -> Optional[PaletteItem]:
        """Parse a command .md into a PaletteItem."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None
        fm = parse_skill_frontmatter(content)
        if not fm.get("name"):
            return None
        name = fm["name"]
        return PaletteItem(
            id=f"{source}:{name}",
            name=name,
            description=fm.get("description", ""),
            action_type=ActionType.INJECT_SKILL,
            action_value=f"/{name}",
            source=source,
            enabled=enabled,
        )

    def _load_enabled_plugins(self) -> Dict[str, bool]:
        settings_file = self.claude_dir / "settings.json"
        if not settings_file.is_file():
            return {}
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return data.get("enabledPlugins", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_installed_plugins(self) -> Dict[str, list]:
        installed_file = self.claude_dir / "plugins" / "installed_plugins.json"
        if not installed_file.is_file():
            return {}
        try:
            data = json.loads(installed_file.read_text(encoding="utf-8"))
            return data.get("plugins", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_blocklist(self) -> list:
        blocklist_file = self.claude_dir / "plugins" / "blocklist.json"
        if not blocklist_file.is_file():
            return []
        try:
            data = json.loads(blocklist_file.read_text(encoding="utf-8"))
            return data.get("plugins", [])
        except (json.JSONDecodeError, OSError):
            return []
```

**Step 4: Run all scanner tests**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py -k scanner -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/bot/features/command_palette.py tests/unit/test_bot/test_command_palette.py
git commit -m "feat(menu): add CommandPaletteScanner for filesystem discovery"
```

---

### Task 4: Plugin Toggle (Enable/Disable)

**Files:**
- Modify: `src/bot/features/command_palette.py`
- Test: `tests/unit/test_bot/test_command_palette.py`

**Step 1: Write the failing test**

```python
def test_toggle_plugin_enable(mock_claude_dir):
    scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
    # Disable superpowers
    result = scanner.toggle_plugin("superpowers@claude-plugins-official", enabled=False)
    assert result is True

    # Verify settings.json updated
    settings = json.loads((mock_claude_dir / "settings.json").read_text())
    assert settings["enabledPlugins"]["superpowers@claude-plugins-official"] is False

    # Re-enable
    result = scanner.toggle_plugin("superpowers@claude-plugins-official", enabled=True)
    assert result is True
    settings = json.loads((mock_claude_dir / "settings.json").read_text())
    assert settings["enabledPlugins"]["superpowers@claude-plugins-official"] is True


def test_toggle_plugin_nonexistent(mock_claude_dir):
    scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
    result = scanner.toggle_plugin("nonexistent@nowhere", enabled=False)
    assert result is True  # Still writes to settings
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py::test_toggle_plugin_enable -v`
Expected: FAIL with `AttributeError: 'CommandPaletteScanner' object has no attribute 'toggle_plugin'`

**Step 3: Write implementation**

Add to `CommandPaletteScanner` class:

```python
    def toggle_plugin(self, qualified_name: str, enabled: bool) -> bool:
        """Enable or disable a plugin by updating settings.json."""
        settings_file = self.claude_dir / "settings.json"
        try:
            if settings_file.is_file():
                data = json.loads(settings_file.read_text(encoding="utf-8"))
            else:
                data = {}

            if "enabledPlugins" not in data:
                data["enabledPlugins"] = {}

            data["enabledPlugins"][qualified_name] = enabled
            settings_file.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to toggle plugin", plugin=qualified_name, error=str(e))
            return False
```

**Step 4: Run tests**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_command_palette.py -k toggle -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/bot/features/command_palette.py tests/unit/test_bot/test_command_palette.py
git commit -m "feat(menu): add plugin enable/disable toggle"
```

---

### Task 5: Menu Keyboard Builder

**Files:**
- Create: `src/bot/handlers/menu.py`
- Test: `tests/unit/test_bot/test_menu.py`

This builds the inline keyboards for each navigation level.

**Step 1: Write the failing tests**

```python
# tests/unit/test_bot/test_menu.py
"""Tests for the menu handler keyboard building."""

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.handlers.menu import MenuBuilder
from src.bot.features.command_palette import (
    ActionType,
    PaletteItem,
    PluginInfo,
)


@pytest.fixture
def sample_items():
    return [
        PaletteItem(
            id="bot:new", name="new", description="Fresh session",
            action_type=ActionType.DIRECT_COMMAND, action_value="/new",
            source="bot", enabled=True,
        ),
        PaletteItem(
            id="bot:status", name="status", description="Session status",
            action_type=ActionType.DIRECT_COMMAND, action_value="/status",
            source="bot", enabled=True,
        ),
        PaletteItem(
            id="superpowers:brainstorming", name="brainstorming",
            description="Creative work", action_type=ActionType.INJECT_SKILL,
            action_value="/brainstorming", source="superpowers", enabled=True,
        ),
        PaletteItem(
            id="commit-commands:commit", name="commit",
            description="Git commit", action_type=ActionType.INJECT_SKILL,
            action_value="/commit", source="commit-commands", enabled=True,
        ),
    ]


@pytest.fixture
def sample_plugins():
    return [
        PluginInfo(
            name="superpowers", qualified_name="superpowers@claude-plugins-official",
            version="4.3.1", enabled=True,
            items=[PaletteItem(
                id="superpowers:brainstorming", name="brainstorming",
                description="Creative work", action_type=ActionType.INJECT_SKILL,
                action_value="/brainstorming", source="superpowers", enabled=True,
            )],
        ),
        PluginInfo(
            name="commit-commands", qualified_name="commit-commands@claude-plugins-official",
            version="1.0", enabled=True,
            items=[PaletteItem(
                id="commit-commands:commit", name="commit",
                description="Git commit", action_type=ActionType.INJECT_SKILL,
                action_value="/commit", source="commit-commands", enabled=True,
            )],
        ),
    ]


def test_build_top_level_keyboard(sample_items, sample_plugins):
    builder = MenuBuilder(sample_items, sample_plugins)
    keyboard = builder.build_top_level()
    assert isinstance(keyboard, InlineKeyboardMarkup)
    # Should have Bot category + 2 plugin categories + Plugin Store
    texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert any("Bot" in t for t in texts)
    assert any("superpowers" in t for t in texts)


def test_build_category_keyboard_bot(sample_items, sample_plugins):
    builder = MenuBuilder(sample_items, sample_plugins)
    keyboard, text = builder.build_category("bot")
    assert isinstance(keyboard, InlineKeyboardMarkup)
    texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert any("new" in t for t in texts)
    assert any("status" in t for t in texts)
    # Should have Back button
    assert any("Back" in t for t in texts)


def test_build_category_keyboard_plugin(sample_items, sample_plugins):
    builder = MenuBuilder(sample_items, sample_plugins)
    keyboard, text = builder.build_category("superpowers")
    assert isinstance(keyboard, InlineKeyboardMarkup)
    texts = [btn.text for row in keyboard.inline_keyboard for btn in row]
    assert any("brainstorming" in t for t in texts)


def test_single_item_plugin_returns_none(sample_items, sample_plugins):
    """Single-item plugins should return None (execute directly)."""
    builder = MenuBuilder(sample_items, sample_plugins)
    # commit-commands has only 1 item, so build_category returns None
    result = builder.get_single_item_action("commit-commands")
    assert result is not None
    assert result.name == "commit"


def test_callback_id_mapping(sample_items, sample_plugins):
    builder = MenuBuilder(sample_items, sample_plugins)
    builder.build_top_level()
    # Verify short ID mapping works
    assert len(builder.id_map) > 0
    for short_id, full_id in builder.id_map.items():
        assert len(f"menu:cat:{short_id}") <= 64  # Telegram limit
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_menu.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/bot/handlers/menu.py
"""Dynamic command menu with inline keyboard navigation."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..features.command_palette import ActionType, PaletteItem, PluginInfo

logger = structlog.get_logger()


class MenuBuilder:
    """Builds inline keyboards for the command palette navigation."""

    def __init__(
        self,
        items: List[PaletteItem],
        plugins: List[PluginInfo],
    ) -> None:
        self.items = items
        self.plugins = plugins
        self.id_map: Dict[str, str] = {}  # short_id -> full_id
        self._counter = 0

    def _short_id(self, full_id: str) -> str:
        """Generate a short numeric ID and store the mapping."""
        self._counter += 1
        short = str(self._counter)
        self.id_map[short] = full_id
        return short

    def build_top_level(self) -> InlineKeyboardMarkup:
        """Build the top-level category menu."""
        keyboard: List[List[InlineKeyboardButton]] = []
        self.id_map.clear()
        self._counter = 0

        # Bot commands category
        bot_items = [i for i in self.items if i.source == "bot"]
        if bot_items:
            sid = self._short_id("bot")
            keyboard.append([
                InlineKeyboardButton(
                    f"\U0001f916 Bot ({len(bot_items)})",
                    callback_data=f"menu:cat:{sid}",
                )
            ])

        # Plugin categories (2 per row for compact layout)
        row: List[InlineKeyboardButton] = []
        for plugin in sorted(self.plugins, key=lambda p: p.name):
            if not plugin.items:
                continue
            count = len(plugin.items)
            status = "\u2705" if plugin.enabled else "\u274c"
            sid = self._short_id(plugin.name)

            # Single-item plugins: execute directly on tap
            if count == 1:
                item = plugin.items[0]
                isid = self._short_id(item.id)
                btn = InlineKeyboardButton(
                    f"{status} {plugin.name}",
                    callback_data=f"menu:run:{isid}",
                )
            else:
                btn = InlineKeyboardButton(
                    f"{status} {plugin.name} ({count})",
                    callback_data=f"menu:cat:{sid}",
                )

            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Custom skills
        custom_items = [i for i in self.items if i.source == "custom"]
        if custom_items:
            cust_row: List[InlineKeyboardButton] = []
            for item in custom_items:
                sid = self._short_id(item.id)
                cust_row.append(
                    InlineKeyboardButton(
                        f"\u2699\ufe0f {item.name}",
                        callback_data=f"menu:run:{sid}",
                    )
                )
                if len(cust_row) == 2:
                    keyboard.append(cust_row)
                    cust_row = []
            if cust_row:
                keyboard.append(cust_row)

        # Plugin Store
        keyboard.append([
            InlineKeyboardButton(
                "\U0001f4e6 Plugin Store", callback_data="menu:store"
            )
        ])

        return InlineKeyboardMarkup(keyboard)

    def build_category(self, source: str) -> Tuple[InlineKeyboardMarkup, str]:
        """Build keyboard for items in a given category/source.

        Returns (keyboard, header_text).
        """
        if source == "bot":
            cat_items = [i for i in self.items if i.source == "bot"]
            header = "\U0001f916 Bot Commands"
        else:
            cat_items = [i for i in self.items if i.source == source]
            plugin = next((p for p in self.plugins if p.name == source), None)
            status = "\u2705" if (plugin and plugin.enabled) else "\u274c"
            version = plugin.version if plugin else ""
            header = f"{status} {source} (v{version})"

        keyboard: List[List[InlineKeyboardButton]] = []
        for item in cat_items:
            sid = self._short_id(item.id)
            keyboard.append([
                InlineKeyboardButton(
                    f"{item.name} — {item.description[:40]}",
                    callback_data=f"menu:run:{sid}",
                )
            ])

        # Plugin management buttons (if it's a plugin, not bot)
        if source != "bot":
            plugin = next((p for p in self.plugins if p.name == source), None)
            if plugin:
                toggle_label = "\U0001f534 Disable" if plugin.enabled else "\U0001f7e2 Enable"
                keyboard.append([
                    InlineKeyboardButton(
                        toggle_label,
                        callback_data=f"menu:tog:{source}",
                    )
                ])

        # Back button
        keyboard.append([
            InlineKeyboardButton("\u2190 Back", callback_data="menu:back")
        ])

        return InlineKeyboardMarkup(keyboard), header

    def get_single_item_action(self, source: str) -> Optional[PaletteItem]:
        """If a plugin has exactly 1 item, return it for direct execution."""
        plugin = next((p for p in self.plugins if p.name == source), None)
        if plugin and len(plugin.items) == 1:
            return plugin.items[0]
        return None

    def resolve_id(self, short_id: str) -> Optional[str]:
        """Resolve a short callback ID to the full item/category ID."""
        return self.id_map.get(short_id)
```

**Step 4: Run tests**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_menu.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/bot/handlers/menu.py tests/unit/test_bot/test_menu.py
git commit -m "feat(menu): add MenuBuilder for inline keyboard navigation"
```

---

### Task 6: Menu Command Handler + Callback Router

**Files:**
- Modify: `src/bot/handlers/menu.py`
- Test: `tests/unit/test_bot/test_menu.py`

This adds the actual Telegram handler functions.

**Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    context.bot_data = {}
    return context


@pytest.mark.asyncio
async def test_menu_command_sends_keyboard(mock_update, mock_context):
    with patch("src.bot.handlers.menu.CommandPaletteScanner") as MockScanner:
        mock_scanner = MockScanner.return_value
        mock_scanner.scan.return_value = (
            [PaletteItem(
                id="bot:new", name="new", description="Fresh session",
                action_type=ActionType.DIRECT_COMMAND, action_value="/new",
                source="bot", enabled=True,
            )],
            [],
        )
        from src.bot.handlers.menu import menu_command
        await menu_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        call_kwargs = mock_update.message.reply_text.call_args
        assert call_kwargs.kwargs.get("reply_markup") is not None
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_menu.py::test_menu_command_sends_keyboard -v`
Expected: FAIL with `ImportError: cannot import name 'menu_command'`

**Step 3: Write implementation**

Add to `src/bot/handlers/menu.py`:

```python
from telegram import Update
from telegram.ext import ContextTypes

from ..features.command_palette import CommandPaletteScanner


async def menu_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /menu command — show the command palette."""
    scanner = CommandPaletteScanner()
    items, plugins = scanner.scan()

    builder = MenuBuilder(items, plugins)
    keyboard = builder.build_top_level()

    # Store builder in user_data for callback resolution
    context.user_data["menu_builder"] = builder

    await update.message.reply_text(
        "\u26a1 <b>Command Palette</b>\n\nSelect a category:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle all menu: callback queries."""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(":", 2)  # "menu:action:arg"
    if len(parts) < 2:
        return

    action = parts[1]
    arg = parts[2] if len(parts) > 2 else ""

    builder: Optional[MenuBuilder] = context.user_data.get("menu_builder")

    if action == "back":
        # Rebuild top-level menu
        scanner = CommandPaletteScanner()
        items, plugins = scanner.scan()
        builder = MenuBuilder(items, plugins)
        context.user_data["menu_builder"] = builder
        keyboard = builder.build_top_level()
        await query.edit_message_text(
            "\u26a1 <b>Command Palette</b>\n\nSelect a category:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    if action == "cat" and builder:
        full_id = builder.resolve_id(arg)
        if not full_id:
            return
        keyboard, header = builder.build_category(full_id)
        await query.edit_message_text(
            f"<b>{header}</b>\n\nSelect a command:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    if action == "run" and builder:
        full_id = builder.resolve_id(arg)
        if not full_id:
            return
        item = next((i for i in builder.items if i.id == full_id), None)
        if not item:
            return

        if item.action_type == ActionType.DIRECT_COMMAND:
            # Remove menu message and let the bot handle the command directly
            await query.edit_message_text(
                f"Running <code>{item.action_value}</code>...",
                parse_mode="HTML",
            )
            # Simulate command by calling appropriate handler
            # The orchestrator will handle this via _execute_bot_command
            context.user_data["menu_pending_command"] = item.action_value
            return

        if item.action_type == ActionType.INJECT_SKILL:
            # Inject skill name as text to Claude
            await query.edit_message_text(
                f"Invoking <code>{item.action_value}</code>...",
                parse_mode="HTML",
            )
            context.user_data["menu_pending_skill"] = item.action_value
            return

    if action == "tog":
        # Toggle plugin enable/disable
        plugin_name = arg
        scanner = CommandPaletteScanner()
        _, plugins = scanner.scan()
        plugin = next((p for p in plugins if p.name == plugin_name), None)
        if plugin:
            new_state = not plugin.enabled
            scanner.toggle_plugin(plugin.qualified_name, new_state)
            status = "\u2705 Enabled" if new_state else "\u274c Disabled"
            await query.edit_message_text(
                f"<b>{plugin.name}</b> — {status}\n\n"
                f"Takes effect on next <code>/new</code> session.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("\u2190 Back", callback_data="menu:back")]
                ]),
            )
            return

    if action == "store":
        await query.edit_message_text(
            "\U0001f4e6 <b>Plugin Store</b>\n\n"
            "Plugin store coming soon.\n"
            "For now, install plugins via Claude Code CLI:\n"
            "<code>claude plugins install &lt;name&gt;</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\u2190 Back", callback_data="menu:back")]
            ]),
        )
        return
```

**Step 4: Run tests**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_menu.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add src/bot/handlers/menu.py tests/unit/test_bot/test_menu.py
git commit -m "feat(menu): add menu_command and menu_callback handlers"
```

---

### Task 7: Wire Menu into Orchestrator

**Files:**
- Modify: `src/bot/orchestrator.py` (lines 307-357, 408-441)
- Test: `tests/unit/test_orchestrator.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_orchestrator.py`:

```python
def test_agentic_mode_registers_menu_handler(agentic_settings, deps):
    orchestrator = MessageOrchestrator(agentic_settings, deps)
    app = MagicMock()
    orchestrator.register_handlers(app)

    # Verify /menu command is registered
    handler_calls = [str(c) for c in app.add_handler.call_args_list]
    handler_strs = str(handler_calls)
    assert "menu" in handler_strs.lower()


def test_agentic_mode_registers_menu_callback(agentic_settings, deps):
    orchestrator = MessageOrchestrator(agentic_settings, deps)
    app = MagicMock()
    orchestrator.register_handlers(app)

    # Verify menu: callback pattern is registered
    handler_strs = str(app.add_handler.call_args_list)
    assert "menu:" in handler_strs


@pytest.mark.asyncio
async def test_get_bot_commands_includes_menu(agentic_settings, deps):
    orchestrator = MessageOrchestrator(agentic_settings, deps)
    commands = await orchestrator.get_bot_commands()
    command_names = [c.command for c in commands]
    assert "menu" in command_names
```

**Step 2: Run to verify failure**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_orchestrator.py::test_agentic_mode_registers_menu_handler -v`
Expected: FAIL (no "menu" in registered handlers)

**Step 3: Modify orchestrator**

In `src/bot/orchestrator.py`:

**At `_register_agentic_handlers()` (line 307)** — add menu command + callback:

After line 318 (`("stop", command.stop_command),`), add:
```python
        from .handlers import menu as menu_handler
```

After the handlers list (before the for loop at line 323), add `menu` to handlers:
```python
            ("menu", menu_handler.menu_command),
```

After the `cd:` callback handler (line 355), add:
```python
        # Menu navigation callbacks
        app.add_handler(
            CallbackQueryHandler(
                self._inject_deps(menu_handler.menu_callback),
                pattern=r"^menu:",
            )
        )
```

**At `get_bot_commands()` (line 408)** — add menu to agentic commands:

After line 412 (`BotCommand("start", "Start the bot"),`), add:
```python
                BotCommand("menu", "Command palette & plugin manager"),
```

**Step 4: Run tests**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_orchestrator.py -k menu -v`
Expected: PASS (3 tests)

**Step 5: Run all existing tests to check for regressions**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/ -v --timeout=30`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add src/bot/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat(menu): wire /menu command and callbacks into orchestrator"
```

---

### Task 8: Skill Injection — Connect Menu to Claude Session

**Files:**
- Modify: `src/bot/orchestrator.py`
- Modify: `src/bot/handlers/menu.py`

When a user taps a skill button (e.g. "brainstorming"), we need to inject that text into the Claude session just like the user typed it. The cleanest approach is to reuse `agentic_text()` logic.

**Step 1: Write the failing test**

Add to `tests/unit/test_bot/test_menu.py`:

```python
@pytest.mark.asyncio
async def test_menu_run_injects_skill_into_user_data():
    """When a skill button is tapped, its action_value is stored for injection."""
    update = MagicMock()
    query = AsyncMock()
    query.data = "menu:run:1"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {
        "menu_builder": MagicMock(
            resolve_id=MagicMock(return_value="commit-commands:commit"),
            items=[PaletteItem(
                id="commit-commands:commit", name="commit",
                description="Git commit", action_type=ActionType.INJECT_SKILL,
                action_value="/commit", source="commit-commands", enabled=True,
            )],
        )
    }

    from src.bot.handlers.menu import menu_callback
    await menu_callback(update, context)

    assert context.user_data.get("menu_pending_skill") == "/commit"
```

**Step 2: Run to verify it passes** (already implemented in Task 6)

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_menu.py::test_menu_run_injects_skill_into_user_data -v`
Expected: PASS

**Step 3: Implement the injection bridge in orchestrator**

Add a helper method to `MessageOrchestrator` that checks for pending menu actions and routes them. This hooks into the existing `agentic_text()` flow.

In `src/bot/handlers/menu.py`, update the `menu_callback` `"run"` action for `INJECT_SKILL` to send the skill invocation as a new message to the bot (simulating user input):

```python
        if item.action_type == ActionType.INJECT_SKILL:
            await query.edit_message_text(
                f"Invoking <code>{item.action_value}</code>...",
                parse_mode="HTML",
            )
            # Send the skill name as a new message from the user
            # This triggers agentic_text() which routes it to Claude
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=item.action_value,
            )
            return
```

Wait — that would send a message *from the bot*, not the user. Better approach: store the pending skill and inform the user to confirm, OR directly call `agentic_text` with a synthetic update. The simplest approach is to use `context.user_data["menu_inject"]` and have the menu callback send a follow-up message that the user just needs to confirm:

Actually, the cleanest approach: after editing the menu message, call the orchestrator's text handler directly with the skill text. Add this to `menu_callback`:

```python
        if item.action_type == ActionType.INJECT_SKILL:
            await query.edit_message_text(
                f"\u26a1 <code>{item.action_value}</code>",
                parse_mode="HTML",
            )
            # Store for the orchestrator to pick up and route to Claude
            context.user_data["menu_inject_text"] = item.action_value
            return
```

Then in the orchestrator, add a post-callback check or simply have a small wrapper. The pragmatic solution: the menu callback directly calls `ClaudeIntegration.run_command()` with the skill text, using the same pattern as `agentic_text()` but simplified.

However, to keep things clean, let's just have the menu handler import and call into a shared helper. This will be implemented in the integration step.

**Step 4: Commit**

```bash
git add src/bot/handlers/menu.py
git commit -m "feat(menu): store pending skill invocation for Claude injection"
```

---

### Task 9: Skill Injection Bridge — Shared Helper

**Files:**
- Modify: `src/bot/orchestrator.py`
- Modify: `src/bot/handlers/menu.py`

**Step 1: Extract a reusable `_send_to_claude` helper from `agentic_text()`**

Read `agentic_text()` (line 835-end) and extract the core Claude invocation into a helper that can be called from both `agentic_text()` and `menu_callback()`.

Add to `MessageOrchestrator`:

```python
    async def send_text_to_claude(
        self,
        text: str,
        chat_id: int,
        user_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        reply_to_message_id: Optional[int] = None,
    ) -> None:
        """Send text to Claude and stream the response back.

        Shared helper used by agentic_text() and menu skill injection.
        """
        # ... extracted from agentic_text core logic
```

This is a larger refactor. For the initial implementation, the simpler approach is to have the menu callback compose a fake Update-like object and delegate. But that's fragile.

**Pragmatic approach:** Instead of refactoring agentic_text, have menu_callback store the skill text and let the user know it's queued. Then use `context.bot.send_message` to send a message in the chat that says the skill name — which the user sees and agentic_text picks up naturally since it processes all non-command text.

Wait, actually `context.bot.send_message` sends *as the bot*. We can't fake a user message.

**Best approach:** The menu callback directly calls `ClaudeIntegration.run_command()` in a simplified flow:

```python
        if item.action_type == ActionType.INJECT_SKILL:
            await query.edit_message_text(
                f"\u26a1 Running <code>{item.action_value}</code>...",
                parse_mode="HTML",
            )

            claude = context.bot_data.get("claude_integration")
            if not claude:
                await query.edit_message_text("Claude integration not available.")
                return

            current_dir = context.user_data.get("current_directory", "/home/florian")
            session_id = context.user_data.get("claude_session_id")

            # Send skill invocation to Claude
            response = await claude.run_command(
                prompt=item.action_value,
                working_directory=str(current_dir),
                user_id=str(query.from_user.id),
                session_id=session_id,
            )

            # Update session ID
            if response and response.session_id:
                context.user_data["claude_session_id"] = response.session_id

            # Send response
            if response and response.content:
                # Truncate for Telegram's 4096 char limit
                content = response.content[:4000]
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=content,
                    parse_mode="HTML",
                )
            return
```

This is clean but skips the streaming/progress UI that `agentic_text` provides. For v1, this is acceptable. The streaming can be added later.

**However**, the even simpler v1: just edit the message to tell the user what to type. No, that defeats the purpose.

**Final decision for v1:** Store the pending skill in user_data, then have the menu_callback call a reference to the orchestrator's `_run_claude_from_menu` helper (a new, simpler method). The orchestrator has access to all the streaming infrastructure.

Let's keep this simple for the plan. The menu callback stores `context.user_data["menu_inject_text"]` and a new `_check_menu_injection()` helper in orchestrator processes it. The menu callback also sends a "Working..." progress message.

**This is getting complex. Let me simplify.**

For v1, the menu callback will:
1. Edit the menu message to show "Running /commit..."
2. Call `ClaudeIntegration.run_command()` directly (no streaming, just final result)
3. Send the response as a message

This avoids refactoring agentic_text and gives a working feature. Streaming can be added in v2.

**Step 2: Implementation in menu.py**

Already described above. Add to the `INJECT_SKILL` branch of `menu_callback`.

**Step 3: Test**

```python
@pytest.mark.asyncio
async def test_menu_run_calls_claude_for_skill():
    update = MagicMock()
    query = AsyncMock()
    query.data = "menu:run:1"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user = MagicMock(id=123)
    query.message = MagicMock(chat_id=456)
    update.callback_query = query

    mock_claude = AsyncMock()
    mock_response = MagicMock(content="Done!", session_id="sess123")
    mock_claude.run_command = AsyncMock(return_value=mock_response)

    context = MagicMock()
    context.user_data = {
        "current_directory": "/home/florian",
        "menu_builder": MagicMock(
            resolve_id=MagicMock(return_value="commit-commands:commit"),
            items=[PaletteItem(
                id="commit-commands:commit", name="commit",
                description="Git commit", action_type=ActionType.INJECT_SKILL,
                action_value="/commit", source="commit-commands", enabled=True,
            )],
        ),
    }
    context.bot_data = {"claude_integration": mock_claude}
    context.bot = AsyncMock()

    from src.bot.handlers.menu import menu_callback
    await menu_callback(update, context)

    mock_claude.run_command.assert_called_once()
    context.bot.send_message.assert_called_once()
```

**Step 4: Commit**

```bash
git add src/bot/handlers/menu.py tests/unit/test_bot/test_menu.py
git commit -m "feat(menu): inject skill invocations into Claude session"
```

---

### Task 10: Integration Test — Full Menu Flow

**Files:**
- Test: `tests/unit/test_bot/test_menu.py`

**Step 1: Write integration test**

```python
@pytest.mark.asyncio
async def test_full_menu_flow_category_navigation():
    """Test: /menu -> tap category -> tap item."""
    # This tests the full flow without Telegram API
    scanner_items = [
        PaletteItem(
            id="bot:status", name="status", description="Session status",
            action_type=ActionType.DIRECT_COMMAND, action_value="/status",
            source="bot", enabled=True,
        ),
        PaletteItem(
            id="superpowers:brainstorming", name="brainstorming",
            description="Creative work", action_type=ActionType.INJECT_SKILL,
            action_value="/brainstorming", source="superpowers", enabled=True,
        ),
        PaletteItem(
            id="superpowers:tdd", name="test-driven-development",
            description="TDD workflow", action_type=ActionType.INJECT_SKILL,
            action_value="/test-driven-development", source="superpowers", enabled=True,
        ),
    ]
    scanner_plugins = [
        PluginInfo(
            name="superpowers", qualified_name="superpowers@claude-plugins-official",
            version="4.3.1", enabled=True,
            items=scanner_items[1:],  # brainstorming + tdd
        ),
    ]

    builder = MenuBuilder(scanner_items, scanner_plugins)

    # Step 1: Build top-level
    top_kb = builder.build_top_level()
    assert top_kb is not None

    # Step 2: Find superpowers category button and resolve its ID
    sp_btn = None
    for row in top_kb.inline_keyboard:
        for btn in row:
            if "superpowers" in btn.text:
                sp_btn = btn
                break
    assert sp_btn is not None
    _, _, sid = sp_btn.callback_data.split(":", 2)
    resolved = builder.resolve_id(sid)
    assert resolved == "superpowers"

    # Step 3: Build category view
    cat_kb, header = builder.build_category("superpowers")
    assert "superpowers" in header
    cat_texts = [btn.text for row in cat_kb.inline_keyboard for btn in row]
    assert any("brainstorming" in t for t in cat_texts)
    assert any("test-driven" in t for t in cat_texts)
```

**Step 2: Run test**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/unit/test_bot/test_menu.py::test_full_menu_flow_category_navigation -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/test_bot/test_menu.py
git commit -m "test(menu): add full menu flow integration test"
```

---

### Task 11: Lint, Type Check, Final Test Suite

**Files:**
- All new/modified files

**Step 1: Run formatter**

Run: `cd /home/florian/config/claude-code-telegram && poetry run black src/bot/features/command_palette.py src/bot/handlers/menu.py tests/unit/test_bot/test_command_palette.py tests/unit/test_bot/test_menu.py`

**Step 2: Run isort**

Run: `cd /home/florian/config/claude-code-telegram && poetry run isort src/bot/features/command_palette.py src/bot/handlers/menu.py tests/unit/test_bot/test_command_palette.py tests/unit/test_bot/test_menu.py`

**Step 3: Run flake8**

Run: `cd /home/florian/config/claude-code-telegram && poetry run flake8 src/bot/features/command_palette.py src/bot/handlers/menu.py`

**Step 4: Run mypy**

Run: `cd /home/florian/config/claude-code-telegram && poetry run mypy src/bot/features/command_palette.py src/bot/handlers/menu.py`

Fix any type errors.

**Step 5: Run full test suite**

Run: `cd /home/florian/config/claude-code-telegram && poetry run pytest tests/ -v --timeout=30`
Expected: All tests pass (existing + new)

**Step 6: Commit**

```bash
git add -A
git commit -m "chore(menu): lint, format, type check all menu code"
```

---

### Task 12: Copy to Installed Location + Restart Bot

**Files:**
- Copy new/modified files to `~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/`

**Step 1: Copy files**

```bash
# New files
cp src/bot/features/command_palette.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/bot/features/command_palette.py

cp src/bot/handlers/menu.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/bot/handlers/menu.py

# Modified files
cp src/bot/orchestrator.py ~/.local/share/uv/tools/claude-code-telegram/lib/python3.12/site-packages/src/bot/orchestrator.py
```

**Step 2: Install PyYAML if not already available**

Check: `pip show pyyaml` in the bot's venv.
If missing: add to pyproject.toml and reinstall.

**Step 3: Restart bot**

```bash
systemctl --user restart claude-telegram-bot
```

**Step 4: Check logs**

```bash
journalctl --user -u claude-telegram-bot -f
```

Verify no startup errors.

**Step 5: Test in Telegram**

1. Send `/menu` to the bot
2. Verify the command palette appears with categories
3. Tap a category (e.g. "superpowers") — verify sub-menu shows skills
4. Tap a skill (e.g. "brainstorming") — verify it invokes via Claude
5. Tap "Back" — verify return to top level
6. Tap a plugin toggle — verify enable/disable works
7. Tap "Plugin Store" — verify placeholder message

**Step 6: Commit if any fixes needed**

```bash
git add -A
git commit -m "fix(menu): adjustments from live testing"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | Data models (PaletteItem, PluginInfo, ActionType) | `command_palette.py` | 3 |
| 2 | YAML frontmatter parser | `command_palette.py` | 5 |
| 3 | Filesystem scanner (CommandPaletteScanner) | `command_palette.py` | 6 |
| 4 | Plugin toggle (enable/disable) | `command_palette.py` | 2 |
| 5 | Menu keyboard builder (MenuBuilder) | `menu.py` | 5 |
| 6 | Menu command handler + callback router | `menu.py` | 1 |
| 7 | Wire into orchestrator | `orchestrator.py` | 3 |
| 8 | Skill injection (pending skill storage) | `menu.py` | 1 |
| 9 | Skill injection bridge (Claude call) | `menu.py` | 1 |
| 10 | Integration test | `test_menu.py` | 1 |
| 11 | Lint + type check + full suite | all | 0 |
| 12 | Deploy + live test | installed copy | 0 |

**Total: 12 tasks, ~28 tests, 2 new files, 1 modified file**
