from bus.eventbus import EventBus


def test_subscribe_publish_flush():
    b = EventBus()
    seen = []
    b.subscribe("greet", lambda t, p: seen.append((t, p)))
    b.publish("greet", "hi")
    b.publish("other", "ignored")
    b.flush()
    assert seen == [("greet", "hi")]


def test_handlers_run_in_subscription_order_and_publish_order():
    b = EventBus()
    seen = []
    b.subscribe("t", lambda t, p: seen.append(("h1", p)))
    b.subscribe("t", lambda t, p: seen.append(("h2", p)))
    b.publish("t", 1)
    b.publish("t", 2)
    b.flush()
    assert seen == [("h1", 1), ("h2", 1), ("h1", 2), ("h2", 2)]


def test_unsubscribe():
    b = EventBus()
    seen = []
    unsub = b.subscribe("t", lambda t, p: seen.append(p))
    b.publish("t", 1)
    b.flush()
    unsub()
    b.publish("t", 2)
    b.flush()
    assert seen == [1]


def test_handler_can_publish():
    b = EventBus()
    seen = []
    b.subscribe("a", lambda t, p: (seen.append("a"), b.publish("b", None)))
    b.subscribe("b", lambda t, p: seen.append("b"))
    b.publish("a", None)
    b.flush()
    assert seen == ["a", "b"]


def test_flush_idempotent_and_no_subscribers():
    b = EventBus()
    b.publish("nobody", 1)
    b.flush()
    b.flush()
