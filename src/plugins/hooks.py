"""Hook system for plugin pipeline interception.

Provides named hook points that plugins can register callbacks for.
Hooks run in registration order and can modify context or cancel
operations by raising exceptions.
"""

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# Type alias for async hook callbacks
HookCallback = Callable[[Dict[str, Any]], Coroutine[Any, Any, Optional[Dict[str, Any]]]]


class HookPoint(enum.Enum):
    """Named points in the processing pipeline where plugins can intercept."""

    PRE_MESSAGE = "pre_message"
    POST_MESSAGE = "post_message"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    ON_ERROR = "on_error"


@dataclass
class HookRegistration:
    """A single hook callback registration."""

    hook_point: HookPoint
    plugin_name: str
    callback: HookCallback
    priority: int = 0  # Lower runs first


class HookManager:
    """Manages hook registrations and execution.

    Hooks are async functions that receive a context dict and can:
    - Return None to pass through unchanged
    - Return a modified context dict
    - Raise an exception to cancel the operation
    """

    def __init__(self) -> None:
        self._hooks: Dict[HookPoint, List[HookRegistration]] = {
            point: [] for point in HookPoint
        }

    def register_hook(
        self,
        hook_point: HookPoint,
        plugin_name: str,
        callback: HookCallback,
        priority: int = 0,
    ) -> None:
        """Register a hook callback at the specified hook point.

        Args:
            hook_point: Where in the pipeline to intercept.
            plugin_name: Name of the plugin registering the hook.
            callback: Async function(context) -> optional modified context.
            priority: Lower values run first. Default 0.
        """
        registration = HookRegistration(
            hook_point=hook_point,
            plugin_name=plugin_name,
            callback=callback,
            priority=priority,
        )
        self._hooks[hook_point].append(registration)
        # Keep sorted by priority
        self._hooks[hook_point].sort(key=lambda r: r.priority)

        logger.debug(
            "Hook registered",
            hook_point=hook_point.value,
            plugin=plugin_name,
            priority=priority,
        )

    def unregister_plugin_hooks(self, plugin_name: str) -> int:
        """Remove all hooks for a plugin. Returns count removed."""
        total_removed = 0
        for point in HookPoint:
            before = len(self._hooks[point])
            self._hooks[point] = [
                r for r in self._hooks[point] if r.plugin_name != plugin_name
            ]
            total_removed += before - len(self._hooks[point])
        return total_removed

    async def execute_hooks(
        self,
        hook_point: HookPoint,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute all hooks at the given point, passing context through the chain.

        Each hook can modify and return the context. If a hook returns None,
        the context passes through unchanged. If a hook raises an exception,
        it propagates up to cancel the operation.

        Args:
            hook_point: Which pipeline point to execute.
            context: Mutable context dict passed through the chain.

        Returns:
            The (possibly modified) context dict.

        Raises:
            Any exception raised by a hook callback.
        """
        registrations = self._hooks.get(hook_point, [])
        if not registrations:
            return context

        current_context = context
        for reg in registrations:
            try:
                result = await reg.callback(current_context)
                if result is not None:
                    current_context = result
            except Exception:
                logger.error(
                    "Hook raised exception, cancelling operation",
                    hook_point=hook_point.value,
                    plugin=reg.plugin_name,
                    exc_info=True,
                )
                raise

        return current_context

    def get_hook_count(self, hook_point: Optional[HookPoint] = None) -> int:
        """Return number of registered hooks, optionally filtered by point."""
        if hook_point is not None:
            return len(self._hooks.get(hook_point, []))
        return sum(len(hooks) for hooks in self._hooks.values())
