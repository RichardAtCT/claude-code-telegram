"""Tests for the event bus."""

import asyncio
from dataclasses import dataclass

import pytest

from src.events.bus import Event, EventBus


@dataclass
class TestEvent(Event):
    """Test event subclass."""

    data: str = ""
    source: str = "test"


@dataclass
class OtherEvent(Event):
    """Another test event subclass."""

    value: int = 0
    source: str = "test"


class TestEventBus:
    """Tests for EventBus."""

    async def test_publish_and_subscribe(self) -> None:
        """Events are delivered to matching handlers."""
        bus = EventBus()
        received = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe(TestEvent, handler)
        await bus.start()

        event = TestEvent(data="hello")
        await bus.publish(event)

        # Give the processor time to dispatch
        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 1
        assert isinstance(received[0], TestEvent)
        assert received[0].data == "hello"

    async def test_handler_receives_only_subscribed_type(self) -> None:
        """Handler only receives events of the subscribed type."""
        bus = EventBus()
        received_test = []
        received_other = []

        async def test_handler(event: Event) -> None:
            received_test.append(event)

        async def other_handler(event: Event) -> None:
            received_other.append(event)

        bus.subscribe(TestEvent, test_handler)
        bus.subscribe(OtherEvent, other_handler)
        await bus.start()

        await bus.publish(TestEvent(data="a"))
        await bus.publish(OtherEvent(value=42))

        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received_test) == 1
        assert len(received_other) == 1
        assert received_test[0].data == "a"
        assert received_other[0].value == 42

    async def test_global_handler_receives_all(self) -> None:
        """Global handlers receive every event."""
        bus = EventBus()
        received = []

        async def global_handler(event: Event) -> None:
            received.append(event)

        bus.subscribe_all(global_handler)
        await bus.start()

        await bus.publish(TestEvent(data="x"))
        await bus.publish(OtherEvent(value=1))

        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received) == 2

    async def test_handler_error_does_not_crash_bus(self) -> None:
        """A failing handler doesn't prevent other handlers from running."""
        bus = EventBus()
        received = []

        async def bad_handler(event: Event) -> None:
            raise RuntimeError("boom")

        async def good_handler(event: Event) -> None:
            received.append(event)

        bus.subscribe(TestEvent, bad_handler)
        bus.subscribe(TestEvent, good_handler)
        await bus.start()

        await bus.publish(TestEvent(data="test"))
        await asyncio.sleep(0.1)
        await bus.stop()

        # Good handler still receives the event
        assert len(received) == 1

    async def test_event_has_id_and_timestamp(self) -> None:
        """Events get auto-generated ID and timestamp."""
        event = TestEvent(data="hi")
        assert event.id
        assert event.timestamp
        assert event.event_type == "TestEvent"

    async def test_multiple_handlers_for_same_type(self) -> None:
        """Multiple handlers can subscribe to the same event type."""
        bus = EventBus()
        results = []

        async def handler_a(event: Event) -> None:
            results.append("a")

        async def handler_b(event: Event) -> None:
            results.append("b")

        bus.subscribe(TestEvent, handler_a)
        bus.subscribe(TestEvent, handler_b)
        await bus.start()

        await bus.publish(TestEvent())
        await asyncio.sleep(0.1)
        await bus.stop()

        assert "a" in results
        assert "b" in results

    async def test_stop_is_idempotent(self) -> None:
        """Stopping an already stopped bus doesn't raise."""
        bus = EventBus()
        await bus.start()
        await bus.stop()
        await bus.stop()  # Should not raise
