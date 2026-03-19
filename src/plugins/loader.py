"""Plugin discovery, loading, and lifecycle management.

Scans a directory for Python modules containing a `create_plugin()`
factory function, validates them, resolves dependencies, and manages
setup/teardown ordering.
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from ..events.bus import EventBus
from .base import Plugin, PluginContext, PluginMetadata
from .hooks import HookManager

logger = structlog.get_logger()


class PluginError(Exception):
    """Base exception for plugin system errors."""


class PluginLoadError(PluginError):
    """Failed to load a plugin module."""


class PluginDependencyError(PluginError):
    """Unresolved plugin dependency."""


class PluginManager:
    """Discovers, loads, validates, and manages plugin lifecycle.

    Usage:
        manager = PluginManager(event_bus, hook_manager)
        manager.load_plugins(Path("./plugins"))
        await manager.initialize_all(bot, settings, storage)
        # ... bot runs ...
        await manager.shutdown_all()
    """

    def __init__(
        self,
        event_bus: EventBus,
        hook_manager: HookManager,
    ) -> None:
        self._event_bus = event_bus
        self._hook_manager = hook_manager
        self._plugins: Dict[str, Plugin] = {}
        self._initialized: List[str] = []  # Track init order for reverse teardown
        self._enabled_plugins: Optional[List[str]] = None

    def set_enabled_plugins(self, names: Optional[List[str]]) -> None:
        """Restrict which plugins will be registered. None means all."""
        self._enabled_plugins = names

    def load_plugins(self, directory: Path) -> int:
        """Scan directory for plugin modules and load them.

        A valid plugin module must contain a `create_plugin()` function
        that returns a Plugin instance.

        Args:
            directory: Path to scan for .py plugin files.

        Returns:
            Number of plugins successfully loaded.
        """
        if not directory.is_dir():
            logger.warning("Plugin directory does not exist", path=str(directory))
            return 0

        loaded = 0
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                plugin = self.load_plugin(path)
                if plugin is not None:
                    self.register_plugin(plugin)
                    loaded += 1
            except PluginError as e:
                logger.error(
                    "Failed to load plugin",
                    path=str(path),
                    error=str(e),
                )

        logger.info("Plugin scan complete", directory=str(directory), loaded=loaded)
        return loaded

    def load_plugin(self, module_path: Path) -> Optional[Plugin]:
        """Import a single plugin module and call its factory function.

        Args:
            module_path: Path to a .py file with a `create_plugin()` function.

        Returns:
            Plugin instance, or None if module has no factory.

        Raises:
            PluginLoadError: If import fails or factory returns invalid type.
        """
        module_name = f"_plugin_{module_path.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Cannot create module spec for {module_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            # Clean up partial import
            sys.modules.pop(module_name, None)
            raise PluginLoadError(
                f"Failed to import {module_path}: {e}"
            ) from e

        factory = getattr(module, "create_plugin", None)
        if factory is None:
            logger.debug(
                "Module has no create_plugin(), skipping",
                path=str(module_path),
            )
            return None

        try:
            plugin = factory()
        except Exception as e:
            raise PluginLoadError(
                f"create_plugin() failed in {module_path}: {e}"
            ) from e

        if not isinstance(plugin, Plugin):
            raise PluginLoadError(
                f"create_plugin() in {module_path} returned {type(plugin).__name__}, "
                f"expected Plugin subclass"
            )

        return plugin

    def register_plugin(self, plugin: Plugin) -> None:
        """Add a plugin to the registry.

        Checks if the plugin name is unique and if it passes the
        enabled filter (if set).

        Args:
            plugin: Plugin instance to register.

        Raises:
            PluginError: If a plugin with the same name is already registered.
        """
        name = plugin.name

        if self._enabled_plugins is not None and name not in self._enabled_plugins:
            logger.info("Plugin not in enabled list, skipping", plugin=name)
            return

        if name in self._plugins:
            raise PluginError(f"Plugin '{name}' is already registered")

        self._plugins[name] = plugin
        logger.info(
            "Plugin registered",
            plugin=name,
            version=plugin.version,
        )

    async def initialize_all(
        self,
        bot: Any,
        settings: Any,
        storage: Any,
    ) -> None:
        """Call setup() on all plugins in dependency order.

        Args:
            bot: ClaudeCodeBot instance.
            settings: Application Settings.
            storage: Storage facade (may be None).

        Raises:
            PluginDependencyError: If dependencies cannot be resolved.
        """
        ordered = self._resolve_dependency_order()

        for name in ordered:
            plugin = self._plugins[name]
            context = PluginContext(
                bot=bot,
                event_bus=self._event_bus,
                storage=storage,
                settings=settings,
                logger=structlog.get_logger(plugin=name),
            )

            try:
                await plugin.setup(context)
                self._initialized.append(name)

                # Wire event handlers to EventBus
                for event_type, handler in plugin.get_event_handlers().items():
                    self._event_bus.subscribe(event_type, handler)

                logger.info(
                    "Plugin initialized",
                    plugin=name,
                    version=plugin.version,
                    commands=len(plugin.get_commands()),
                    event_handlers=len(plugin.get_event_handlers()),
                )
            except Exception as e:
                logger.error(
                    "Plugin setup failed",
                    plugin=name,
                    error=str(e),
                    exc_info=True,
                )
                raise PluginError(f"Plugin '{name}' setup failed: {e}") from e

    async def shutdown_all(self) -> None:
        """Call teardown() on all initialized plugins in reverse order."""
        for name in reversed(self._initialized):
            plugin = self._plugins.get(name)
            if plugin is None:
                continue

            try:
                await plugin.teardown()
                self._hook_manager.unregister_plugin_hooks(name)
                logger.info("Plugin shut down", plugin=name)
            except Exception as e:
                logger.error(
                    "Plugin teardown failed",
                    plugin=name,
                    error=str(e),
                    exc_info=True,
                )

        self._initialized.clear()

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginMetadata]:
        """Return metadata for all registered plugins."""
        return [p.metadata for p in self._plugins.values()]

    def _resolve_dependency_order(self) -> List[str]:
        """Topological sort of plugins by dependencies.

        Returns:
            List of plugin names in initialization order.

        Raises:
            PluginDependencyError: If there are missing or circular deps.
        """
        # Check all dependencies exist
        for name, plugin in self._plugins.items():
            for dep in plugin.dependencies:
                if dep not in self._plugins:
                    raise PluginDependencyError(
                        f"Plugin '{name}' requires '{dep}' which is not registered"
                    )

        # Kahn's algorithm for topological sort
        in_degree: Dict[str, int] = {name: 0 for name in self._plugins}
        for name, plugin in self._plugins.items():
            for dep in plugin.dependencies:
                in_degree[name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            # Find plugins that depend on this node
            for name, plugin in self._plugins.items():
                if node in plugin.dependencies:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)

        if len(result) != len(self._plugins):
            missing = set(self._plugins.keys()) - set(result)
            raise PluginDependencyError(
                f"Circular dependency detected among plugins: {missing}"
            )

        return result
