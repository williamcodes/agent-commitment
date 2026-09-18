"""In-process publish/subscribe event bus (queued dispatch, Approach B).

``publish`` enqueues events; ``flush`` drains the queue in FIFO order and
invokes handlers. Events published while draining are appended to the queue
and handled after the current event finishes, so handlers never re-enter
each other and stack depth stays bounded.

Subscriptions:

* An exact topic (``"orders.created"``) matches only that topic.
* A wildcard topic ending in ``.*`` (``"orders.*"``) matches every topic that
  starts with the prefix up to and including the dot (``"orders.created"``,
  ``"orders.paid"``, ``"orders.a.b"``), but not the bare prefix ``"orders"``.
* When several subscriptions match one event, their handlers run in
  descending ``priority`` order; ties keep overall subscription order,
  regardless of whether a subscription is exact or wildcard.
* ``once`` registers a handler that is removed just before its first call.
* ``unsubscribe_all(topic)`` removes every subscription registered with exactly
  that topic string (so ``"orders.*"`` removes the wildcard subscriptions and
  leaves ``"orders.created"`` alone, and vice versa).

Errors and stats:

* ``on_error`` registers a callback ``(topic, payload, exc)``. When a handler
  raises and at least one error callback is registered, the exception is passed
  to every callback and the remaining handlers for the event still run. With no
  callback registered, the exception propagates out of ``flush``; events still
  in the queue stay there and are delivered by the next ``flush``.
* ``stats`` reports the number of events published, the number of handler
  invocations (a handler that raised still counts), and published events per topic.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, BaseException], Any]

WILDCARD_SUFFIX = ".*"


@dataclass(eq=False)
class _Subscription:
    topic: str
    handler: Handler
    once: bool
    priority: int
    seq: int
    table: dict[str, list["_Subscription"]]
    key: str
    active: bool = field(default=True)


class EventBus:
    def __init__(self) -> None:
        self._exact: dict[str, list[_Subscription]] = {}
        # Wildcard subscriptions keyed by prefix including the trailing dot,
        # e.g. "orders." for the pattern "orders.*".
        self._wildcards: dict[str, list[_Subscription]] = {}
        self._queue: deque[tuple[str, Any]] = deque()
        self._seq = count()
        self._flushing = False
        self._error_callbacks: list[ErrorCallback] = []
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    # ------------------------------------------------------------------ API

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``; return a function that removes it.

        ``topic`` may end in ``.*`` to match every topic under that prefix.
        Higher ``priority`` handlers run first; ties keep subscription order.
        """
        return self._add(topic, handler, once=False, priority=priority)

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe``, but the handler is removed after its first call."""
        return self._add(topic, handler, once=True, priority=priority)

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every subscription registered with exactly ``topic``."""
        table, key = self._locate(topic)
        for sub in list(table.get(key, ())):
            self._remove(sub)

    def publish(self, topic: str, payload: Any) -> None:
        """Enqueue an event. It is delivered on the next ``flush``."""
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        self._queue.append((topic, payload))

    def on_error(self, callback: ErrorCallback) -> Callable[[], None]:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        Returns a function that removes the callback again.
        """
        self._error_callbacks.append(callback)

        def remove() -> None:
            try:
                self._error_callbacks.remove(callback)
            except ValueError:
                pass

        return remove

    def stats(self) -> dict[str, Any]:
        """Counters: events published, handler invocations, published per topic."""
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    def flush(self) -> None:
        """Deliver every queued event, including ones published while draining."""
        if self._flushing:
            # A handler called flush(); the outer flush loop will drain the
            # newly queued events in order, so there is nothing more to do.
            return
        self._flushing = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                self._dispatch(topic, payload)
        finally:
            self._flushing = False

    # ------------------------------------------------------------ internals

    def _locate(self, topic: str) -> tuple[dict[str, list[_Subscription]], str]:
        """Return the (table, key) under which subscriptions to ``topic`` live."""
        if topic.endswith(WILDCARD_SUFFIX):
            return self._wildcards, topic[: -len(WILDCARD_SUFFIX) + 1]  # keep the dot
        return self._exact, topic

    def _add(
        self, topic: str, handler: Handler, *, once: bool, priority: int
    ) -> Callable[[], None]:
        table, key = self._locate(topic)
        sub = _Subscription(topic, handler, once, priority, next(self._seq), table, key)
        table.setdefault(key, []).append(sub)

        def unsubscribe() -> None:
            self._remove(sub)

        return unsubscribe

    @staticmethod
    def _remove(sub: _Subscription) -> None:
        if not sub.active:
            return
        sub.active = False
        subs = sub.table.get(sub.key)
        if subs is None:
            return
        try:
            subs.remove(sub)  # eq=False, so this is identity-based
        except ValueError:
            pass
        if not subs:
            sub.table.pop(sub.key, None)

    def _matching(self, topic: str) -> list[_Subscription]:
        """All live subscriptions matching ``topic``, highest priority first,
        ties in subscription order."""
        matches = list(self._exact.get(topic, ()))
        # Every prefix "a.", "a.b.", ... of the topic is a candidate wildcard key.
        if self._wildcards:
            for i, ch in enumerate(topic):
                if ch == "." and i + 1 < len(topic):
                    matches.extend(self._wildcards.get(topic[: i + 1], ()))
        matches.sort(key=lambda s: (-s.priority, s.seq))
        return matches

    def _dispatch(self, topic: str, payload: Any) -> None:
        # Snapshot so (un)subscribing inside a handler doesn't disturb this
        # event's delivery; skip entries unsubscribed mid-dispatch.
        for sub in self._matching(topic):
            if not sub.active:
                continue
            if sub.once:
                self._remove(sub)
            self._handled += 1
            try:
                sub.handler(topic, payload)
            except Exception as exc:
                if not self._error_callbacks:
                    raise
                for callback in list(self._error_callbacks):
                    callback(topic, payload, exc)
