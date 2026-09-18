"""In-process event bus, Approach B: queued dispatch.

`publish` appends the event to a FIFO queue and returns. `flush` drains the queue in
publish order, including events published by handlers while draining, so handlers never
run re-entrantly and the stack depth is bounded.
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

    def matches(self, topic: str) -> bool:
        if self.topic == topic:
            return True
        if self.topic.endswith(".*"):
            return topic.startswith(self.topic[:-1])
        return False


class EventBus:
    def __init__(self):
        self._subs: list[_Subscription] = []
        self._seq = 0
        self._queue: deque[tuple[str, object]] = deque()
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
        self._queue.append((topic, payload))

    def flush(self) -> None:
        if self._draining:
            return
        self._draining = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                self._dispatch(topic, payload)
        finally:
            self._draining = False

    def _dispatch(self, topic, payload) -> None:
        matching = sorted((s for s in self._subs if s.matches(topic)), key=lambda s: (-s.priority, s.seq))
        for sub in matching:
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
