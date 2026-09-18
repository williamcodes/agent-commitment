"""In-process publish/subscribe event bus (Approach A: synchronous dispatch).

``publish`` calls every matching handler before it returns. Handlers may
publish further events; those are dispatched immediately and recursively, so
by the time any ``publish`` call returns, every side effect it caused,
transitively, is complete. ``flush`` is retained for backward compatibility
and is a no-op: there is never anything queued.

The trade-off versus queued dispatch is that dispatch is re-entrant and stack
depth grows with the length of a publish chain. A cycle of handlers that
publish to each other unconditionally will hit Python's recursion limit
rather than loop forever.

Subscription topics may end in ``.*`` to match every topic under that prefix
(``orders.*`` matches ``orders.created`` and ``orders.a.b`` but not ``orders``).
For a given event, exact-topic handlers run first, then wildcard handlers.
Within each group, handlers run in descending ``priority`` (default 0); ties
keep subscription order. ``unsubscribe_all(topic)`` removes every handler that
was subscribed with exactly that topic string (so ``"orders.*"`` clears the
wildcard subscribers for that prefix and nothing else).

Errors: if an error callback is registered via ``on_error``, a handler that
raises is reported to it as ``callback(topic, payload, exc)`` and the
remaining handlers for that event still run. Without a callback the exception
propagates out of ``publish`` and the remaining handlers for that event are
skipped.
"""

from bisect import insort
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, BaseException], Any]
# (-priority, subscription sequence number, handler). Lists of these are kept
# sorted, which yields highest priority first and subscription order on ties.
_Entry = tuple[int, int, Handler]

WILDCARD_SUFFIX = ".*"


class EventBus:
    def __init__(self) -> None:
        # Exact topic -> sorted entries.
        self._handlers: dict[str, list[_Entry]] = {}
        # Wildcard prefix (including trailing ".") -> sorted entries.
        self._wildcards: dict[str, list[_Entry]] = {}
        self._seq = 0  # monotonically increasing subscription counter
        self._error_callback: ErrorCallback | None = None
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``; return a function that unsubscribes it.

        A ``topic`` ending in ``.*`` subscribes to every topic under that prefix.
        Within a topic, higher ``priority`` handlers run first; equal priorities
        run in subscription order.
        """
        entries = self._entries_for(topic, create=True)
        self._seq += 1
        entry: _Entry = (-priority, self._seq, handler)
        insort(entries, entry)

        def unsubscribe() -> None:
            try:
                entries.remove(entry)
            except ValueError:
                pass  # already unsubscribed; idempotent

        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed with exactly this ``topic`` string.

        ``"a.b"`` removes only exact subscribers to ``a.b``; ``"a.*"`` removes
        only the wildcard subscribers registered as ``a.*``. Unknown topics are
        a no-op.
        """
        entries = self._entries_for(topic, create=False)
        if entries is not None:
            entries.clear()  # in place, so outstanding unsubscribe closures stay valid

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe``, but ``handler`` is removed after its first invocation.

        Returns an unsubscribe function usable to cancel before it fires.
        """

        def wrapper(t: str, payload: Any) -> None:
            unsubscribe()  # remove before calling so a re-publish can't re-trigger it
            handler(t, payload)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def on_error(self, callback: ErrorCallback | None) -> None:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        While a callback is registered, a raising handler does not stop the
        remaining handlers for that event. Pass ``None`` to remove it.
        """
        self._error_callback = callback

    def publish(self, topic: str, payload: Any) -> None:
        """Dispatch ``payload`` to every handler for ``topic`` before returning.

        Events published by handlers are dispatched immediately, so all
        transitive side effects are complete when this call returns.
        """
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        # Snapshot so (un)subscribing during dispatch doesn't affect this event.
        for _, _, handler in self._matching_handlers(topic):
            self._handled += 1
            if self._error_callback is None:
                handler(topic, payload)
                continue
            try:
                handler(topic, payload)
            except Exception as exc:
                self._error_callback(topic, payload, exc)

    def flush(self) -> None:
        """No-op, kept for backward compatibility.

        Dispatch is synchronous, so every published event has already been
        handled by the time ``publish`` returned.
        """

    def stats(self) -> dict[str, Any]:
        """Return counters: events published, handler invocations, and publishes per topic.

        ``handled`` counts every handler invocation, including ones that raised.
        """
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    def _matching_handlers(self, topic: str) -> list[_Entry]:
        """Snapshot of entries for ``topic``: exact matches, then wildcard matches.

        Each group is already sorted by (priority desc, subscription order).
        """
        matched = list(self._handlers.get(topic, ()))
        for prefix, entries in self._wildcards.items():
            if topic.startswith(prefix):
                matched.extend(entries)
        return matched

    def _entries_for(self, topic: str, *, create: bool) -> list[_Entry] | None:
        """The entry list a subscription to ``topic`` lives in (exact or wildcard)."""
        if topic.endswith(WILDCARD_SUFFIX):
            table, key = self._wildcards, topic[: -len(WILDCARD_SUFFIX)] + "."
        else:
            table, key = self._handlers, topic
        if create:
            return table.setdefault(key, [])
        return table.get(key)
