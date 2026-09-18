"""In-process publish/subscribe event bus with queued (FIFO) dispatch.

Design: Approach B. ``publish`` enqueues the event and returns immediately;
``flush`` drains the queue, including any events published by handlers while
draining. Handlers therefore never run re-entrantly and stack depth stays
bounded regardless of how deeply handlers chain publishes.

Topics
------
A subscription topic is either an exact topic name or a wildcard of the form
``"<prefix>.*"``, which matches every topic beginning with ``"<prefix>."``
(so ``"orders.*"`` matches ``"orders.created"`` and ``"orders.a.b"`` but not
``"orders"`` or ``"ordersx"``). Exact and wildcard subscriptions both receive
a matching event, in overall subscription order.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
Unsubscribe = Callable[[], None]
ErrorCallback = Callable[[str, Any, BaseException], Any]

_WILDCARD_SUFFIX = ".*"


@dataclass(frozen=True)
class _Subscription:
    pattern: str
    handler: Handler
    priority: int = 0

    def matches(self, topic: str) -> bool:
        if self.pattern.endswith(_WILDCARD_SUFFIX):
            prefix = self.pattern[: -len(_WILDCARD_SUFFIX) + 1]  # keep the dot
            return topic.startswith(prefix)
        return topic == self.pattern


class EventBus:
    def __init__(self) -> None:
        # All subscriptions, in subscription order.
        self._subscriptions: list[_Subscription] = []
        self._queue: deque[tuple[str, Any]] = deque()
        self._flushing = False
        self._error_callbacks: list[ErrorCallback] = []
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Unsubscribe:
        """Register ``handler`` for ``topic`` (exact or ``"prefix.*"`` wildcard).

        For a given published topic, matching handlers run in descending
        ``priority``; handlers with equal priority run in subscription order.
        Returns an unsubscribe function; calling it more than once is a no-op.
        """
        sub = _Subscription(topic, handler, priority)
        self._subscriptions.append(sub)

        def unsubscribe() -> None:
            # Remove by identity so equal (pattern, handler) pairs subscribed
            # twice are removed one at a time.
            for i, existing in enumerate(self._subscriptions):
                if existing is sub:
                    del self._subscriptions[i]
                    return

        return unsubscribe

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Unsubscribe:
        """Like ``subscribe`` but the handler is removed after its first call.

        The handler is unsubscribed *before* it runs, so it never fires twice
        even if it raises or re-publishes its own topic. Returns an unsubscribe
        function usable to cancel it before it fires.
        """
        unsubscribe: Unsubscribe

        def wrapper(t: str, p: Any) -> None:
            unsubscribe()
            handler(t, p)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed with exactly this topic string.

        Matching is literal: ``unsubscribe_all("orders.*")`` removes the
        wildcard subscriptions registered under that pattern, not the exact
        subscriptions for ``"orders.created"`` and the like.
        """
        self._subscriptions = [s for s in self._subscriptions if s.pattern != topic]

    def on_error(self, callback: ErrorCallback) -> Callable[[], None]:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        While at least one error callback is registered, an exception raised by
        a handler is passed to every callback and the remaining handlers for
        that event still run. With no callback registered, the exception
        propagates out of ``flush()``. Returns a function that removes the
        callback again.
        """
        self._error_callbacks.append(callback)

        def remove() -> None:
            for i, existing in enumerate(self._error_callbacks):
                if existing is callback:
                    del self._error_callbacks[i]
                    return

        return remove

    def stats(self) -> dict[str, Any]:
        """Return counters: events published, handler invocations, and
        published events per topic. The result is a snapshot copy."""
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    def publish(self, topic: str, payload: Any) -> None:
        """Enqueue an event. Handlers run on the next ``flush``."""
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        self._queue.append((topic, payload))

    def flush(self) -> None:
        """Handle every queued event in publish order.

        Events published by handlers during the flush are appended to the queue
        and handled after the current event's handlers finish. A nested call to
        ``flush`` from inside a handler returns immediately; the outer flush
        will drain everything.

        If a handler raises and no error callback is registered, the exception
        propagates out of this call. The failing event is already dequeued, so
        its remaining handlers are skipped; events still in the queue are left
        in place and handled by the next ``flush``.
        """
        if self._flushing:
            return
        self._flushing = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                self._dispatch(topic, payload)
        finally:
            self._flushing = False

    def _dispatch(self, topic: str, payload: Any) -> None:
        # Snapshot so (un)subscribes during dispatch don't affect this event.
        # The list is in subscription order and sort() is stable, so ties on
        # priority keep subscription order.
        matching = [s for s in self._subscriptions if s.matches(topic)]
        matching.sort(key=lambda s: s.priority, reverse=True)
        for sub in matching:
            self._handled += 1
            try:
                sub.handler(topic, payload)
            except Exception as exc:
                if not self._error_callbacks:
                    raise
                for callback in list(self._error_callbacks):
                    callback(topic, payload, exc)
