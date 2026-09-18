"""In-process publish/subscribe event bus (queued dispatch, Approach B).

``publish`` enqueues an event and returns immediately; ``flush`` drains the
FIFO queue, calling handlers in subscription order for each event in publish
order. Events published while draining are appended to the queue and handled
after the current event finishes, so handler execution is never re-entrant
and stack depth stays bounded regardless of how deep the publish chain goes.

Subscription topics ending in ``.*`` are wildcards: ``orders.*`` matches every
topic starting with ``orders.`` (``orders.created``, ``orders.paid``, ...).
Exact and wildcard subscribers both receive a matching event, interleaved in
overall subscription order. ``once`` registers a handler that unsubscribes
itself after its first invocation.

``subscribe(..., priority=n)`` orders handlers: for a given event, higher
priority handlers run first and ties keep subscription order (default
priority is 0). ``unsubscribe_all(topic)`` drops every handler registered
under exactly that topic string (so ``unsubscribe_all("orders.*")`` removes
the wildcard subscribers, not the ``orders.created`` ones).

Errors: if an error callback is registered via ``on_error``, a handler that
raises is reported as ``callback(topic, payload, exc)`` and the remaining
handlers for that event (and the remaining queued events) still run. Without
a callback the exception propagates out of ``flush``; the undelivered events
stay queued and are delivered by the next ``flush``.

``stats`` reports how many events were published (overall and per topic) and
how many handler invocations have been made.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, BaseException], Any]


class EventBus:
    def __init__(self) -> None:
        # topic -> list of (subscription id, priority, handler); lists preserve
        # subscription order
        self._subscribers: dict[str, list[tuple[int, int, Handler]]] = {}
        self._queue: deque[tuple[str, Any]] = deque()
        self._next_id = 0
        self._flushing = False
        self._error_callback: ErrorCallback | None = None
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``; returns a function that unsubscribes it.

        Higher ``priority`` handlers run before lower ones for the same event;
        equal priorities run in subscription order.
        """
        sub_id = self._next_id
        self._next_id += 1
        self._subscribers.setdefault(topic, []).append((sub_id, priority, handler))

        def unsubscribe() -> None:
            handlers = self._subscribers.get(topic)
            if not handlers:
                return
            # Build a new list rather than mutating in place so an unsubscribe
            # performed from inside a handler doesn't disturb the iteration in flush.
            remaining = [entry for entry in handlers if entry[0] != sub_id]
            if remaining:
                self._subscribers[topic] = remaining
            else:
                del self._subscribers[topic]

        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed to exactly ``topic`` (no wildcard matching)."""
        # pop rather than clear in place: flush iterates over a snapshot, so
        # this is safe to call from inside a handler.
        self._subscribers.pop(topic, None)

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe`` but the handler is removed after its first call."""
        fired = False

        def wrapper(t: str, payload: Any) -> None:
            nonlocal fired
            if fired:
                return
            fired = True
            unsubscribe()
            handler(t, payload)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def on_error(self, callback: ErrorCallback | None) -> None:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        While a callback is registered, a raising handler no longer aborts
        delivery: the exception is passed to the callback and dispatch
        continues with the next handler. Pass ``None`` to clear it.
        """
        self._error_callback = callback

    def stats(self) -> dict[str, Any]:
        """Counters: events published (total and per topic) and handler invocations."""
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        if pattern == topic:
            return True
        return pattern.endswith(".*") and topic.startswith(pattern[:-1])

    def _handlers_for(self, topic: str) -> list[Handler]:
        """Snapshot of every handler whose subscription matches ``topic``.

        Ordered by descending priority, then subscription order.
        """
        matched: list[tuple[int, int, Handler]] = []
        for pattern, entries in self._subscribers.items():
            if self._matches(pattern, topic):
                matched.extend(entries)
        matched.sort(key=lambda entry: (-entry[1], entry[0]))
        return [handler for _, _, handler in matched]

    def publish(self, topic: str, payload: Any) -> None:
        """Queue an event; it is delivered on the next ``flush``."""
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        self._queue.append((topic, payload))

    def flush(self) -> None:
        """Deliver every queued event, including ones published while draining."""
        if self._flushing:
            # A handler called flush(); the outer flush loop will pick up
            # anything it published, so there is nothing extra to do here.
            return
        self._flushing = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                # _handlers_for returns a fresh list, so subscribe/unsubscribe
                # inside a handler can't affect which handlers see this event.
                for handler in self._handlers_for(topic):
                    self._handled += 1
                    try:
                        handler(topic, payload)
                    except Exception as exc:
                        if self._error_callback is None:
                            raise
                        self._error_callback(topic, payload, exc)
        finally:
            self._flushing = False
