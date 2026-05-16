"""
tests/test_story_136_event_bus.py
==================================
Story 136 — MekkaEventBus: lightweight in-process pub/sub observability.

Testes isolados — sem dependências externas.
"""

from __future__ import annotations

import asyncio

import pytest

from src.services.event_bus import MekkaEventBus, get_event_bus, reset_event_bus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_bus():
    """Garante que o singleton está limpo antes e depois de cada teste."""
    reset_event_bus()
    yield
    reset_event_bus()


def fresh_bus() -> MekkaEventBus:
    return MekkaEventBus()


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------

class TestSubscription:
    def test_subscribe_increases_count(self):
        bus = fresh_bus()
        async def handler(e): pass
        bus.subscribe("test.event", handler)
        assert bus.subscriber_count("test.event") == 1

    def test_duplicate_subscribe_ignored(self):
        bus = fresh_bus()
        async def handler(e): pass
        bus.subscribe("test.event", handler)
        bus.subscribe("test.event", handler)
        assert bus.subscriber_count("test.event") == 1

    def test_unsubscribe_removes_handler(self):
        bus = fresh_bus()
        async def handler(e): pass
        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        assert bus.subscriber_count("test.event") == 0

    def test_unsubscribe_nonexistent_noop(self):
        bus = fresh_bus()
        async def handler(e): pass
        bus.unsubscribe("missing.topic", handler)  # should not raise

    def test_wildcard_subscribe(self):
        bus = fresh_bus()
        async def handler(e): pass
        bus.subscribe("*", handler)
        assert bus.subscriber_count("*") == 1

    def test_wildcard_duplicate_ignored(self):
        bus = fresh_bus()
        async def handler(e): pass
        bus.subscribe("*", handler)
        bus.subscribe("*", handler)
        assert bus.subscriber_count("*") == 1


# ---------------------------------------------------------------------------
# publish — basic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPublish:
    async def test_publish_calls_handler(self):
        bus = fresh_bus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("vision.signal", handler)
        await bus.publish("vision.signal", {"action": "LONG", "confidence": 0.8})

        assert len(received) == 1
        assert received[0]["action"] == "LONG"

    async def test_publish_injects_topic(self):
        bus = fresh_bus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("cycle.start", handler)
        await bus.publish("cycle.start", {"symbol": "BTC"})

        assert received[0]["topic"] == "cycle.start"

    async def test_publish_no_subscribers_returns_zero(self):
        bus = fresh_bus()
        count = await bus.publish("orphan.topic", {"x": 1})
        assert count == 0

    async def test_publish_returns_success_count(self):
        bus = fresh_bus()

        async def h1(e): pass
        async def h2(e): pass

        bus.subscribe("t", h1)
        bus.subscribe("t", h2)
        count = await bus.publish("t", {})
        assert count == 2

    async def test_publish_increments_counter(self):
        bus = fresh_bus()
        await bus.publish("test.topic", {})
        await bus.publish("test.topic", {})
        assert bus.event_count("test.topic") == 2

    async def test_publish_sync_callable(self):
        """Handler síncrono também deve funcionar."""
        bus = fresh_bus()
        received = []

        def sync_handler(event):
            received.append(event["topic"])

        bus.subscribe("sync.test", sync_handler)
        await bus.publish("sync.test", {})

        assert received == ["sync.test"]


# ---------------------------------------------------------------------------
# publish — wildcard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWildcard:
    async def test_wildcard_receives_all_topics(self):
        bus = fresh_bus()
        received_topics = []

        async def wildcard(event):
            received_topics.append(event["topic"])

        bus.subscribe("*", wildcard)

        await bus.publish("topic.a", {})
        await bus.publish("topic.b", {})
        await bus.publish("topic.c", {})

        assert sorted(received_topics) == ["topic.a", "topic.b", "topic.c"]

    async def test_wildcard_plus_specific_both_called(self):
        bus = fresh_bus()
        calls = []

        async def specific(e): calls.append("specific")
        async def wildcard(e): calls.append("wildcard")

        bus.subscribe("event.x", specific)
        bus.subscribe("*", wildcard)

        await bus.publish("event.x", {})

        assert "specific" in calls
        assert "wildcard" in calls


# ---------------------------------------------------------------------------
# publish — fail-silent on handler error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFailSilent:
    async def test_handler_error_does_not_propagate(self):
        bus = fresh_bus()

        async def bad_handler(event):
            raise ValueError("boom")

        bus.subscribe("risky.topic", bad_handler)
        # Should not raise
        count = await bus.publish("risky.topic", {"x": 1})
        # Error → 0 successful
        assert count == 0

    async def test_one_handler_error_others_still_called(self):
        bus = fresh_bus()
        received = []

        async def bad(e): raise RuntimeError("fail")
        async def good(e): received.append(True)

        bus.subscribe("mixed", bad)
        bus.subscribe("mixed", good)

        count = await bus.publish("mixed", {})
        assert count == 1  # good handler succeeded
        assert received == [True]


# ---------------------------------------------------------------------------
# Metrics and management
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_topics_after_publish(self):
        async def run():
            bus = fresh_bus()
            await bus.publish("a", {})
            await bus.publish("b", {})
            return bus.topics()
        topics = asyncio.get_event_loop().run_until_complete(run())
        assert set(topics) == {"a", "b"}

    def test_reset_counters(self):
        async def run():
            bus = fresh_bus()
            await bus.publish("x", {})
            await bus.publish("x", {})
            bus.reset_counters()
            return bus.event_count("x")
        count = asyncio.get_event_loop().run_until_complete(run())
        assert count == 0

    def test_clear_removes_subscribers_and_counters(self):
        async def run():
            bus = fresh_bus()
            async def h(e): pass
            bus.subscribe("t", h)
            await bus.publish("t", {})
            bus.clear()
            return bus.subscriber_count("t"), bus.event_count("t")
        sc, ec = asyncio.get_event_loop().run_until_complete(run())
        assert sc == 0
        assert ec == 0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_event_bus_returns_same_instance(self):
        reset_event_bus()
        b1 = get_event_bus()
        b2 = get_event_bus()
        assert b1 is b2

    def test_reset_event_bus_creates_new_instance(self):
        reset_event_bus()
        b1 = get_event_bus()
        reset_event_bus()
        b2 = get_event_bus()
        assert b1 is not b2


# ---------------------------------------------------------------------------
# Standard event topics present in docstring
# ---------------------------------------------------------------------------

class TestConventionalTopics:
    def test_standard_topics_documented(self):
        from src.services.event_bus import __doc__ as doc
        topics = ["cycle.start", "cycle.end", "vision.signal",
                  "batman.gate", "ironman.exec", "agent.error"]
        for topic in topics:
            assert topic in doc, f"Topic '{topic}' missing from module docstring"
