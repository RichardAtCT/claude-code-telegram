"""Example plugin — reference implementation.

Demonstrates how to create a plugin that:
- Adds a /hello command
- Subscribes to events
- Uses hooks

To enable: place this file in your plugins directory and set
PLUGINS_DIRECTORY in your config.
"""

from typing import Any, Coroutine, Dict, List, Tuple

import structlog

from ..events.bus import Event
from .base import CommandHandler, Plugin, PluginContext

logger = structlog.get_logger()


class HelloPlugin(Plugin):
    """Simple greeting plugin for demonstration."""

    def __init__(self) -> None:
        self._context: PluginContext | None = None

    @property
    def name(self) -> str:
        return "hello"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Example plugin that adds a /hello command"

    @property
    def author(self) -> str:
        return "claude-code-telegram"

    async def setup(self, context: PluginContext) -> None:
        """Store context for later use."""
        self._context = context
        context.logger.info("HelloPlugin initialized")

    async def teardown(self) -> None:
        """Clean up resources."""
        if self._context:
            self._context.logger.info("HelloPlugin shutting down")
        self._context = None

    def get_commands(self) -> List[Tuple[str, str, CommandHandler]]:
        """Register the /hello command."""
        return [
            ("hello", "Say hello (example plugin)", self._hello_command),
        ]

    def get_event_handlers(self) -> Dict[type, Any]:
        """Subscribe to all events for logging (demonstration)."""
        return {
            Event: self._on_any_event,
        }

    async def _hello_command(self, update: Any, context: Any) -> None:
        """Handle /hello command."""
        user = update.effective_user
        await update.message.reply_text(
            f"Hello {user.first_name}! This response comes from the "
            f"'{self.name}' plugin (v{self.version})."
        )

    async def _on_any_event(self, event: Event) -> None:
        """Log all events (demonstration of event subscription)."""
        if self._context:
            self._context.logger.debug(
                "Event observed by HelloPlugin",
                event_type=event.event_type,
                event_id=event.id,
            )


def create_plugin() -> Plugin:
    """Factory function — required for plugin discovery."""
    return HelloPlugin()
