"""Plugin system for extending bot functionality."""

from .base import Plugin, PluginContext, PluginMetadata
from .hooks import HookManager, HookPoint
from .loader import PluginManager

__all__ = [
    "Plugin",
    "PluginContext",
    "PluginMetadata",
    "PluginManager",
    "HookManager",
    "HookPoint",
]
