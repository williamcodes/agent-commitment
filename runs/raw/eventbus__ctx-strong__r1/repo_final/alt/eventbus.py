"""In-process event bus, Approach A: synchronous dispatch.

`publish` calls the matching handlers immediately, before returning. `flush` is a no-op
kept for interface compatibility.
"""
from __future__ import annotations


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

    def flush(self) -> None:
        """No-op: every event was already handled inside publish()."""
        return None

    def stats(self) -> dict:
        return {"published": self._published, "handled": self._handled, "by_topic": dict(self._by_topic)}
