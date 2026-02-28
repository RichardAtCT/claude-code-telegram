"""Dynamic command palette: scans ~/.claude/ for skills, commands, and plugins."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class ActionType(Enum):
    """How a palette item is executed."""

    DIRECT_COMMAND = "direct"
    INJECT_SKILL = "inject"


@dataclass
class PaletteItem:
    """A single actionable item in the command palette."""

    id: str
    name: str
    description: str
    action_type: ActionType
    action_value: str
    source: str
    enabled: bool = True


@dataclass
class PluginInfo:
    """Metadata about an installed plugin."""

    name: str
    qualified_name: str
    version: str
    enabled: bool
    items: List[PaletteItem] = field(default_factory=list)
    install_path: str = ""


def parse_skill_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from a SKILL.md or command .md file.

    Uses simple key: value parsing to avoid adding a PyYAML dependency.
    Handles standard single-line ``key: value`` pairs.  Lines starting
    with ``#`` and blank lines inside the frontmatter block are skipped.

    Args:
        content: Full text content of the markdown file.

    Returns:
        Dictionary of parsed frontmatter key/value pairs, or ``{}`` if
        no valid frontmatter block is found.
    """
    if not content.strip():
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    try:
        result: Dict[str, Any] = {}
        for line in match.group(1).strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip()
        return result
    except Exception:
        logger.warning("Failed to parse SKILL.md frontmatter")
        return {}


BOT_COMMANDS: List[PaletteItem] = [
    PaletteItem(
        id="bot:new",
        name="new",
        description="Start a fresh session",
        action_type=ActionType.DIRECT_COMMAND,
        action_value="/new",
        source="bot",
    ),
    PaletteItem(
        id="bot:status",
        name="status",
        description="Show session status",
        action_type=ActionType.DIRECT_COMMAND,
        action_value="/status",
        source="bot",
    ),
    PaletteItem(
        id="bot:repo",
        name="repo",
        description="List repos / switch workspace",
        action_type=ActionType.DIRECT_COMMAND,
        action_value="/repo",
        source="bot",
    ),
    PaletteItem(
        id="bot:verbose",
        name="verbose",
        description="Set output verbosity (0/1/2)",
        action_type=ActionType.DIRECT_COMMAND,
        action_value="/verbose",
        source="bot",
    ),
    PaletteItem(
        id="bot:stop",
        name="stop",
        description="Stop running Claude call",
        action_type=ActionType.DIRECT_COMMAND,
        action_value="/stop",
        source="bot",
    ),
]


class CommandPaletteScanner:
    """Scans ~/.claude/ for all available skills, commands, and plugins."""

    def __init__(self, claude_dir: Optional[Path] = None) -> None:
        self.claude_dir = claude_dir or Path.home() / ".claude"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> Tuple[List[PaletteItem], List[PluginInfo]]:
        """Discover all palette items and plugin info from the filesystem.

        Returns:
            A tuple of (all palette items, plugin info list).
        """
        items: List[PaletteItem] = []
        plugins: List[PluginInfo] = []

        # Always include built-in bot commands
        items.extend(BOT_COMMANDS)

        if not self.claude_dir.is_dir():
            return items, plugins

        enabled_plugins = self._load_enabled_plugins()
        installed_plugins = self._load_installed_plugins()
        blocklisted = self._load_blocklist()

        # --- Installed plugins ---
        for qualified_name, installs in installed_plugins.items():
            if not installs:
                continue
            install = installs[0]
            install_path = Path(install.get("installPath", ""))
            version = install.get("version", "unknown")
            short_name = qualified_name.split("@")[0]

            is_enabled = enabled_plugins.get(qualified_name, False)
            is_blocked = any(b.get("plugin") == qualified_name for b in blocklisted)
            effective_enabled = is_enabled and not is_blocked

            plugin_items: List[PaletteItem] = []

            # Plugin skills
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

            # Plugin commands
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

        # --- Custom user skills ---
        custom_dir = self.claude_dir / "skills"
        if custom_dir.is_dir():
            for skill_dir in sorted(custom_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_file = skill_dir / "SKILL.md"
                if skill_file.is_file():
                    item = self._parse_skill_file(skill_file, "custom", True)
                    if item:
                        item.source = "custom"
                        items.append(item)

        return items, plugins

    def toggle_plugin(self, qualified_name: str, enabled: bool) -> bool:
        """Enable or disable a plugin by updating settings.json.

        Args:
            qualified_name: The fully qualified plugin name (e.g. ``name@marketplace``).
            enabled: Whether the plugin should be enabled.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
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
            logger.error(
                "Failed to toggle plugin",
                plugin=qualified_name,
                error=str(e),
            )
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_skill_file(
        self, path: Path, source: str, enabled: bool
    ) -> Optional[PaletteItem]:
        """Parse a SKILL.md file and return a PaletteItem, or ``None``."""
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
        """Parse a command .md file and return a PaletteItem, or ``None``."""
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
        """Load the ``enabledPlugins`` map from settings.json."""
        settings_file = self.claude_dir / "settings.json"
        if not settings_file.is_file():
            return {}
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return data.get("enabledPlugins", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_installed_plugins(self) -> Dict[str, list]:
        """Load the installed plugins map from installed_plugins.json."""
        installed_file = self.claude_dir / "plugins" / "installed_plugins.json"
        if not installed_file.is_file():
            return {}
        try:
            data = json.loads(installed_file.read_text(encoding="utf-8"))
            return data.get("plugins", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_blocklist(self) -> list:
        """Load the blocklist from blocklist.json."""
        blocklist_file = self.claude_dir / "plugins" / "blocklist.json"
        if not blocklist_file.is_file():
            return []
        try:
            data = json.loads(blocklist_file.read_text(encoding="utf-8"))
            return data.get("plugins", [])
        except (json.JSONDecodeError, OSError):
            return []
