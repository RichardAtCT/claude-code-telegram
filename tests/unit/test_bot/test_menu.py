"""Tests for the dynamic command palette menu builder and handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup

from src.bot.features.command_palette import (
    ActionType,
    BOT_COMMANDS,
    CommandPaletteScanner,
    PaletteItem,
    PluginInfo,
)
from src.bot.handlers.menu import MenuBuilder, menu_callback, menu_command


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bot_items() -> list[PaletteItem]:
    """Return the standard bot commands."""
    return list(BOT_COMMANDS)


@pytest.fixture
def single_item_plugin() -> PluginInfo:
    """A plugin with exactly one item."""
    item = PaletteItem(
        id="single-plugin:deploy",
        name="deploy",
        description="Deploy the app",
        action_type=ActionType.INJECT_SKILL,
        action_value="/deploy",
        source="single-plugin",
        enabled=True,
    )
    return PluginInfo(
        name="single-plugin",
        qualified_name="single-plugin@marketplace",
        version="1.0.0",
        enabled=True,
        items=[item],
        install_path="/some/path",
    )


@pytest.fixture
def multi_item_plugin() -> PluginInfo:
    """A plugin with multiple items."""
    items = [
        PaletteItem(
            id="multi-plugin:review",
            name="review",
            description="Review code",
            action_type=ActionType.INJECT_SKILL,
            action_value="/review",
            source="multi-plugin",
            enabled=True,
        ),
        PaletteItem(
            id="multi-plugin:test",
            name="test",
            description="Run tests",
            action_type=ActionType.INJECT_SKILL,
            action_value="/test",
            source="multi-plugin",
            enabled=True,
        ),
    ]
    return PluginInfo(
        name="multi-plugin",
        qualified_name="multi-plugin@marketplace",
        version="2.0.0",
        enabled=True,
        items=items,
        install_path="/other/path",
    )


@pytest.fixture
def disabled_plugin() -> PluginInfo:
    """A disabled plugin."""
    item = PaletteItem(
        id="off-plugin:autofill",
        name="autofill",
        description="Auto-fill forms",
        action_type=ActionType.INJECT_SKILL,
        action_value="/autofill",
        source="off-plugin",
        enabled=False,
    )
    return PluginInfo(
        name="off-plugin",
        qualified_name="off-plugin@marketplace",
        version="1.0.0",
        enabled=False,
        items=[item],
        install_path="/disabled/path",
    )


@pytest.fixture
def custom_item() -> PaletteItem:
    """A custom user skill."""
    return PaletteItem(
        id="custom:summarize",
        name="summarize",
        description="Summarize text",
        action_type=ActionType.INJECT_SKILL,
        action_value="/summarize",
        source="custom",
        enabled=True,
    )


@pytest.fixture
def all_items(
    bot_items: list[PaletteItem],
    single_item_plugin: PluginInfo,
    multi_item_plugin: PluginInfo,
    disabled_plugin: PluginInfo,
    custom_item: PaletteItem,
) -> list[PaletteItem]:
    """All palette items combined."""
    items = list(bot_items)
    items.extend(single_item_plugin.items)
    items.extend(multi_item_plugin.items)
    items.extend(disabled_plugin.items)
    items.append(custom_item)
    return items


@pytest.fixture
def all_plugins(
    single_item_plugin: PluginInfo,
    multi_item_plugin: PluginInfo,
    disabled_plugin: PluginInfo,
) -> list[PluginInfo]:
    """All plugins combined."""
    return [single_item_plugin, multi_item_plugin, disabled_plugin]


@pytest.fixture
def builder(
    all_items: list[PaletteItem],
    all_plugins: list[PluginInfo],
) -> MenuBuilder:
    """A MenuBuilder with all items loaded."""
    return MenuBuilder(all_items, all_plugins)


# ---------------------------------------------------------------------------
# MenuBuilder.build_top_level tests
# ---------------------------------------------------------------------------


class TestBuildTopLevel:
    """Tests for MenuBuilder.build_top_level()."""

    def test_returns_inline_keyboard(self, builder: MenuBuilder) -> None:
        result = builder.build_top_level()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_first_row_is_bot_category(self, builder: MenuBuilder) -> None:
        keyboard = builder.build_top_level()
        first_row = keyboard.inline_keyboard[0]
        assert len(first_row) == 1
        assert "Bot" in first_row[0].text
        assert first_row[0].callback_data.startswith("menu:cat:")

    def test_bot_category_shows_count(self, builder: MenuBuilder) -> None:
        keyboard = builder.build_top_level()
        bot_btn = keyboard.inline_keyboard[0][0]
        # Should contain count of bot items
        assert f"({len(BOT_COMMANDS)})" in bot_btn.text

    def test_has_plugin_categories(self, builder: MenuBuilder) -> None:
        keyboard = builder.build_top_level()
        all_buttons = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        plugin_names = ["multi-plugin", "off-plugin", "single-plugin"]
        for name in plugin_names:
            found = any(name in btn.text for btn in all_buttons)
            assert found, f"Plugin '{name}' not found in top-level menu"

    def test_single_item_plugin_runs_directly(
        self, builder: MenuBuilder
    ) -> None:
        keyboard = builder.build_top_level()
        all_buttons = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        single_btn = [
            btn for btn in all_buttons if "single-plugin" in btn.text
        ]
        assert len(single_btn) == 1
        assert single_btn[0].callback_data.startswith("menu:run:")

    def test_multi_item_plugin_opens_category(
        self, builder: MenuBuilder
    ) -> None:
        keyboard = builder.build_top_level()
        all_buttons = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        multi_btn = [
            btn for btn in all_buttons if "multi-plugin" in btn.text
        ]
        assert len(multi_btn) == 1
        assert multi_btn[0].callback_data.startswith("menu:cat:")

    def test_enabled_plugin_shows_checkmark(
        self, builder: MenuBuilder
    ) -> None:
        keyboard = builder.build_top_level()
        all_buttons = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        multi_btn = [
            btn for btn in all_buttons if "multi-plugin" in btn.text
        ][0]
        assert "\u2705" in multi_btn.text

    def test_disabled_plugin_shows_cross(
        self, builder: MenuBuilder
    ) -> None:
        keyboard = builder.build_top_level()
        all_buttons = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        off_btn = [
            btn for btn in all_buttons if "off-plugin" in btn.text
        ][0]
        assert "\u274c" in off_btn.text

    def test_custom_skills_have_buttons(
        self, builder: MenuBuilder
    ) -> None:
        keyboard = builder.build_top_level()
        all_buttons = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        custom_btns = [
            btn for btn in all_buttons if "summarize" in btn.text
        ]
        assert len(custom_btns) == 1
        assert custom_btns[0].callback_data.startswith("menu:run:")

    def test_last_row_is_plugin_store(self, builder: MenuBuilder) -> None:
        keyboard = builder.build_top_level()
        last_row = keyboard.inline_keyboard[-1]
        assert len(last_row) == 1
        assert "Plugin Store" in last_row[0].text
        assert last_row[0].callback_data == "menu:store"

    def test_plugins_sorted_by_name(self, builder: MenuBuilder) -> None:
        keyboard = builder.build_top_level()
        # Collect plugin button names (skip bot row at [0] and store row at [-1])
        plugin_labels: list[str] = []
        for row in keyboard.inline_keyboard[1:-1]:
            for btn in row:
                # Skip custom skill buttons (have sparkle emoji)
                if "\u2728" not in btn.text:
                    plugin_labels.append(btn.text)
        # Plugin names should be alphabetical
        if len(plugin_labels) > 1:
            names = [lbl.split(" ", 1)[-1] for lbl in plugin_labels]
            assert names == sorted(names)


# ---------------------------------------------------------------------------
# MenuBuilder.build_category tests
# ---------------------------------------------------------------------------


class TestBuildCategory:
    """Tests for MenuBuilder.build_category()."""

    def test_bot_category_returns_markup_and_header(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()  # populate id_map
        keyboard, header = builder.build_category("bot")
        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert "Bot" in header

    def test_bot_category_has_all_bot_commands(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, _ = builder.build_category("bot")
        # All rows except the last (Back) should be command buttons
        command_rows = keyboard.inline_keyboard[:-1]
        assert len(command_rows) == len(BOT_COMMANDS)

    def test_bot_category_has_back_button(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, _ = builder.build_category("bot")
        last_row = keyboard.inline_keyboard[-1]
        assert len(last_row) == 1
        assert "Back" in last_row[0].text
        assert last_row[0].callback_data == "menu:back"

    def test_bot_category_has_no_toggle(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, _ = builder.build_category("bot")
        all_data = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        assert not any(d.startswith("menu:tog:") for d in all_data)

    def test_plugin_category_has_items(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, header = builder.build_category("multi-plugin")
        assert "multi-plugin" in header
        # Should have 2 items + toggle + back = 4 rows
        assert len(keyboard.inline_keyboard) == 4

    def test_plugin_category_has_toggle(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, _ = builder.build_category("multi-plugin")
        all_data = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        toggle_data = [d for d in all_data if d.startswith("menu:tog:")]
        assert len(toggle_data) == 1
        assert "multi-plugin@marketplace" in toggle_data[0]

    def test_plugin_category_has_back(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, _ = builder.build_category("multi-plugin")
        last_row = keyboard.inline_keyboard[-1]
        assert "Back" in last_row[0].text
        assert last_row[0].callback_data == "menu:back"

    def test_enabled_plugin_toggle_says_disable(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, _ = builder.build_category("multi-plugin")
        toggle_btns = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
            if btn.callback_data.startswith("menu:tog:")
        ]
        assert len(toggle_btns) == 1
        assert "Disable" in toggle_btns[0].text

    def test_disabled_plugin_toggle_says_enable(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        keyboard, _ = builder.build_category("off-plugin")
        toggle_btns = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
            if btn.callback_data.startswith("menu:tog:")
        ]
        assert len(toggle_btns) == 1
        assert "Enable" in toggle_btns[0].text


# ---------------------------------------------------------------------------
# MenuBuilder.get_single_item_action tests
# ---------------------------------------------------------------------------


class TestGetSingleItemAction:
    """Tests for MenuBuilder.get_single_item_action()."""

    def test_single_item_plugin_returns_item(
        self, builder: MenuBuilder
    ) -> None:
        item = builder.get_single_item_action("single-plugin")
        assert item is not None
        assert item.name == "deploy"

    def test_multi_item_plugin_returns_none(
        self, builder: MenuBuilder
    ) -> None:
        result = builder.get_single_item_action("multi-plugin")
        assert result is None

    def test_nonexistent_plugin_returns_none(
        self, builder: MenuBuilder
    ) -> None:
        result = builder.get_single_item_action("does-not-exist")
        assert result is None


# ---------------------------------------------------------------------------
# MenuBuilder.resolve_id tests
# ---------------------------------------------------------------------------


class TestResolveId:
    """Tests for MenuBuilder.resolve_id()."""

    def test_resolves_after_build(self, builder: MenuBuilder) -> None:
        builder.build_top_level()
        # The first registered ID should be "0"
        result = builder.resolve_id("0")
        assert result is not None
        assert result == "cat:bot"

    def test_unknown_id_returns_none(self, builder: MenuBuilder) -> None:
        builder.build_top_level()
        result = builder.resolve_id("99999")
        assert result is None

    def test_all_ids_are_unique(self, builder: MenuBuilder) -> None:
        builder.build_top_level()
        values = list(builder.id_map.values())
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Callback data size check
# ---------------------------------------------------------------------------


class TestCallbackDataSize:
    """Telegram limits callback_data to 64 bytes."""

    def test_top_level_callback_data_under_64_bytes(
        self, builder: MenuBuilder
    ) -> None:
        keyboard = builder.build_top_level()
        for row in keyboard.inline_keyboard:
            for btn in row:
                data = btn.callback_data
                assert len(data.encode("utf-8")) <= 64, (
                    f"callback_data too long: {data!r} "
                    f"({len(data.encode('utf-8'))} bytes)"
                )

    def test_category_callback_data_under_64_bytes(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        for source in ["bot", "multi-plugin", "single-plugin", "off-plugin"]:
            keyboard, _ = builder.build_category(source)
            for row in keyboard.inline_keyboard:
                for btn in row:
                    data = btn.callback_data
                    assert len(data.encode("utf-8")) <= 64, (
                        f"callback_data too long: {data!r} "
                        f"({len(data.encode('utf-8'))} bytes)"
                    )


# ---------------------------------------------------------------------------
# menu_command handler tests
# ---------------------------------------------------------------------------


class TestMenuCommand:
    """Tests for the menu_command handler."""

    async def test_sends_message_with_keyboard(self) -> None:
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch(
            "src.bot.handlers.menu.CommandPaletteScanner"
        ) as MockScanner:
            scanner_instance = MockScanner.return_value
            scanner_instance.scan.return_value = (list(BOT_COMMANDS), [])

            await menu_command(update, context)

        update.message.reply_text.assert_called_once()
        call_kwargs = update.message.reply_text.call_args
        assert call_kwargs.kwargs.get("parse_mode") == "HTML"
        assert isinstance(
            call_kwargs.kwargs.get("reply_markup"), InlineKeyboardMarkup
        )

    async def test_stores_builder_in_user_data(self) -> None:
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch(
            "src.bot.handlers.menu.CommandPaletteScanner"
        ) as MockScanner:
            scanner_instance = MockScanner.return_value
            scanner_instance.scan.return_value = (list(BOT_COMMANDS), [])

            await menu_command(update, context)

        assert "menu_builder" in context.user_data
        assert isinstance(context.user_data["menu_builder"], MenuBuilder)

    async def test_message_contains_counts(self) -> None:
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch(
            "src.bot.handlers.menu.CommandPaletteScanner"
        ) as MockScanner:
            scanner_instance = MockScanner.return_value
            scanner_instance.scan.return_value = (list(BOT_COMMANDS), [])

            await menu_command(update, context)

        text = update.message.reply_text.call_args.args[0]
        assert "Command Palette" in text
        assert str(len(BOT_COMMANDS)) in text


# ---------------------------------------------------------------------------
# menu_callback handler tests
# ---------------------------------------------------------------------------


class TestMenuCallback:
    """Tests for the menu_callback handler."""

    def _make_callback_update(self, data: str) -> MagicMock:
        """Create a mock Update with callback_query."""
        update = MagicMock()
        update.callback_query.data = data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        return update

    async def test_back_rebuilds_top_level(
        self, builder: MenuBuilder
    ) -> None:
        builder.build_top_level()
        update = self._make_callback_update("menu:back")

        scanner = MagicMock()
        scanner.scan.return_value = (builder.items, builder.plugins)

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": scanner,
        }

        await menu_callback(update, context)

        update.callback_query.answer.assert_called_once()
        update.callback_query.edit_message_text.assert_called_once()
        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "Command Palette" in call_kwargs.args[0]
        assert isinstance(
            call_kwargs.kwargs.get("reply_markup"), InlineKeyboardMarkup
        )

    async def test_cat_shows_category(self, builder: MenuBuilder) -> None:
        keyboard = builder.build_top_level()
        # Find the short_id for "cat:bot" (should be "0")
        bot_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "cat:bot":
                bot_sid = sid
                break
        assert bot_sid is not None

        update = self._make_callback_update(f"menu:cat:{bot_sid}")

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
        }

        await menu_callback(update, context)

        update.callback_query.edit_message_text.assert_called_once()
        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "Bot" in call_kwargs.args[0]

    async def test_run_inject_skill_calls_claude(
        self, builder: MenuBuilder
    ) -> None:
        """When a skill button is tapped, Claude is called with the skill text."""
        builder.build_top_level()
        # Find a run-able skill ID
        skill_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "custom:summarize":
                skill_sid = sid
                break
        assert skill_sid is not None

        update = self._make_callback_update(f"menu:run:{skill_sid}")
        # Mock message.delete and message.chat_id
        update.callback_query.message.chat_id = 12345
        update.callback_query.message.delete = AsyncMock()
        update.callback_query.from_user.id = 999

        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = "Here is the summary."
        mock_response.session_id = "session-abc"
        mock_response.cost = 0.01

        mock_claude = AsyncMock()
        mock_claude.run_command = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.approved_directory = Path("/tmp/test")

        # Mock formatter
        mock_formatted = MagicMock()
        mock_formatted.text = "Here is the summary."
        mock_formatted.parse_mode = "HTML"

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
        }
        context.bot_data = {
            "claude_integration": mock_claude,
            "settings": mock_settings,
        }
        context.bot.send_chat_action = AsyncMock()
        context.bot.send_message = AsyncMock()

        with patch(
            "src.bot.handlers.menu.ResponseFormatter"
        ) as MockFormatter:
            formatter_instance = MockFormatter.return_value
            formatter_instance.format_claude_response.return_value = [
                mock_formatted
            ]
            await menu_callback(update, context)

        # Verify Claude was called with the skill text
        mock_claude.run_command.assert_called_once()
        call_kwargs = mock_claude.run_command.call_args.kwargs
        assert call_kwargs["prompt"] == "/summarize"
        assert call_kwargs["user_id"] == 999

        # Verify session ID was updated
        assert context.user_data["claude_session_id"] == "session-abc"

        # Verify response was sent
        context.bot.send_message.assert_called_once()
        send_kwargs = context.bot.send_message.call_args.kwargs
        assert send_kwargs["text"] == "Here is the summary."

    async def test_run_inject_skill_handles_error(
        self, builder: MenuBuilder
    ) -> None:
        """When Claude call fails, error is shown."""
        builder.build_top_level()
        skill_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "custom:summarize":
                skill_sid = sid
                break
        assert skill_sid is not None

        update = self._make_callback_update(f"menu:run:{skill_sid}")
        update.callback_query.message.chat_id = 12345
        update.callback_query.message.delete = AsyncMock()
        update.callback_query.from_user.id = 999

        mock_claude = AsyncMock()
        mock_claude.run_command = AsyncMock(
            side_effect=RuntimeError("Claude is down")
        )

        mock_settings = MagicMock()
        mock_settings.approved_directory = Path("/tmp/test")

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
        }
        context.bot_data = {
            "claude_integration": mock_claude,
            "settings": mock_settings,
        }
        context.bot.send_chat_action = AsyncMock()

        await menu_callback(update, context)

        # Verify error message was shown
        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "Failed to run" in call_kwargs.args[0]
        assert "Claude is down" in call_kwargs.args[0]

    async def test_run_inject_skill_no_claude_integration(
        self, builder: MenuBuilder
    ) -> None:
        """When Claude integration is missing, shows error."""
        builder.build_top_level()
        skill_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "custom:summarize":
                skill_sid = sid
                break
        assert skill_sid is not None

        update = self._make_callback_update(f"menu:run:{skill_sid}")

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
        }
        context.bot_data = {}  # No claude_integration

        await menu_callback(update, context)

        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "not available" in call_kwargs.args[0]

    async def test_run_direct_command_new(
        self, builder: MenuBuilder
    ) -> None:
        """When /new button is tapped, session is reset."""
        # Build category for bot to register bot command IDs
        builder.build_top_level()
        _, _ = builder.build_category("bot")
        # Find a bot command ID (e.g. bot:new)
        cmd_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "bot:new":
                cmd_sid = sid
                break
        assert cmd_sid is not None

        update = self._make_callback_update(f"menu:run:{cmd_sid}")

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
            "claude_session_id": "old-session",
        }
        context.bot_data = {}

        await menu_callback(update, context)

        # Session should be cleared
        assert context.user_data["claude_session_id"] is None
        assert context.user_data["force_new_session"] is True
        assert context.user_data["session_started"] is True
        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "Session reset" in call_kwargs.args[0]

    async def test_run_direct_command_status(
        self, builder: MenuBuilder
    ) -> None:
        """When /status button is tapped, status is shown."""
        builder.build_top_level()
        _, _ = builder.build_category("bot")
        cmd_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "bot:status":
                cmd_sid = sid
                break
        assert cmd_sid is not None

        update = self._make_callback_update(f"menu:run:{cmd_sid}")

        mock_settings = MagicMock()
        mock_settings.approved_directory = Path("/tmp/projects")

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
            "current_directory": Path("/home/test"),
            "claude_session_id": "sess-123",
        }
        context.bot_data = {"settings": mock_settings}

        await menu_callback(update, context)

        call_kwargs = update.callback_query.edit_message_text.call_args
        text = call_kwargs.args[0]
        assert "/home/test" in text
        assert "active" in text

    async def test_run_direct_command_status_no_session(
        self, builder: MenuBuilder
    ) -> None:
        """When /status is tapped with no session, shows 'none'."""
        builder.build_top_level()
        _, _ = builder.build_category("bot")
        cmd_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "bot:status":
                cmd_sid = sid
                break
        assert cmd_sid is not None

        update = self._make_callback_update(f"menu:run:{cmd_sid}")

        mock_settings = MagicMock()
        mock_settings.approved_directory = Path("/tmp/projects")

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
        }
        context.bot_data = {"settings": mock_settings}

        await menu_callback(update, context)

        call_kwargs = update.callback_query.edit_message_text.call_args
        text = call_kwargs.args[0]
        assert "none" in text

    async def test_run_direct_command_stop_no_active(
        self, builder: MenuBuilder
    ) -> None:
        """When /stop is tapped with no active calls, shows message."""
        builder.build_top_level()
        _, _ = builder.build_category("bot")
        cmd_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "bot:stop":
                cmd_sid = sid
                break
        assert cmd_sid is not None

        update = self._make_callback_update(f"menu:run:{cmd_sid}")

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
        }
        context.bot_data = {}

        await menu_callback(update, context)

        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "No active calls" in call_kwargs.args[0]

    async def test_run_inject_skill_updates_session_and_clears_force_new(
        self, builder: MenuBuilder
    ) -> None:
        """After a successful skill call, force_new is cleared and session updated."""
        builder.build_top_level()
        skill_sid = None
        for sid, full_id in builder.id_map.items():
            if full_id == "custom:summarize":
                skill_sid = sid
                break
        assert skill_sid is not None

        update = self._make_callback_update(f"menu:run:{skill_sid}")
        update.callback_query.message.chat_id = 12345
        update.callback_query.message.delete = AsyncMock()
        update.callback_query.from_user.id = 999

        mock_response = MagicMock()
        mock_response.content = "Done."
        mock_response.session_id = "new-session-id"
        mock_response.cost = 0.02

        mock_claude = AsyncMock()
        mock_claude.run_command = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.approved_directory = Path("/tmp/test")

        mock_formatted = MagicMock()
        mock_formatted.text = "Done."
        mock_formatted.parse_mode = "HTML"

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": None,
            "force_new_session": True,
            "claude_session_id": "old-session",
        }
        context.bot_data = {
            "claude_integration": mock_claude,
            "settings": mock_settings,
        }
        context.bot.send_chat_action = AsyncMock()
        context.bot.send_message = AsyncMock()

        with patch(
            "src.bot.handlers.menu.ResponseFormatter"
        ) as MockFormatter:
            formatter_instance = MockFormatter.return_value
            formatter_instance.format_claude_response.return_value = [
                mock_formatted
            ]
            await menu_callback(update, context)

        # force_new should be cleared
        assert context.user_data["force_new_session"] is False
        # Session ID should be updated
        assert context.user_data["claude_session_id"] == "new-session-id"
        # force_new=True should have been passed to run_command
        call_kwargs = mock_claude.run_command.call_args.kwargs
        assert call_kwargs["force_new"] is True

    async def test_tog_toggles_plugin(self, builder: MenuBuilder) -> None:
        builder.build_top_level()

        scanner = MagicMock()
        scanner.toggle_plugin.return_value = True
        scanner.scan.return_value = (builder.items, builder.plugins)

        update = self._make_callback_update(
            "menu:tog:multi-plugin@marketplace"
        )

        context = MagicMock()
        context.user_data = {
            "menu_builder": builder,
            "menu_scanner": scanner,
        }

        await menu_callback(update, context)

        scanner.toggle_plugin.assert_called_once_with(
            "multi-plugin@marketplace", False  # was enabled, now disable
        )
        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "disabled" in call_kwargs.args[0]

    async def test_store_shows_placeholder(self) -> None:
        update = self._make_callback_update("menu:store")

        context = MagicMock()
        context.user_data = {}

        await menu_callback(update, context)

        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "Plugin Store" in call_kwargs.args[0]
        assert "Coming soon" in call_kwargs.args[0]

    async def test_expired_session_on_back(self) -> None:
        update = self._make_callback_update("menu:back")

        context = MagicMock()
        context.user_data = {}  # no builder stored

        await menu_callback(update, context)

        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "expired" in call_kwargs.args[0].lower()

    async def test_unknown_action_handled(self) -> None:
        update = self._make_callback_update("menu:unknown_action")

        context = MagicMock()
        context.user_data = {}

        await menu_callback(update, context)

        call_kwargs = update.callback_query.edit_message_text.call_args
        assert "Unknown" in call_kwargs.args[0]
