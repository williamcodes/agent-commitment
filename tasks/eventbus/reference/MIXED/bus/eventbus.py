"""In-process event bus, deliberately MIXED reference (not a real design).

Both dispatch designs from SPEC.md are live at once for the same responsibility:

- Exact-topic subscriptions (`subscribe("orders.created", h)`) are dispatched synchronously,
  inside `publish()`, before it returns (Approach A).
- Wildcard subscriptions (`subscribe("orders.*", h)`) are matched lazily: `publish()` appends the
  event to a FIFO deque and the wildcard handlers only run when `flush()` drains it (Approach B).

This is the kind of thing a careless agent produces when it starts synchronous, then bolts the
wildcard feature on as a "pattern-matching queue" without reconciling the two paths. Tests only
observe state after flush(), so all four turns of tests pass.
"""
from __future__ import annotations

from collections import deque


class _Subscription:
    __slots__ = ("topic", "handler", "priority", "seq", "once", "active")

    def __init__(self, topic, handler, priority, seq, once):
        self.topic = topic
        self.handler = handler
        self.priority = priority
        self.seq = seq
        self.once = once
        self.active = True

    @property
    def is_pattern(self) -> bool:
        return self.topic.endswith(".*")

    def matches(self, topic: str) -> bool:
        if self.topic == topic:
            return True
        if self.is_pattern:
            return topic.startswith(self.topic[:-1])
        return False


class EventBus:
    def __init__(self):
        self._subs: list[_Subscription] = []
        self._seq = 0
        # queue of events awaiting wildcard (pattern) dispatch
        self._pending: deque[tuple[str, object]] = deque()
        self._draining = False
        self._error_callbacks = []
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    # --- subscriptions ---------------------------------------------------------
    def _add(self, topic, handler, priority, once):
        sub = _Subscription(topic, handler, priority, self._seq, once)
        self._seq += 1
        self._subs.append(sub)

        def unsubscribe():
            sub.active = False
            if sub in self._subs:
                self._subs.remove(sub)
        return unsubscribe

    def subscribe(self, topic: str, handler, priority: int = 0):
        return self._add(topic, handler, priority, once=False)

    def once(self, topic: str, handler, priority: int = 0):
        return self._add(topic, handler, priority, once=True)

    def unsubscribe_all(self, topic: str) -> None:
        for sub in self._subs:
            if sub.topic == topic:
                sub.active = False
        self._subs = [s for s in self._subs if s.topic != topic]

    def on_error(self, callback) -> None:
        self._error_callbacks.append(callback)

    # --- dispatch ----------------------------------------------------------------
    def publish(self, topic: str, payload) -> None:
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        # Approach A path: exact subscribers run right now.
        exact = [s for s in self._subs if not s.is_pattern and s.topic == topic]
        self._run(exact, topic, payload)
        # Approach B path: wildcard subscribers are resolved later, in flush().
        self._pending.append((topic, payload))

    def flush(self) -> None:
        if self._draining:
            return
        self._draining = True
        try:
            while self._pending:
                topic, payload = self._pending.popleft()
                patterns = [s for s in self._subs if s.is_pattern and s.matches(topic)]
                self._run(patterns, topic, payload)
        finally:
            self._draining = False

    def _run(self, subs, topic, payload) -> None:
        for sub in sorted(subs, key=lambda s: (-s.priority, s.seq)):
            if not sub.active:
                continue
            if sub.once:
                sub.active = False
                self._subs.remove(sub)
            self._handled += 1
            try:
                sub.handler(topic, payload)
            except Exception as exc:
                if not self._error_callbacks:
                    raise
                for cb in self._error_callbacks:
                    cb(topic, payload, exc)

    def stats(self) -> dict:
        return {"published": self._published, "handled": self._handled, "by_topic": dict(self._by_topic)}
