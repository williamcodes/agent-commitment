"""In-process publish/subscribe event bus.

Dispatch model: run-to-completion queue
---------------------------------------
Events go through a FIFO queue, but ``publish`` drains that queue before it
returns unless a drain is already in progress. The effect is:

* From the caller's point of view, ``publish`` is transactional: when it
  returns, every handler for that event, and for every event those handlers
  published (transitively), has already run. Callers do not need ``flush``.
* From a handler's point of view, ``publish`` only enqueues. Events published
  during handling run after the current event finishes, in publish order.
  Handlers never re-enter the dispatch loop, so stack depth stays bounded no
  matter how deeply events chain.

``flush`` remains for backward compatibility. It drains anything still
queued, which in practice only happens after a handler exception propagated
out of a previous drain (see "Errors" below).

Topics
------
Subscriptions may be exact topics or wildcard patterns. A pattern ending in
``.*`` matches any topic that begins with the text before the ``*``, so
``orders.*`` matches ``orders.created`` and ``orders.created.v2`` but not
``orders`` or ``ordersx``. Exact and wildcard subscriptions both receive a
matching event.

Handler order
-------------
Each subscription has an integer ``priority`` (default 0). For a given event,
matching handlers run from highest priority to lowest; equal priorities keep
subscription order. The ordering is global across exact and wildcard
subscriptions, so a priority-10 wildcard handler runs before a priority-0
exact handler.

Errors
------
If an error callback is registered via ``on_error``, a raising handler is
reported to it as ``callback(topic, payload, exc)`` and the remaining handlers
for that event still run. Without a callback the exception propagates out of
the ``publish`` (or ``flush``) call that was draining; the remaining handlers
for that event are skipped and any events still queued stay queued until the
next ``publish`` or ``flush``, so no event is silently dropped.
"""

from bisect import insort
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, BaseException], Any]

_WILDCARD_SUFFIX = ".*"


@dataclass(frozen=True, slots=True)
class _Subscription:
    pattern: str
    handler: Handler
    priority: int

    def matches(self, topic: str) -> bool:
        if self.pattern.endswith(_WILDCARD_SUFFIX):
            return topic.startswith(self.pattern[: -len(_WILDCARD_SUFFIX) + 1])
        return topic == self.pattern


class EventBus:
    def __init__(self) -> None:
        self._subscriptions: list[_Subscription] = []
        self._queue: deque[tuple[str, Any]] = deque()
        self._draining = False
        self._error_callback: ErrorCallback | None = None
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    # -- subscriptions -----------------------------------------------------

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic`` (exact or ``prefix.*`` wildcard).

        Higher ``priority`` handlers run first; ties keep subscription order.
        Returns an unsubscribe function; calling it more than once is harmless.
        """
        sub = _Subscription(topic, handler, priority)
        # The list is kept sorted by descending priority. insort_right places
        # a new entry after existing equal-priority entries, which preserves
        # subscription order among ties.
        insort(self._subscriptions, sub, key=lambda s: -s.priority)

        def unsubscribe() -> None:
            try:
                self._subscriptions.remove(sub)
            except ValueError:
                pass  # already unsubscribed

        return unsubscribe

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe`` but the handler is removed after its first call.

        The subscription is removed *before* the handler runs, so a handler
        that re-publishes its own topic will not be invoked again. Returns an
        unsubscribe function for cancelling before the handler has fired.
        """

        def one_shot(t: str, p: Any) -> None:
            unsubscribe()
            handler(t, p)

        unsubscribe = self.subscribe(topic, one_shot, priority)
        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every subscription whose pattern is exactly ``topic``.

        ``unsubscribe_all("orders.*")`` removes that wildcard subscription;
        ``unsubscribe_all("orders.created")`` does not touch it.
        """
        self._subscriptions = [s for s in self._subscriptions if s.pattern != topic]

    def on_error(self, callback: ErrorCallback | None) -> None:
        """Set the error callback ``callback(topic, payload, exc)``.

        Pass ``None`` to clear it and return to propagating exceptions.
        """
        self._error_callback = callback

    # -- publishing --------------------------------------------------------

    def publish(self, topic: str, payload: Any) -> None:
        """Publish an event.

        Called from outside a handler, this handles the event and everything
        it triggers before returning. Called from inside a handler, it only
        enqueues; the event runs after the current one finishes.
        """
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        self._queue.append((topic, payload))
        self.flush()

    def flush(self) -> None:
        """Handle every queued event, including events published while draining.

        A nested call from inside a handler is a no-op; the outer drain will
        pick up whatever the handler published.
        """
        if self._draining:
            return
        self._draining = True
        try:
            while self._queue:
                topic, payload = self._queue.popleft()
                self._dispatch(topic, payload)
        finally:
            self._draining = False

    def _dispatch(self, topic: str, payload: Any) -> None:
        # Snapshot so handlers that subscribe/unsubscribe during dispatch
        # don't perturb iteration of the current event.
        for sub in list(self._subscriptions):
            if not sub.matches(topic):
                continue
            self._handled += 1
            try:
                sub.handler(topic, payload)
            except Exception as exc:
                if self._error_callback is None:
                    raise
                self._error_callback(topic, payload, exc)

    # -- introspection -----------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Counters: ``published`` events, ``handled`` handler invocations,
        and ``by_topic`` published counts keyed by topic."""
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }
