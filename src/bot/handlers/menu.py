"""Dynamic command palette menu: inline keyboard builder + handlers."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..features.command_palette import (
    ActionType,
    CommandPaletteScanner,
    PaletteItem,
    PluginInfo,
)

logger = structlog.get_logger()


class MenuBuilder:
    """Builds inline keyboards for the command palette navigation.

    Telegram limits ``callback_data`` to 64 bytes.  We use short
    incrementing numeric IDs and store the mapping in ``id_map``.
    """

    def __init__(
        self, items: List[PaletteItem], plugins: List[PluginInfo]
    ) -> None:
        self.items = items
        self.plugins = plugins
        self.id_map: Dict[str, str] = {}  # short_id -> full_id
        self._counter = 0

    # ------------------------------------------------------------------
    # Short-ID helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        """Return the next short numeric ID as a string."""
        sid = str(self._counter)
        self._counter += 1
        return sid

    def _register(self, full_id: str) -> str:
        """Map *full_id* to a short numeric ID and return the short ID."""
        sid = self._next_id()
        self.id_map[sid] = full_id
        return sid

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_top_level(self) -> InlineKeyboardMarkup:
        """Build the top-level menu keyboard.

        Layout:
        - **Bot (count)** -- always first row
        - Each plugin with items -- sorted by name, 2 per row.
          Single-item plugins trigger directly (``menu:run:{id}``),
          multi-item plugins open a category (``menu:cat:{id}``).
        - Custom skills -- individual buttons
        - Plugin Store -- last row
        """
        # Reset short-ID state for a fresh build
        self.id_map.clear()
        self._counter = 0

        rows: List[List[InlineKeyboardButton]] = []

        # --- Bot category ---
        bot_items = [i for i in self.items if i.source == "bot"]
        bot_sid = self._register("cat:bot")
        rows.append(
            [
                InlineKeyboardButton(
                    f"\U0001f916 Bot ({len(bot_items)})",
                    callback_data=f"menu:cat:{bot_sid}",
                )
            ]
        )

        # --- Plugin categories (sorted by name, 2 per row) ---
        sorted_plugins = sorted(
            [p for p in self.plugins if p.items],
            key=lambda p: p.name,
        )
        plugin_buttons: List[InlineKeyboardButton] = []
        for plugin in sorted_plugins:
            status = "\u2705" if plugin.enabled else "\u274c"
            if len(plugin.items) == 1:
                # Single-item plugin -- tap runs directly
                item = plugin.items[0]
                sid = self._register(item.id)
                label = f"{status} {plugin.name}"
                plugin_buttons.append(
                    InlineKeyboardButton(
                        label, callback_data=f"menu:run:{sid}"
                    )
                )
            else:
                sid = self._register(f"cat:{plugin.name}")
                label = f"{status} {plugin.name} ({len(plugin.items)})"
                plugin_buttons.append(
                    InlineKeyboardButton(
                        label, callback_data=f"menu:cat:{sid}"
                    )
                )
        # Pack plugin buttons 2-per-row
        for i in range(0, len(plugin_buttons), 2):
            rows.append(plugin_buttons[i : i + 2])

        # --- Custom skills (individual buttons, 2-per-row) ---
        custom_items = [i for i in self.items if i.source == "custom"]
        custom_buttons: List[InlineKeyboardButton] = []
        for item in custom_items:
            sid = self._register(item.id)
            custom_buttons.append(
                InlineKeyboardButton(
                    f"\u2728 {item.name}",
                    callback_data=f"menu:run:{sid}",
                )
            )
        for i in range(0, len(custom_buttons), 2):
            rows.append(custom_buttons[i : i + 2])

        # --- Plugin Store (last row) ---
        rows.append(
            [
                InlineKeyboardButton(
                    "\U0001f50c Plugin Store", callback_data="menu:store"
                )
            ]
        )

        return InlineKeyboardMarkup(rows)

    def build_category(self, source: str) -> Tuple[InlineKeyboardMarkup, str]:
        """Build a category sub-menu keyboard.

        Args:
            source: The source identifier (``"bot"`` or a plugin name).

        Returns:
            Tuple of (keyboard, header_text).
        """
        if source == "bot":
            cat_items = [i for i in self.items if i.source == "bot"]
            header = "\U0001f916 <b>Bot commands</b>"
        else:
            cat_items = [i for i in self.items if i.source == source]
            plugin = self._find_plugin(source)
            status = ""
            if plugin:
                status = " \u2705" if plugin.enabled else " \u274c"
            header = f"\U0001f50c <b>{source}</b>{status}"

        rows: List[List[InlineKeyboardButton]] = []
        for item in cat_items:
            sid = self._register(item.id)
            label = f"{item.name} — {item.description}" if item.description else item.name
            rows.append(
                [
                    InlineKeyboardButton(
                        label, callback_data=f"menu:run:{sid}"
                    )
                ]
            )

        # Toggle button for plugins (not bot)
        if source != "bot":
            plugin = self._find_plugin(source)
            if plugin:
                action = "Disable" if plugin.enabled else "Enable"
                icon = "\u274c" if plugin.enabled else "\u2705"
                rows.append(
                    [
                        InlineKeyboardButton(
                            f"{icon} {action} {plugin.name}",
                            callback_data=f"menu:tog:{plugin.qualified_name}",
                        )
                    ]
                )

        # Back button
        rows.append(
            [
                InlineKeyboardButton(
                    "\u2b05 Back", callback_data="menu:back"
                )
            ]
        )

        return InlineKeyboardMarkup(rows), header

    def get_single_item_action(self, source: str) -> Optional[PaletteItem]:
        """Return the item if a plugin has exactly 1 item, else ``None``."""
        plugin = self._find_plugin(source)
        if plugin and len(plugin.items) == 1:
            return plugin.items[0]
        return None

    def resolve_id(self, short_id: str) -> Optional[str]:
        """Resolve a short callback ID to the full item/category ID."""
        return self.id_map.get(short_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_plugin(self, name: str) -> Optional[PluginInfo]:
        """Find a plugin by short name."""
        for p in self.plugins:
            if p.name == name:
                return p
        return None


# ======================================================================
# Telegram handler functions
# ======================================================================


async def menu_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle ``/menu`` -- scan filesystem, build top-level keyboard, send."""
    scanner = CommandPaletteScanner()
    items, plugins = scanner.scan()

    builder = MenuBuilder(items, plugins)
    keyboard = builder.build_top_level()

    # Persist builder for callback resolution
    if context.user_data is not None:
        context.user_data["menu_builder"] = builder
        context.user_data["menu_scanner"] = scanner

    item_count = len(items)
    plugin_count = len(plugins)
    custom_count = len([i for i in items if i.source == "custom"])

    text = (
        f"\U0001f3af <b>Command Palette</b>\n\n"
        f"{item_count} commands \u00b7 {plugin_count} plugins"
        f" \u00b7 {custom_count} custom skills"
    )

    await update.message.reply_text(  # type: ignore[union-attr]
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    logger.info(
        "Menu opened",
        items=item_count,
        plugins=plugin_count,
        custom=custom_count,
    )


async def menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle all ``menu:`` callbacks.

    Actions:
    - ``menu:back``            -- rebuild and show top-level
    - ``menu:cat:{id}``        -- show category sub-menu
    - ``menu:run:{id}``        -- execute item
    - ``menu:tog:{plugin}``    -- toggle plugin enable/disable
    - ``menu:store``           -- show plugin store placeholder
    """
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data = query.data or ""
    builder: Optional[MenuBuilder] = None
    scanner: Optional[CommandPaletteScanner] = None
    if context.user_data is not None:
        builder = context.user_data.get("menu_builder")
        scanner = context.user_data.get("menu_scanner")

    # ------------------------------------------------------------------
    # menu:back — rebuild top-level
    # ------------------------------------------------------------------
    if data == "menu:back":
        if builder is None:
            await query.edit_message_text("Session expired. Send /menu again.")
            return
        # Re-scan to reflect any toggle changes
        if scanner:
            items, plugins = scanner.scan()
            builder = MenuBuilder(items, plugins)
            if context.user_data is not None:
                context.user_data["menu_builder"] = builder

        keyboard = builder.build_top_level()
        item_count = len(builder.items)
        plugin_count = len(builder.plugins)
        custom_count = len([i for i in builder.items if i.source == "custom"])
        text = (
            f"\U0001f3af <b>Command Palette</b>\n\n"
            f"{item_count} commands \u00b7 {plugin_count} plugins"
            f" \u00b7 {custom_count} custom skills"
        )
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=keyboard
        )
        return

    # ------------------------------------------------------------------
    # menu:store — placeholder
    # ------------------------------------------------------------------
    if data == "menu:store":
        back_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "\u2b05 Back", callback_data="menu:back"
                    )
                ]
            ]
        )
        await query.edit_message_text(
            "\U0001f50c <b>Plugin Store</b>\n\nComing soon.",
            parse_mode="HTML",
            reply_markup=back_keyboard,
        )
        return

    # ------------------------------------------------------------------
    # menu:tog:{qualified_name} — toggle plugin
    # ------------------------------------------------------------------
    if data.startswith("menu:tog:"):
        qualified_name = data[len("menu:tog:") :]
        if scanner is None:
            await query.edit_message_text("Session expired. Send /menu again.")
            return

        # Find current state
        plugin_info: Optional[PluginInfo] = None
        if builder:
            for p in builder.plugins:
                if p.qualified_name == qualified_name:
                    plugin_info = p
                    break

        new_state = not (plugin_info.enabled if plugin_info else True)
        success = scanner.toggle_plugin(qualified_name, new_state)

        if not success:
            await query.edit_message_text(
                f"\u26a0 Failed to toggle plugin.", parse_mode="HTML"
            )
            return

        # Re-scan and rebuild category
        items, plugins = scanner.scan()
        builder = MenuBuilder(items, plugins)
        if context.user_data is not None:
            context.user_data["menu_builder"] = builder

        # Find plugin name from qualified_name
        source_name = qualified_name.split("@")[0]
        keyboard, header = builder.build_category(source_name)
        state_label = "enabled" if new_state else "disabled"
        text = f"{header}\n\nPlugin {state_label}."
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=keyboard
        )
        logger.info(
            "Plugin toggled",
            plugin=qualified_name,
            enabled=new_state,
        )
        return

    # ------------------------------------------------------------------
    # menu:cat:{short_id} — show category sub-menu
    # ------------------------------------------------------------------
    if data.startswith("menu:cat:"):
        short_id = data[len("menu:cat:") :]
        if builder is None:
            await query.edit_message_text("Session expired. Send /menu again.")
            return

        full_id = builder.resolve_id(short_id)
        if full_id is None or not full_id.startswith("cat:"):
            await query.edit_message_text("Invalid menu action.")
            return

        source = full_id[len("cat:") :]
        keyboard, header = builder.build_category(source)
        await query.edit_message_text(
            header, parse_mode="HTML", reply_markup=keyboard
        )
        return

    # ------------------------------------------------------------------
    # menu:run:{short_id} — execute item
    # ------------------------------------------------------------------
    if data.startswith("menu:run:"):
        short_id = data[len("menu:run:") :]
        if builder is None:
            await query.edit_message_text("Session expired. Send /menu again.")
            return

        full_id = builder.resolve_id(short_id)
        if full_id is None:
            await query.edit_message_text("Invalid menu action.")
            return

        # Find the PaletteItem
        item: Optional[PaletteItem] = None
        for candidate in builder.items:
            if candidate.id == full_id:
                item = candidate
                break

        if item is None:
            await query.edit_message_text("Command not found.")
            return

        if item.action_type == ActionType.INJECT_SKILL:
            # Store pending skill for Task 8-9 integration
            if context.user_data is not None:
                context.user_data["menu_pending_skill"] = item.action_value
            await query.edit_message_text(
                f"Invoking <code>{item.action_value}</code>...",
                parse_mode="HTML",
            )
            logger.info(
                "Menu skill invoked",
                item_id=item.id,
                action=item.action_value,
            )
        elif item.action_type == ActionType.DIRECT_COMMAND:
            # Store pending command for Task 8-9 integration
            if context.user_data is not None:
                context.user_data["menu_pending_command"] = item.action_value
            await query.edit_message_text(
                f"Running <code>{item.action_value}</code>...",
                parse_mode="HTML",
            )
            logger.info(
                "Menu command invoked",
                item_id=item.id,
                action=item.action_value,
            )
        return

    # Fallback for unknown actions
    await query.edit_message_text("Unknown menu action.")
