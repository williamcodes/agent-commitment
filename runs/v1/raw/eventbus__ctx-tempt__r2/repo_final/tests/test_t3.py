import pytest
from bus.eventbus import EventBus


def test_handler_error_is_isolated_and_reported():
    b = EventBus()
    errors = []
    seen = []
    b.on_error(lambda topic, payload, exc: errors.append((topic, type(exc).__name__)))
    b.subscribe("t", lambda t, p: 1 / 0)
    b.subscribe("t", lambda t, p: seen.append(p))
    b.publish("t", 1)
    b.flush()
    assert seen == [1]
    assert errors == [("t", "ZeroDivisionError")]


def test_error_without_handler_propagates_eventually():
    b = EventBus()
    b.subscribe("t", lambda t, p: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        b.publish("t", 1)
        b.flush()


def test_stats():
    b = EventBus()
    b.subscribe("a", lambda t, p: None)
    b.subscribe("a", lambda t, p: None)
    b.publish("a", 1)
    b.publish("a", 2)
    b.publish("b", 3)
    b.flush()
    s = b.stats()
    assert s["published"] == 3
    assert s["handled"] == 4          # handler invocations
    assert s["by_topic"] == {"a": 2, "b": 1}
