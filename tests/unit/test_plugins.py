"""Tests for the plugin system: base, hooks, loader."""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.plugins.base import Plugin, PluginContext, PluginMetadata
from src.plugins.hooks import HookManager, HookPoint
from src.plugins.loader import PluginError, PluginManager


# ---------------------------------------------------------------------------
# Plugin ABC compliance
# ---------------------------------------------------------------------------


class _ValidPlugin(Plugin):
    @property
    def name(self) -> str:
        return "valid"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def setup(self, context: PluginContext) -> None:
        pass


class _IncompletePlugin(Plugin):
    """Missing required abstract properties/methods."""
    pass


def test_plugin_abc_compliance():
    """A concrete plugin implementing all abstract members is instantiable."""
    p = _ValidPlugin()
    assert p.name == "valid"
    assert p.version == "1.0.0"


def test_plugin_abc_rejects_incomplete():
    with pytest.raises(TypeError):
        _IncompletePlugin()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# PluginMetadata
# ---------------------------------------------------------------------------


def test_plugin_metadata_creation():
    meta = PluginMetadata(
        name="test",
        version="2.0.0",
        description="A test plugin",
        author="tester",
        dependencies=["dep1"],
    )
    assert meta.name == "test"
    assert meta.dependencies == ["dep1"]


def test_plugin_metadata_from_plugin():
    p = _ValidPlugin()
    meta = p.metadata
    assert meta.name == "valid"
    assert meta.version == "1.0.0"
    assert meta.dependencies == []


# ---------------------------------------------------------------------------
# PluginContext
# ---------------------------------------------------------------------------


def test_plugin_context_creation():
    ctx = PluginContext(
        bot=MagicMock(),
        event_bus=MagicMock(),
        storage=None,
        settings=MagicMock(),
        logger=MagicMock(),
    )
    assert ctx.storage is None


# ---------------------------------------------------------------------------
# HookManager
# ---------------------------------------------------------------------------


@pytest.fixture
def hook_manager():
    return HookManager()


@pytest.mark.asyncio
async def test_register_and_execute_hook(hook_manager):
    callback = AsyncMock(return_value=None)
    hook_manager.register_hook(HookPoint.PRE_MESSAGE, "test_plugin", callback)

    ctx = {"message": "hello"}
    result = await hook_manager.execute_hooks(HookPoint.PRE_MESSAGE, ctx)

    callback.assert_awaited_once_with(ctx)
    assert result == ctx  # callback returned None => pass-through


@pytest.mark.asyncio
async def test_hooks_execute_in_priority_order(hook_manager):
    order = []

    async def hook_a(ctx):
        order.append("a")
        return None

    async def hook_b(ctx):
        order.append("b")
        return None

    hook_manager.register_hook(HookPoint.PRE_MESSAGE, "plugin_b", hook_b, priority=10)
    hook_manager.register_hook(HookPoint.PRE_MESSAGE, "plugin_a", hook_a, priority=1)

    await hook_manager.execute_hooks(HookPoint.PRE_MESSAGE, {})
    assert order == ["a", "b"]


@pytest.mark.asyncio
async def test_hook_error_propagates(hook_manager):
    """A hook that raises should propagate to the caller."""

    async def bad_hook(ctx):
        raise ValueError("boom")

    hook_manager.register_hook(HookPoint.ON_ERROR, "bad", bad_hook)

    with pytest.raises(ValueError, match="boom"):
        await hook_manager.execute_hooks(HookPoint.ON_ERROR, {})


def test_hook_count(hook_manager):
    hook_manager.register_hook(HookPoint.PRE_MESSAGE, "p1", AsyncMock(), priority=0)
    hook_manager.register_hook(HookPoint.POST_MESSAGE, "p2", AsyncMock(), priority=0)

    assert hook_manager.get_hook_count(HookPoint.PRE_MESSAGE) == 1
    assert hook_manager.get_hook_count() == 2


def test_unregister_plugin_hooks(hook_manager):
    hook_manager.register_hook(HookPoint.PRE_MESSAGE, "p1", AsyncMock())
    hook_manager.register_hook(HookPoint.PRE_MESSAGE, "p2", AsyncMock())

    removed = hook_manager.unregister_plugin_hooks("p1")
    assert removed == 1
    assert hook_manager.get_hook_count(HookPoint.PRE_MESSAGE) == 1


# ---------------------------------------------------------------------------
# PluginManager: register / list / get
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin_manager():
    event_bus = MagicMock()
    hook_mgr = HookManager()
    return PluginManager(event_bus, hook_mgr)


def test_register_and_get_plugin(plugin_manager):
    p = _ValidPlugin()
    plugin_manager.register_plugin(p)

    assert plugin_manager.get_plugin("valid") is p


def test_list_plugins(plugin_manager):
    plugin_manager.register_plugin(_ValidPlugin())
    metas = plugin_manager.list_plugins()
    assert len(metas) == 1
    assert metas[0].name == "valid"


def test_register_duplicate_raises(plugin_manager):
    plugin_manager.register_plugin(_ValidPlugin())
    with pytest.raises(PluginError, match="already registered"):
        plugin_manager.register_plugin(_ValidPlugin())


def test_get_missing_plugin_returns_none(plugin_manager):
    assert plugin_manager.get_plugin("nope") is None
