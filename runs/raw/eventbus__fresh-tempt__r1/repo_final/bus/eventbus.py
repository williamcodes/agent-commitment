"""In-process publish/subscribe event bus with queued (FIFO) dispatch.

Design: Approach B from SPEC.md. ``publish`` only enqueues; ``flush`` drains
the queue in publish order, including events published by handlers while
draining. Handlers therefore never run re-entrantly and stack depth stays
bounded regardless of how deeply events cascade.

Topics: a subscription topic ending in ``.*`` is a wildcard that matches any
published topic sharing the prefix before the dot (``orders.*`` matches
``orders.created``). Exact subscribers run first (in subscription order),
then wildcard subscribers. ``once`` registers a handler that is removed
after its first invocation.

Priority: ``subscribe(..., priority=n)`` orders handlers within a topic so
that higher priorities run first; equal priorities keep subscription order.
``unsubscribe_all(topic)`` drops every handler registered under exactly that
topic string (a wildcard pattern counts as its own topic string).

Errors: if a handler raises and an error callback is registered via
``on_error``, the callback receives ``(topic, payload, exc)`` and dispatch
continues with the remaining handlers. Without a callback the exception
propagates out of ``flush`` (the remaining queued events stay queued for a
later ``flush``).

Stats: ``stats()`` reports the number of events published, the number of
handler invocations (including ones that raised), and published counts per
topic.
"""

from collections import deque
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, BaseException], Any]


class EventBus:
    def __init__(self) -> None:
        # topic -> [(priority, handler), ...], sorted by descending priority;
        # ties keep subscription order.
        self._handlers: dict[str, list[tuple[int, Handler]]] = {}
        self._queue: deque[tuple[str, Any]] = deque()
        self._flushing = False
        self._error_callback: ErrorCallback | None = None
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``; returns an unsubscribe function.

        Within a topic, handlers with a higher ``priority`` run first; handlers
        with equal priority run in subscription order.
        """
        handlers = self._handlers.setdefault(topic, [])
        entry = (priority, handler)
        # Insert after every existing entry with priority >= ours, so the list
        # stays sorted by descending priority and ties keep insertion order.
        index = len(handlers)
        while index > 0 and handlers[index - 1][0] < priority:
            index -= 1
        handlers.insert(index, entry)

        def unsubscribe() -> None:
            # Identity match on the tuple so two subscriptions of the same
            # handler object at the same priority are removed one at a time.
            for i, existing in enumerate(handlers):
                if existing is entry:
                    del handlers[i]
                    return
            # already unsubscribed (or removed by unsubscribe_all); idempotent

        return unsubscribe

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe``, but the handler is removed after its first call."""
        def wrapper(t: str, payload: Any) -> Any:
            unsubscribe()
            return handler(t, payload)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed to exactly ``topic``.

        Only the literal topic string is matched: ``unsubscribe_all("a.b")``
        does not touch ``"a.*"`` subscribers, and vice versa. The list is
        cleared in place so an in-progress ``flush`` (which snapshots the
        handler list per event) is unaffected.
        """
        handlers = self._handlers.get(topic)
        if handlers is not None:
            handlers.clear()

    def _matching_handlers(self, topic: str) -> list[Handler]:
        """Exact-topic handlers followed by handlers of any matching wildcard.

        Each group is already ordered by descending priority.
        """
        matched = [h for _, h in self._handlers.get(topic, ())]
        # Most specific wildcard first: "a.b.*" before "a.*" for topic "a.b.c".
        dot = topic.rfind(".")
        while dot != -1:
            matched.extend(h for _, h in self._handlers.get(topic[:dot] + ".*", ()))
            dot = topic.rfind(".", 0, dot)
        return matched

    def on_error(self, callback: ErrorCallback | None) -> None:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        While a callback is registered, a raising handler does not stop the
        remaining handlers for that event. Pass ``None`` to remove it.
        """
        self._error_callback = callback

    def stats(self) -> dict[str, Any]:
        """Counters: events published, handler invocations, published per topic."""
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
        """Handle every queued event, including ones published while draining."""
        if self._flushing:
            # A handler called flush(); the outer flush is already draining
            # the queue, so there is nothing more to do here.
            return
        self._flushing = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                # Snapshot so handlers that (un)subscribe during dispatch
                # don't disturb this event's handler list.
                for handler in self._matching_handlers(topic):
                    self._handled += 1
                    if self._error_callback is None:
                        handler(topic, payload)
                        continue
                    try:
                        handler(topic, payload)
                    except Exception as exc:
                        self._error_callback(topic, payload, exc)
        finally:
            self._flushing = False
