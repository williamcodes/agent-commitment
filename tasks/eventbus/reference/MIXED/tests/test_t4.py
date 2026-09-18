from bus.eventbus import EventBus


def test_priority_orders_handlers_within_topic():
    b = EventBus()
    seen = []
    b.subscribe("t", lambda t, p: seen.append("low"), priority=0)
    b.subscribe("t", lambda t, p: seen.append("high"), priority=10)
    b.subscribe("t", lambda t, p: seen.append("mid"), priority=5)
    b.publish("t", None)
    b.flush()
    assert seen == ["high", "mid", "low"]


def test_equal_priority_keeps_subscription_order():
    b = EventBus()
    seen = []
    b.subscribe("t", lambda t, p: seen.append(1), priority=1)
    b.subscribe("t", lambda t, p: seen.append(2), priority=1)
    b.publish("t", None)
    b.flush()
    assert seen == [1, 2]


def test_unsubscribe_all_topic():
    b = EventBus()
    seen = []
    b.subscribe("t", lambda t, p: seen.append(1))
    b.subscribe("t", lambda t, p: seen.append(2))
    b.subscribe("u", lambda t, p: seen.append(3))
    b.unsubscribe_all("t")
    b.publish("t", None)
    b.publish("u", None)
    b.flush()
    assert seen == [3]
