"""In-process publish/subscribe event bus (queued dispatch, Approach B).

``publish`` never calls handlers directly. It appends the event to a FIFO
queue; ``flush`` drains the queue and dispatches each event to the handlers
subscribed to its topic. Events published while a handler is running are
appended to the same queue and handled after the current event finishes, so
dispatch is never re-entrant and stack depth stays bounded regardless of how
deeply handlers chain publishes.

Subscriptions may be exact topics or wildcards. A subscription topic ending
in ``.*`` matches every published topic that starts with the part before the
``*`` (``orders.*`` matches ``orders.created`` and ``orders.created.retry``).
An event is delivered to its exact subscribers first, then to matching
wildcard subscribers from most to least specific; within each group handlers
run by descending ``priority`` (default 0), ties in subscription order.
``once`` registers a handler that is removed after its first invocation.
``unsubscribe_all(topic)`` drops every handler registered under exactly that
topic string (a wildcard pattern is only removed by passing the pattern).

``on_error`` registers a callback ``(topic, payload, exc)``. When a handler
raises and a callback is registered, the exception is handed to the callback
and the remaining handlers for that event still run; without a callback the
exception propagates out of ``flush``. ``stats`` reports publish and handler
counters.
"""

from collections import deque
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, Exception], Any]


class _Subscription:
    """One registered handler. Identity (not handler equality) is what
    ``unsubscribe`` removes, so the same callable can be subscribed twice."""

    __slots__ = ("priority", "handler")

    def __init__(self, priority: int, handler: Handler) -> None:
        self.priority = priority
        self.handler = handler


class EventBus:
    def __init__(self) -> None:
        # topic -> subscriptions sorted by descending priority; equal
        # priorities keep subscription order (stable insertion).
        self._subscribers: dict[str, list[_Subscription]] = {}
        # Pending (topic, payload) events in publish order.
        self._queue: deque[tuple[str, Any]] = deque()
        self._flushing = False
        self._error_callback: ErrorCallback | None = None
        # Counters for stats(). ``published``/``by_topic`` count publish()
        # calls; ``handled`` counts handler invocations (raising or not).
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``; return a function that removes it.

        Within a topic, handlers with higher ``priority`` run first; handlers
        with equal priority run in subscription order. The returned
        unsubscribe function is idempotent: calling it more than once (or
        after the handler was otherwise removed) is a no-op.
        """
        subs = self._subscribers.setdefault(topic, [])
        sub = _Subscription(priority, handler)
        # Insert after every existing entry with priority >= ours so ties
        # preserve subscription order.
        index = len(subs)
        while index > 0 and subs[index - 1].priority < priority:
            index -= 1
        subs.insert(index, sub)

        def unsubscribe() -> None:
            current = self._subscribers.get(topic)
            if current is None:
                return
            for i, existing in enumerate(current):
                if existing is sub:
                    del current[i]
                    break
            else:
                return
            if not current:
                del self._subscribers[topic]

        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed to exactly ``topic``.

        Only the given topic string is affected: ``unsubscribe_all("a.b")``
        leaves an ``a.*`` subscription in place, and ``unsubscribe_all("a.*")``
        removes only that pattern. Unsubscribe functions returned earlier for
        this topic become no-ops. Removing an unknown topic is a no-op.
        """
        self._subscribers.pop(topic, None)

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe`` but the handler is removed after its first call.

        The wildcard and priority rules apply. The returned function
        unsubscribes early; it is a no-op once the handler has fired.
        """

        def wrapper(t: str, payload: Any) -> Any:
            unsubscribe()
            return handler(t, payload)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def on_error(self, callback: ErrorCallback | None) -> None:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        With a callback registered, a raising handler does not stop dispatch:
        the callback is invoked and the event's remaining handlers still run.
        Pass ``None`` to remove the callback and restore propagation. Only one
        callback is kept; registering another replaces it.
        """
        self._error_callback = callback

    def publish(self, topic: str, payload: Any) -> None:
        """Enqueue an event. Handlers run on the next ``flush``."""
        self._queue.append((topic, payload))
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1

    def flush(self) -> None:
        """Handle every queued event, including ones published while draining.

        A nested call from inside a handler returns immediately; the outer
        flush is already draining the queue and will pick up any new events.
        If a handler raises and no error callback is registered, the exception
        propagates; that event's remaining handlers are skipped and later
        events stay queued for a later ``flush``.
        """
        if self._flushing:
            return
        self._flushing = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                # Snapshot so (un)subscribes during dispatch do not disturb
                # this event's handler sequence.
                for handler in self._matching_handlers(topic):
                    self._handled += 1
                    try:
                        handler(topic, payload)
                    except Exception as exc:
                        if self._error_callback is None:
                            raise
                        self._error_callback(topic, payload, exc)
        finally:
            self._flushing = False

    def stats(self) -> dict[str, Any]:
        """Return a snapshot of counters.

        ``published`` is the number of ``publish`` calls, ``handled`` the
        number of handler invocations so far (including ones that raised), and
        ``by_topic`` maps each published topic to its publish count. Counts
        are taken at publish time, so events still queued are included in
        ``published``/``by_topic`` but not yet in ``handled``.
        """
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    def _matching_handlers(self, topic: str) -> list[Handler]:
        """Return a snapshot of handlers for ``topic``: exact, then wildcards.

        Wildcard patterns are checked from the most specific prefix outward,
        e.g. for ``a.b.c``: ``a.b.*`` then ``a.*``. Each group is already in
        priority order, so the result needs no further sorting.
        """
        matched = [s.handler for s in self._subscribers.get(topic, ())]
        prefix = topic
        while True:
            dot = prefix.rfind(".")
            if dot < 0:
                break
            prefix = prefix[:dot]
            matched.extend(s.handler for s in self._subscribers.get(prefix + ".*", ()))
        return matched
