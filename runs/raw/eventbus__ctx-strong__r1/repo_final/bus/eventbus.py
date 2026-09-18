"""In-process publish/subscribe event bus (queued dispatch, Approach B).

``publish`` never invokes handlers directly. It appends the event to a FIFO
queue and returns. ``flush`` drains the queue, including any events that
handlers publish while draining, so that after ``flush`` returns every
published event has been handled.

Consequences of the queued design:

- Handlers are never re-entered: an event published from inside a handler is
  handled only after the current event's handlers have all finished.
- Stack depth is bounded regardless of how deeply handlers chain publishes.
- Events are handled strictly in publish order; handlers run in descending
  priority order, and within a priority in subscription order.

Topics
------
A subscription topic is either an exact topic name or a wildcard pattern
ending in ``.*``. The pattern ``orders.*`` matches every topic that begins
with ``orders.`` (``orders.created``, ``orders.paid``, ``orders.a.b``), but
not ``orders`` itself. When both an exact and a wildcard subscription match
an event, both receive it, ordered by priority and then subscription order.

Errors
------
By default an exception raised by a handler propagates out of ``flush``.
The failing event's remaining handlers are skipped, but events still in the
queue are kept and will be handled by the next ``flush``. Registering an
error callback with ``on_error`` changes this: the exception is passed to
every registered callback as ``callback(topic, payload, exc)`` and the
remaining handlers for that event still run. Only ``Exception`` subclasses
are routed to callbacks; ``KeyboardInterrupt`` and friends always propagate.

Stats
-----
``stats()`` returns counters: events published, handler invocations
attempted (a handler that raised still counts), and published events per
topic. Counts are keyed by the concrete published topic, never by a
wildcard pattern.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, Exception], Any]
WILDCARD_SUFFIX = ".*"


@dataclass(frozen=True, slots=True)
class _Subscription:
    id: int
    handler: Handler
    priority: int = 0

    @property
    def sort_key(self) -> tuple[int, int]:
        """Higher priority first; ties fall back to subscription order."""
        return (-self.priority, self.id)


class EventBus:
    """A single-threaded FIFO event bus."""

    def __init__(self) -> None:
        # Exact topic -> subscriptions, in subscription order.
        self._exact: dict[str, list[_Subscription]] = {}
        # Wildcard prefix (e.g. "orders." for "orders.*") -> subscriptions.
        self._wildcards: dict[str, list[_Subscription]] = {}
        self._queue: deque[tuple[str, Any]] = deque()
        self._next_id = 0
        self._flushing = False
        self._error_callbacks: list[ErrorCallback] = []
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    # ------------------------------------------------------------------ API

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``. Returns an unsubscribe function.

        ``topic`` may be an exact name or a wildcard pattern ending in ``.*``.
        Handlers matching an event run in descending ``priority`` order;
        handlers with equal priority run in subscription order. The
        unsubscribe function is idempotent and safe to call from inside a
        handler, including the handler being unsubscribed.
        """
        table, key = self._table_for(topic)
        sub = _Subscription(self._next_id, handler, priority)
        self._next_id += 1
        table.setdefault(key, []).append(sub)

        def unsubscribe() -> None:
            entries = table.get(key)
            if not entries:
                return
            # Rebuild rather than mutate in place so that a dispatch loop
            # iterating over a snapshot of this list is unaffected.
            remaining = [s for s in entries if s.id != sub.id]
            if remaining:
                table[key] = remaining
            else:
                del table[key]

        return unsubscribe

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe``, but the handler is removed after its first call.

        The subscription is removed *before* the handler runs, so the handler
        cannot be invoked a second time even if it raises or publishes an
        event that would match it again. Returns an unsubscribe function
        that can cancel the subscription before it ever fires.
        """

        def wrapper(t: str, p: Any) -> Any:
            unsubscribe()
            return handler(t, p)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed with exactly this topic string.

        Passing ``"orders.*"`` removes the subscriptions registered with that
        wildcard pattern, not the exact ``orders.x`` subscriptions. Safe to
        call from inside a handler; the current event's dispatch, which works
        from a snapshot, is unaffected.
        """
        table, key = self._table_for(topic)
        table.pop(key, None)

    def on_error(self, callback: ErrorCallback) -> Callable[[], None]:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        While at least one callback is registered, a handler that raises no
        longer aborts dispatch: the exception is reported to every callback
        in registration order and the event's remaining handlers still run.
        An exception raised by a callback itself is not caught. Returns a
        function that removes the callback again.
        """
        self._error_callbacks.append(callback)

        def remove() -> None:
            try:
                self._error_callbacks.remove(callback)
            except ValueError:
                pass

        return remove

    def publish(self, topic: str, payload: Any) -> None:
        """Enqueue an event. Handlers run on the next ``flush``."""
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        self._queue.append((topic, payload))

    def flush(self) -> None:
        """Handle every queued event, including events published while draining.

        Calling ``flush`` from inside a handler is a no-op; the outer flush
        already owns the queue and will pick up whatever was published.
        """
        if self._flushing:
            return
        self._flushing = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                for sub in self._matching(topic):
                    self._invoke(sub.handler, topic, payload)
        finally:
            self._flushing = False

    def stats(self) -> dict[str, Any]:
        """Return a snapshot of the counters; mutating it does not affect the bus."""
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    # ------------------------------------------------------------ internals

    def _invoke(self, handler: Handler, topic: str, payload: Any) -> None:
        """Call one handler, routing exceptions to error callbacks if any."""
        self._handled += 1
        try:
            handler(topic, payload)
        except Exception as exc:
            if not self._error_callbacks:
                raise
            # Snapshot so a callback that unregisters itself is safe.
            for callback in list(self._error_callbacks):
                callback(topic, payload, exc)

    def _matching(self, topic: str) -> list[_Subscription]:
        """Snapshot of every subscription matching ``topic``, in subscription order.

        Taking a snapshot means subscribe/unsubscribe calls made while this
        event is being handled do not affect which handlers see it.
        """
        matches = list(self._exact.get(topic, ()))
        for prefix, subs in self._wildcards.items():
            if topic.startswith(prefix):
                matches.extend(subs)
        # Order across exact and wildcard kinds: higher priority first, then
        # global subscription order.
        matches.sort(key=_Subscription.sort_key.fget)
        return matches

    def _table_for(self, topic: str) -> tuple[dict[str, list[_Subscription]], str]:
        """Map a subscription topic string to its table and key."""
        if topic.endswith(WILDCARD_SUFFIX):
            return self._wildcards, topic[: -len(WILDCARD_SUFFIX)] + "."
        return self._exact, topic
