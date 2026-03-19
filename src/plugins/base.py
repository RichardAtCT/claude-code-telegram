"""Plugin base classes and data structures.

Defines the Plugin ABC that all plugins must implement,
along with PluginContext and PluginMetadata.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import structlog

from ..events.bus import Event, EventBus

logger = structlog.get_logger()

# Type alias for async command handlers
CommandHandler = Callable[..., Coroutine[Any, Any, None]]

# Type alias for async event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


@dataclass
class PluginMetadata:
    """Metadata describing a plugin."""

    name: str
    version: str
    description: str
    author: str
    dependencies: List[str] = field(default_factory=list)


@dataclass
class PluginContext:
    """Context provided to plugins during setup.

    Gives plugins access to core bot infrastructure without
    tight coupling to internal implementations.
    """

    bot: Any  # ClaudeCodeBot instance
    event_bus: EventBus
    storage: Any  # Storage instance (optional)
    settings: Any  # Settings instance
    logger: Any  # structlog logger


class Plugin(ABC):
    """Abstract base class for all plugins.

    Plugins extend bot functionality by:
    - Registering commands (Telegram command handlers)
    - Subscribing to events via the EventBus
    - Hooking into message processing pipeline
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin name."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string (semver recommended)."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        return ""

    @property
    def author(self) -> str:
        """Plugin author."""
        return "unknown"

    @property
    def dependencies(self) -> List[str]:
        """List of plugin names this plugin depends on."""
        return []

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            dependencies=self.dependencies,
        )

    @abstractmethod
    async def setup(self, context: PluginContext) -> None:
        """Initialize the plugin with the provided context.

        Called once during bot startup after all dependencies are resolved.
        Use this to register event handlers, initialize state, etc.
        """
        ...

    async def teardown(self) -> None:
        """Clean up plugin resources.

        Called during bot shutdown in reverse dependency order.
        Override to release connections, flush buffers, etc.
        """
        pass

    def get_commands(self) -> List[Tuple[str, str, CommandHandler]]:
        """Return list of (command_name, description, handler) tuples.

        These are registered as Telegram bot commands.
        The handler receives (update, context) like standard handlers.

        Returns empty list by default — override to add commands.
        """
        return []

    def get_event_handlers(self) -> Dict[type, EventHandler]:
        """Return mapping of event types to async handler functions.

        These are wired to the EventBus during plugin registration.

        Returns empty dict by default — override to subscribe to events.
        """
        return {}
