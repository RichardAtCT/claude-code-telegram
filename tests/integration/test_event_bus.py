"""Integration tests for the EventBus.

Verifies publish/subscribe, multiple subscribers, error isolation,
and typed event routing using real asyncio tasks.
"""

import asyncio
from dataclasses import dataclass

import pytest

from src.events.bus import Event, EventBus


@dataclass
class AlphaEvent(Event):
    """Test event type A."""
    value: str = ""
    source: str = "test"


@dataclass
class BetaEvent(Event):
    """Test event type B."""
    number: int = 0
    source: str = "test"


class TestPublishSubscribe:
    """Basic publish and subscribe."""

    async def test_handler_receives_event(self, event_bus: EventBus):
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(AlphaEvent, handler)
        await event_bus.start()

        try:
            await event_bus.publish(AlphaEvent(value="hello"))
            # Allow the processor task to run
            await asyncio.sleep(0.1)
        finally:
            await event_bus.stop()

        assert len(received) == 1
        assert isinstance(received[0], AlphaEvent)
        assert received[0].value == "hello"

    async def test_no_handler_no_error(self, event_bus: EventBus):
        """Publishing with no subscribers should not raise."""
        await event_bus.start()
        try:
            await event_bus.publish(AlphaEvent(value="ignored"))
            await asyncio.sleep(0.1)
        finally:
            await event_bus.stop()


class TestMultipleSubscribers:
    """Multiple handlers for the same event type."""

    async def test_all_handlers_called(self, event_bus: EventBus):
        results: list[str] = []

        async def handler_a(event: Event) -> None:
            results.append("a")

        async def handler_b(event: Event) -> None:
            results.append("b")

        event_bus.subscribe(AlphaEvent, handler_a)
        event_bus.subscribe(AlphaEvent, handler_b)
        await event_bus.start()

        try:
            await event_bus.publish(AlphaEvent(value="multi"))
            await asyncio.sleep(0.1)
        finally:
            await event_bus.stop()

        assert "a" in results
        assert "b" in results
        assert len(results) == 2

    async def test_global_handler_receives_all(self, event_bus: EventBus):
        received: list[str] = []

        async def global_handler(event: Event) -> None:
            received.append(event.event_type)

        event_bus.subscribe_all(global_handler)
        await event_bus.start()

        try:
            await event_bus.publish(AlphaEvent(value="x"))
            await event_bus.publish(BetaEvent(number=1))
            await asyncio.sleep(0.2)
        finally:
            await event_bus.stop()

        assert "AlphaEvent" in received
        assert "BetaEvent" in received


class TestErrorIsolation:
    """One handler's error must not prevent others from running."""

    async def test_error_does_not_block_sibling(self, event_bus: EventBus):
        results: list[str] = []

        async def bad_handler(event: Event) -> None:
            raise RuntimeError("boom")

        async def good_handler(event: Event) -> None:
            results.append("ok")

        event_bus.subscribe(AlphaEvent, bad_handler)
        event_bus.subscribe(AlphaEvent, good_handler)
        await event_bus.start()

        try:
            await event_bus.publish(AlphaEvent(value="test"))
            await asyncio.sleep(0.1)
        finally:
            await event_bus.stop()

        # The good handler must have run despite the bad one failing
        assert "ok" in results


class TestTypedSubscriptions:
    """Handlers only receive events of their subscribed type."""

    async def test_type_routing(self, event_bus: EventBus):
        alpha_received: list[Event] = []
        beta_received: list[Event] = []

        async def alpha_handler(event: Event) -> None:
            alpha_received.append(event)

        async def beta_handler(event: Event) -> None:
            beta_received.append(event)

        event_bus.subscribe(AlphaEvent, alpha_handler)
        event_bus.subscribe(BetaEvent, beta_handler)
        await event_bus.start()

        try:
            await event_bus.publish(AlphaEvent(value="a1"))
            await event_bus.publish(BetaEvent(number=42))
            await event_bus.publish(AlphaEvent(value="a2"))
            await asyncio.sleep(0.2)
        finally:
            await event_bus.stop()

        assert len(alpha_received) == 2
        assert len(beta_received) == 1
        assert all(isinstance(e, AlphaEvent) for e in alpha_received)
        assert isinstance(beta_received[0], BetaEvent)
        assert beta_received[0].number == 42

    async def test_base_event_subscription_receives_all(self, event_bus: EventBus):
        """Subscribing to the base Event class should receive all subtypes."""
        received: list[Event] = []

        async def catch_all(event: Event) -> None:
            received.append(event)

        event_bus.subscribe(Event, catch_all)
        await event_bus.start()

        try:
            await event_bus.publish(AlphaEvent(value="x"))
            await event_bus.publish(BetaEvent(number=7))
            await asyncio.sleep(0.2)
        finally:
            await event_bus.stop()

        assert len(received) == 2
