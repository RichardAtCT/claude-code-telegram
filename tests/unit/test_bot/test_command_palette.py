"""Tests for the dynamic command palette scanner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.bot.features.command_palette import (
    ActionType,
    BOT_COMMANDS,
    CommandPaletteScanner,
    PaletteItem,
    PluginInfo,
    parse_skill_frontmatter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_claude_dir(tmp_path: Path) -> Path:
    """Create a realistic ~/.claude/ directory tree for testing.

    Layout::

        tmp/
        ├── settings.json
        ├── plugins/
        │   ├── installed_plugins.json
        │   ├── blocklist.json
        │   └── cache/claude-plugins-official/
        │       └── my-plugin/1.0.0/
        │           ├── skills/brainstorming/SKILL.md
        │           └── commands/review.md
        └── skills/
            └── my-custom-skill/SKILL.md
    """
    # settings.json
    settings = {
        "enabledPlugins": {
            "my-plugin@marketplace": True,
            "disabled-plugin@marketplace": False,
        }
    }
    (tmp_path / "settings.json").write_text(
        json.dumps(settings, indent=2), encoding="utf-8"
    )

    # plugins directory
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    # installed_plugins.json
    plugin_install_path = (
        plugins_dir
        / "cache"
        / "claude-plugins-official"
        / "my-plugin"
        / "1.0.0"
    )
    plugin_install_path.mkdir(parents=True)

    disabled_plugin_path = (
        plugins_dir
        / "cache"
        / "claude-plugins-official"
        / "disabled-plugin"
        / "2.0.0"
    )
    disabled_plugin_path.mkdir(parents=True)

    installed = {
        "plugins": {
            "my-plugin@marketplace": [
                {
                    "installPath": str(plugin_install_path),
                    "version": "1.0.0",
                }
            ],
            "disabled-plugin@marketplace": [
                {
                    "installPath": str(disabled_plugin_path),
                    "version": "2.0.0",
                }
            ],
        }
    }
    (plugins_dir / "installed_plugins.json").write_text(
        json.dumps(installed, indent=2), encoding="utf-8"
    )

    # blocklist.json — empty
    (plugins_dir / "blocklist.json").write_text(
        json.dumps({"plugins": []}, indent=2), encoding="utf-8"
    )

    # Plugin skill: my-plugin/skills/brainstorming/SKILL.md
    skill_dir = plugin_install_path / "skills" / "brainstorming"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: brainstorming\ndescription: Use before creative work\n---\n"
        "# Brainstorming\nContent here.\n",
        encoding="utf-8",
    )

    # Plugin command: my-plugin/commands/review.md
    cmd_dir = plugin_install_path / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "review.md").write_text(
        "---\nname: review\ndescription: Review code changes\n---\n"
        "# Review\nRun code review.\n",
        encoding="utf-8",
    )

    # Disabled plugin skill
    disabled_skill_dir = disabled_plugin_path / "skills" / "autofill"
    disabled_skill_dir.mkdir(parents=True)
    (disabled_skill_dir / "SKILL.md").write_text(
        "---\nname: autofill\ndescription: Auto-fill forms\n---\n"
        "# Autofill\nFills forms.\n",
        encoding="utf-8",
    )

    # Custom user skill
    custom_skill_dir = tmp_path / "skills" / "my-custom-skill"
    custom_skill_dir.mkdir(parents=True)
    (custom_skill_dir / "SKILL.md").write_text(
        "---\nname: summarize\ndescription: Summarize any text\n---\n"
        "# Summarize\nSummarizes content.\n",
        encoding="utf-8",
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestActionType:
    """Test ActionType enum values."""

    def test_direct_command_value(self) -> None:
        assert ActionType.DIRECT_COMMAND.value == "direct"

    def test_inject_skill_value(self) -> None:
        assert ActionType.INJECT_SKILL.value == "inject"

    def test_enum_members(self) -> None:
        members = list(ActionType)
        assert len(members) == 2
        assert ActionType.DIRECT_COMMAND in members
        assert ActionType.INJECT_SKILL in members


class TestPaletteItem:
    """Test PaletteItem dataclass."""

    def test_creation_with_defaults(self) -> None:
        item = PaletteItem(
            id="test:item",
            name="item",
            description="A test item",
            action_type=ActionType.DIRECT_COMMAND,
            action_value="/item",
            source="test",
        )
        assert item.id == "test:item"
        assert item.name == "item"
        assert item.description == "A test item"
        assert item.action_type == ActionType.DIRECT_COMMAND
        assert item.action_value == "/item"
        assert item.source == "test"
        assert item.enabled is True  # default

    def test_creation_disabled(self) -> None:
        item = PaletteItem(
            id="x:y",
            name="y",
            description="",
            action_type=ActionType.INJECT_SKILL,
            action_value="/y",
            source="plugin",
            enabled=False,
        )
        assert item.enabled is False

    def test_equality(self) -> None:
        a = PaletteItem(
            id="a:b",
            name="b",
            description="desc",
            action_type=ActionType.DIRECT_COMMAND,
            action_value="/b",
            source="bot",
        )
        b = PaletteItem(
            id="a:b",
            name="b",
            description="desc",
            action_type=ActionType.DIRECT_COMMAND,
            action_value="/b",
            source="bot",
        )
        assert a == b


class TestPluginInfo:
    """Test PluginInfo dataclass."""

    def test_creation_with_defaults(self) -> None:
        plugin = PluginInfo(
            name="test",
            qualified_name="test@marketplace",
            version="1.0.0",
            enabled=True,
        )
        assert plugin.name == "test"
        assert plugin.qualified_name == "test@marketplace"
        assert plugin.version == "1.0.0"
        assert plugin.enabled is True
        assert plugin.items == []
        assert plugin.install_path == ""

    def test_creation_with_items(self) -> None:
        item = PaletteItem(
            id="p:s",
            name="s",
            description="",
            action_type=ActionType.INJECT_SKILL,
            action_value="/s",
            source="p",
        )
        plugin = PluginInfo(
            name="p",
            qualified_name="p@marketplace",
            version="2.0.0",
            enabled=False,
            items=[item],
            install_path="/some/path",
        )
        assert len(plugin.items) == 1
        assert plugin.install_path == "/some/path"

    def test_items_default_is_not_shared(self) -> None:
        """Verify that each instance gets its own list."""
        a = PluginInfo(
            name="a",
            qualified_name="a@m",
            version="1",
            enabled=True,
        )
        b = PluginInfo(
            name="b",
            qualified_name="b@m",
            version="1",
            enabled=True,
        )
        a.items.append(
            PaletteItem(
                id="x:y",
                name="y",
                description="",
                action_type=ActionType.INJECT_SKILL,
                action_value="/y",
                source="x",
            )
        )
        assert len(b.items) == 0


# ---------------------------------------------------------------------------
# Frontmatter parser tests
# ---------------------------------------------------------------------------


class TestParseSkillFrontmatter:
    """Test the YAML frontmatter parser."""

    def test_valid_frontmatter(self) -> None:
        content = (
            "---\n"
            "name: brainstorming\n"
            "description: Use before creative work\n"
            "---\n"
            "# Content\n"
        )
        result = parse_skill_frontmatter(content)
        assert result["name"] == "brainstorming"
        assert result["description"] == "Use before creative work"

    def test_frontmatter_with_allowed_tools(self) -> None:
        content = (
            "---\n"
            "name: deploy\n"
            "description: Deploy application\n"
            "allowed-tools: Bash, Read, Write\n"
            "---\n"
            "# Deploy\n"
        )
        result = parse_skill_frontmatter(content)
        assert result["name"] == "deploy"
        assert result["allowed-tools"] == "Bash, Read, Write"

    def test_no_frontmatter(self) -> None:
        content = "# Just a heading\nSome text.\n"
        result = parse_skill_frontmatter(content)
        assert result == {}

    def test_empty_content(self) -> None:
        result = parse_skill_frontmatter("")
        assert result == {}

    def test_whitespace_only(self) -> None:
        result = parse_skill_frontmatter("   \n  \n  ")
        assert result == {}

    def test_frontmatter_with_comments(self) -> None:
        content = (
            "---\n"
            "# This is a comment\n"
            "name: test\n"
            "---\n"
        )
        result = parse_skill_frontmatter(content)
        assert result == {"name": "test"}

    def test_frontmatter_with_blank_lines(self) -> None:
        content = (
            "---\n"
            "name: test\n"
            "\n"
            "description: desc\n"
            "---\n"
        )
        result = parse_skill_frontmatter(content)
        assert result["name"] == "test"
        assert result["description"] == "desc"

    def test_value_with_colon(self) -> None:
        """Values containing colons should preserve everything after first."""
        content = (
            "---\n"
            "name: my-skill\n"
            "description: Step 1: do this, Step 2: do that\n"
            "---\n"
        )
        result = parse_skill_frontmatter(content)
        assert result["description"] == "Step 1: do this, Step 2: do that"

    def test_unclosed_frontmatter(self) -> None:
        content = "---\nname: test\nSome body text\n"
        result = parse_skill_frontmatter(content)
        assert result == {}

    def test_frontmatter_not_at_start(self) -> None:
        content = "Some text\n---\nname: test\n---\n"
        result = parse_skill_frontmatter(content)
        assert result == {}


# ---------------------------------------------------------------------------
# Scanner tests
# ---------------------------------------------------------------------------


class TestCommandPaletteScanner:
    """Test the filesystem scanner."""

    def test_bot_commands_always_present(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        bot_items = [i for i in items if i.source == "bot"]
        assert len(bot_items) == len(BOT_COMMANDS)

    def test_bot_commands_are_direct(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        for item in items:
            if item.source == "bot":
                assert item.action_type == ActionType.DIRECT_COMMAND

    def test_discovers_plugin_skills(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        skill_names = [i.name for i in items if i.source == "my-plugin"]
        assert "brainstorming" in skill_names

    def test_discovers_plugin_commands(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        cmd_names = [i.name for i in items if i.source == "my-plugin"]
        assert "review" in cmd_names

    def test_plugin_skills_are_inject_type(
        self, mock_claude_dir: Path
    ) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        for item in items:
            if item.source == "my-plugin":
                assert item.action_type == ActionType.INJECT_SKILL

    def test_enabled_plugin_items_are_enabled(
        self, mock_claude_dir: Path
    ) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        enabled_items = [
            i for i in items if i.source == "my-plugin"
        ]
        for item in enabled_items:
            assert item.enabled is True

    def test_disabled_plugin_items_are_disabled(
        self, mock_claude_dir: Path
    ) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        disabled_items = [
            i for i in items if i.source == "disabled-plugin"
        ]
        for item in disabled_items:
            assert item.enabled is False

    def test_discovers_custom_skills(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        custom_items = [i for i in items if i.source == "custom"]
        assert len(custom_items) == 1
        assert custom_items[0].name == "summarize"

    def test_custom_skills_always_enabled(
        self, mock_claude_dir: Path
    ) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        custom_items = [i for i in items if i.source == "custom"]
        for item in custom_items:
            assert item.enabled is True

    def test_builds_plugin_info(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        _, plugins = scanner.scan()
        assert len(plugins) == 2

        by_name = {p.qualified_name: p for p in plugins}

        my_plugin = by_name["my-plugin@marketplace"]
        assert my_plugin.name == "my-plugin"
        assert my_plugin.version == "1.0.0"
        assert my_plugin.enabled is True
        assert len(my_plugin.items) == 2  # brainstorming + review

        disabled = by_name["disabled-plugin@marketplace"]
        assert disabled.name == "disabled-plugin"
        assert disabled.version == "2.0.0"
        assert disabled.enabled is False
        assert len(disabled.items) == 1  # autofill

    def test_missing_claude_dir(self, tmp_path: Path) -> None:
        """Scanner should return only bot commands if dir is missing."""
        missing = tmp_path / "nonexistent"
        scanner = CommandPaletteScanner(claude_dir=missing)
        items, plugins = scanner.scan()
        assert len(items) == len(BOT_COMMANDS)
        assert plugins == []

    def test_empty_claude_dir(self, tmp_path: Path) -> None:
        """Scanner with an empty directory returns only bot commands."""
        empty = tmp_path / "empty_claude"
        empty.mkdir()
        scanner = CommandPaletteScanner(claude_dir=empty)
        items, plugins = scanner.scan()
        assert len(items) == len(BOT_COMMANDS)
        assert plugins == []

    def test_blocklisted_plugin_is_disabled(
        self, mock_claude_dir: Path
    ) -> None:
        """A plugin on the blocklist should be treated as disabled."""
        blocklist = {"plugins": [{"plugin": "my-plugin@marketplace"}]}
        blocklist_file = mock_claude_dir / "plugins" / "blocklist.json"
        blocklist_file.write_text(
            json.dumps(blocklist, indent=2), encoding="utf-8"
        )

        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, plugins = scanner.scan()

        by_name = {p.qualified_name: p for p in plugins}
        my_plugin = by_name["my-plugin@marketplace"]
        assert my_plugin.enabled is False

        plugin_items = [i for i in items if i.source == "my-plugin"]
        for item in plugin_items:
            assert item.enabled is False

    def test_skill_without_name_is_skipped(
        self, mock_claude_dir: Path
    ) -> None:
        """A SKILL.md without a 'name' field should be ignored."""
        bad_skill_dir = mock_claude_dir / "skills" / "bad-skill"
        bad_skill_dir.mkdir(parents=True)
        (bad_skill_dir / "SKILL.md").write_text(
            "---\ndescription: No name field\n---\nContent\n",
            encoding="utf-8",
        )

        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        custom_items = [i for i in items if i.source == "custom"]
        # Only the original 'summarize' custom skill should be present
        assert len(custom_items) == 1
        assert custom_items[0].name == "summarize"

    def test_non_directory_in_skills_is_skipped(
        self, mock_claude_dir: Path
    ) -> None:
        """Regular files inside skills/ should be ignored."""
        (mock_claude_dir / "skills" / "stray_file.txt").write_text(
            "Not a skill", encoding="utf-8"
        )
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        items, _ = scanner.scan()
        custom_items = [i for i in items if i.source == "custom"]
        assert len(custom_items) == 1

    def test_malformed_settings_json(self, tmp_path: Path) -> None:
        """Scanner handles corrupt settings.json gracefully."""
        claude_dir = tmp_path / "claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text(
            "{bad json", encoding="utf-8"
        )
        scanner = CommandPaletteScanner(claude_dir=claude_dir)
        items, plugins = scanner.scan()
        assert len(items) == len(BOT_COMMANDS)

    def test_malformed_installed_plugins_json(self, tmp_path: Path) -> None:
        """Scanner handles corrupt installed_plugins.json gracefully."""
        claude_dir = tmp_path / "claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "installed_plugins.json").write_text(
            "not json!", encoding="utf-8"
        )
        (claude_dir / "settings.json").write_text(
            "{}", encoding="utf-8"
        )
        scanner = CommandPaletteScanner(claude_dir=claude_dir)
        items, plugins = scanner.scan()
        assert len(items) == len(BOT_COMMANDS)
        assert plugins == []

    def test_empty_install_list_for_plugin(self, tmp_path: Path) -> None:
        """A plugin with an empty installs array should be skipped."""
        claude_dir = tmp_path / "claude"
        plugins_dir = claude_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"ghost@mp": True}}),
            encoding="utf-8",
        )
        (plugins_dir / "installed_plugins.json").write_text(
            json.dumps({"plugins": {"ghost@mp": []}}),
            encoding="utf-8",
        )
        scanner = CommandPaletteScanner(claude_dir=claude_dir)
        items, plugins = scanner.scan()
        assert plugins == []


# ---------------------------------------------------------------------------
# toggle_plugin tests
# ---------------------------------------------------------------------------


class TestTogglePlugin:
    """Test the toggle_plugin method."""

    def test_enable_plugin(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        result = scanner.toggle_plugin("disabled-plugin@marketplace", True)
        assert result is True

        settings = json.loads(
            (mock_claude_dir / "settings.json").read_text(encoding="utf-8")
        )
        assert settings["enabledPlugins"]["disabled-plugin@marketplace"] is True

    def test_disable_plugin(self, mock_claude_dir: Path) -> None:
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        result = scanner.toggle_plugin("my-plugin@marketplace", False)
        assert result is True

        settings = json.loads(
            (mock_claude_dir / "settings.json").read_text(encoding="utf-8")
        )
        assert settings["enabledPlugins"]["my-plugin@marketplace"] is False

    def test_toggle_nonexistent_plugin(self, mock_claude_dir: Path) -> None:
        """Toggling a plugin that does not yet exist in settings should add it."""
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        result = scanner.toggle_plugin("new-plugin@marketplace", True)
        assert result is True

        settings = json.loads(
            (mock_claude_dir / "settings.json").read_text(encoding="utf-8")
        )
        assert settings["enabledPlugins"]["new-plugin@marketplace"] is True

    def test_toggle_creates_settings_file(self, tmp_path: Path) -> None:
        """toggle_plugin should create settings.json if it does not exist."""
        claude_dir = tmp_path / "fresh_claude"
        claude_dir.mkdir()
        scanner = CommandPaletteScanner(claude_dir=claude_dir)
        result = scanner.toggle_plugin("p@m", True)
        assert result is True

        settings = json.loads(
            (claude_dir / "settings.json").read_text(encoding="utf-8")
        )
        assert settings["enabledPlugins"]["p@m"] is True

    def test_toggle_preserves_existing_settings(
        self, mock_claude_dir: Path
    ) -> None:
        """Toggling one plugin should not clobber other settings."""
        scanner = CommandPaletteScanner(claude_dir=mock_claude_dir)
        scanner.toggle_plugin("new@mp", True)

        settings = json.loads(
            (mock_claude_dir / "settings.json").read_text(encoding="utf-8")
        )
        # Original entries should still be present
        assert "my-plugin@marketplace" in settings["enabledPlugins"]
        assert "disabled-plugin@marketplace" in settings["enabledPlugins"]
        assert settings["enabledPlugins"]["new@mp"] is True

    def test_toggle_fails_on_read_only_dir(self, tmp_path: Path) -> None:
        """toggle_plugin returns False when the file can't be written."""
        claude_dir = tmp_path / "ro_claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.json"
        settings_file.write_text("{}", encoding="utf-8")
        # Make the directory read-only so writing fails
        settings_file.chmod(0o444)
        claude_dir.chmod(0o555)

        scanner = CommandPaletteScanner(claude_dir=claude_dir)
        result = scanner.toggle_plugin("x@m", True)
        assert result is False

        # Restore permissions for cleanup
        claude_dir.chmod(0o755)
        settings_file.chmod(0o644)
