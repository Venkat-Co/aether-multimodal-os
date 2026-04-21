import pytest

from aether_core.event_bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_in_memory_event_bus_publishes_envelopes_to_subscribers() -> None:
    bus = InMemoryEventBus()
    await bus.connect()
    queue = await bus.subscribe("fusion")

    envelope = await bus.publish("fusion", {"event_id": "evt_123"}, source="unit-test")
    received = await queue.get()

    assert envelope.topic == "fusion"
    assert received.payload["event_id"] == "evt_123"
    assert received.source == "unit-test"
    await bus.close()
