"""In-process publish/subscribe event bus with synchronous dispatch.

Approach A: ``publish`` calls every matching handler before it returns, so all
handler side effects for the event -- including those of any events the
handlers themselves publish -- are complete by the time ``publish`` returns.
Callers may therefore read handler-written state immediately after
``publish``. ``flush`` is retained for backward compatibility and is a no-op.

Dispatch is re-entrant: an event published from inside a handler is handled
depth-first, right there, before the publishing handler continues. Handlers
for one topic run in subscription order. A handler that (transitively)
publishes its own topic without a termination condition will recurse until
Python raises ``RecursionError``; that is the caller's responsibility, exactly
as with any other recursive function.

Subscriptions may be exact (``"orders.created"``) or wildcard: a topic ending
in ``.*`` matches every published topic that starts with the part before the
``.*`` followed by a dot (``"orders.*"`` matches ``"orders.created"``). Exact
and wildcard subscribers both receive a matching event, interleaved in
subscription order.

Each subscription carries an integer ``priority`` (default 0). For a given
published topic, matching handlers run from highest priority to lowest; ties
keep subscription order. ``unsubscribe_all(topic)`` drops every handler that
was subscribed with exactly that topic string (so ``unsubscribe_all("a.*")``
removes the wildcard subscribers of that pattern and nothing else).

Errors: if a handler raises and an error callback has been registered with
``on_error``, the callback receives ``(topic, payload, exc)`` and the remaining
handlers for the event still run. Without an error callback the exception
propagates out of ``publish`` and the remaining handlers for that event are
skipped.
"""

import itertools
from typing import Any, Callable, Optional

Handler = Callable[[str, Any], Any]
ErrorHandler = Callable[[str, Any, BaseException], Any]

_WILDCARD_SUFFIX = ".*"


class EventBus:
    def __init__(self) -> None:
        # pattern -> list of (priority, token, handler). Tokens are
        # monotonically increasing ints so that (a) unsubscribe is unambiguous
        # even if the same handler object is subscribed more than once and
        # (b) handlers matched via different patterns can be ordered by
        # subscription time. Dispatch order is (-priority, token).
        self._subscribers: dict[str, list[tuple[int, int, Handler]]] = {}
        self._tokens = itertools.count()
        self._error_handler: Optional[ErrorHandler] = None
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Subscribe ``handler`` to ``topic`` and return an unsubscribe function.

        Higher ``priority`` handlers run before lower ones for the same event;
        handlers with equal priority run in subscription order.
        """
        token = next(self._tokens)
        self._subscribers.setdefault(topic, []).append((priority, token, handler))

        def unsubscribe() -> None:
            handlers = self._subscribers.get(topic)
            if not handlers:
                return
            self._subscribers[topic] = [
                entry for entry in handlers if entry[1] != token
            ]
            if not self._subscribers[topic]:
                del self._subscribers[topic]

        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed with exactly this topic string.

        Matching is literal: ``unsubscribe_all("orders.created")`` leaves an
        ``"orders.*"`` subscription in place, and vice versa. Unsubscribe
        functions previously returned for the topic remain safe to call.
        """
        self._subscribers.pop(topic, None)

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Subscribe ``handler`` so it is removed after its first invocation.

        Returns an unsubscribe function, like ``subscribe``, so a one-shot
        handler can also be cancelled before it ever fires. ``priority`` has
        the same meaning as in ``subscribe``.
        """
        fired = False

        def wrapper(t: str, payload: Any) -> Any:
            nonlocal fired
            if fired:
                return None
            fired = True
            unsubscribe()
            return handler(t, payload)

        unsubscribe = self.subscribe(topic, wrapper, priority=priority)
        return unsubscribe

    def on_error(self, callback: Optional[ErrorHandler]) -> None:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        While a callback is registered, a raising handler does not stop the
        remaining handlers for that event. Registering replaces any previous
        callback; pass ``None`` to remove it. An exception raised by the
        callback itself propagates out of ``publish``.
        """
        self._error_handler = callback

    def stats(self) -> dict:
        """Return counters: events published, handler invocations, and
        published events per topic. Handler invocations are counted even if
        the handler raised."""
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    def publish(self, topic: str, payload: Any) -> None:
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1
        for handler in self._matching_handlers(topic):
            self._handled += 1
            try:
                handler(topic, payload)
            except Exception as exc:
                if self._error_handler is None:
                    raise
                self._error_handler(topic, payload, exc)

    def _matching_handlers(self, topic: str) -> list[Handler]:
        # Snapshot so (un)subscribing during dispatch doesn't affect which
        # handlers see the event currently being handled.
        matches: list[tuple[int, int, Handler]] = list(self._subscribers.get(topic, ()))
        for pattern, handlers in self._subscribers.items():
            if pattern.endswith(_WILDCARD_SUFFIX) and pattern != topic:
                prefix = pattern[: -len(_WILDCARD_SUFFIX)] + "."
                if topic.startswith(prefix):
                    matches.extend(handlers)
        # Highest priority first; equal priorities keep subscription order.
        matches.sort(key=lambda entry: (-entry[0], entry[1]))
        return [handler for _, _, handler in matches]

    def flush(self) -> None:
        """No-op. Dispatch is synchronous, so there is never anything pending.

        Kept for backward compatibility with callers written against the
        queued design.
        """
        return None
