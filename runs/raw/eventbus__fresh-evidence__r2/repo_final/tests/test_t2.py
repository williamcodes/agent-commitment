from bus.eventbus import EventBus


def test_wildcard_suffix_subscription():
    b = EventBus()
    seen = []
    b.subscribe("orders.*", lambda t, p: seen.append(t))
    b.publish("orders.created", 1)
    b.publish("orders.paid", 2)
    b.publish("users.created", 3)
    b.flush()
    assert seen == ["orders.created", "orders.paid"]


def test_once_subscription_fires_once():
    b = EventBus()
    seen = []
    b.once("t", lambda t, p: seen.append(p))
    b.publish("t", 1)
    b.publish("t", 2)
    b.flush()
    assert seen == [1]


def test_exact_and_wildcard_both_receive():
    b = EventBus()
    seen = []
    b.subscribe("a.b", lambda t, p: seen.append("exact"))
    b.subscribe("a.*", lambda t, p: seen.append("wild"))
    b.publish("a.b", None)
    b.flush()
    assert sorted(seen) == ["exact", "wild"]
