"""In-process publish/subscribe event bus (Approach A: synchronous dispatch).

``publish`` calls every matching handler before it returns. A handler that
publishes another event has that event fully handled, recursively, before its
own ``publish`` call returns. So when any ``publish`` returns, every side
effect of that event and of every event it caused is complete, and the caller
can read state written by the handlers immediately. ``flush`` is kept for
backward compatibility and does nothing.

Because dispatch is nested function calls, a publish cycle (a handler that
directly or indirectly re-publishes its own topic without a stopping
condition) fails loudly with ``RecursionError`` rather than looping forever.

Topics
------
A subscription topic is either an exact topic name or a wildcard pattern
ending in ``.*``. The pattern ``orders.*`` matches every published topic that
starts with ``orders.`` (``orders.created``, ``orders.paid``, and deeper
names such as ``orders.item.added``); it does not match the bare topic
``orders``. Exact and wildcard subscriptions that both match an event all
receive it, in the order they were subscribed.

Ordering
--------
Each subscription has an integer ``priority`` (default 0). Handlers that
match an event run from highest priority to lowest; among equal priorities
they run in subscription order. The ordering is applied across every
subscription that matches the event, exact or wildcard, so a wildcard
handler with priority 10 runs before an exact handler with priority 0.

Errors
------
By default an exception raised by a handler propagates out of ``publish``
(through any enclosing handler's own ``publish`` call); the handlers that had
not yet run for that event are skipped. Registering a callback with
``on_error`` changes this: the exception is passed to the callback as
``callback(topic, payload, exc)`` and dispatch continues with the remaining
handlers. An exception raised by the callback itself propagates.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, Exception], Any]

WILDCARD_SUFFIX = ".*"


class _Subscription:
    """One registration of a handler on a topic or wildcard pattern.

    Registrations are matched by identity so the same callable can be
    subscribed more than once and each registration can be removed
    independently. ``priority`` orders handlers (higher first); ``order`` is
    a bus-wide sequence number that breaks ties and keeps subscription order
    even when an event matches several subscription keys (an exact topic
    plus one or more wildcards).
    """

    __slots__ = ("handler", "priority", "order")

    def __init__(self, handler: Handler, priority: int, order: int) -> None:
        self.handler = handler
        self.priority = priority
        self.order = order

    @property
    def sort_key(self) -> tuple[int, int]:
        """Sort ascending: highest priority first, then earliest subscription."""
        return (-self.priority, self.order)


class EventBus:
    def __init__(self) -> None:
        # Keyed by the subscription topic as given: either an exact topic or
        # a wildcard pattern such as "orders.*".
        self._subscribers: dict[str, list[_Subscription]] = {}
        self._order = itertools.count()
        self._error_callback: ErrorCallback | None = None
        self._published = 0
        self._handled = 0
        self._published_by_topic: dict[str, int] = {}

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``; return a function that removes it.

        ``topic`` may be an exact name or a wildcard pattern ending in ``.*``.
        Handlers with a higher ``priority`` run before handlers with a lower
        one; equal priorities run in subscription order. The returned
        unsubscribe function is idempotent, and is also a harmless no-op after
        ``unsubscribe_all`` has removed the subscription.
        """
        sub = _Subscription(handler, priority, next(self._order))
        self._subscribers.setdefault(topic, []).append(sub)

        def unsubscribe() -> None:
            subs = self._subscribers.get(topic)
            if not subs:
                return
            for i, s in enumerate(subs):
                if s is sub:
                    del subs[i]
                    break
            if not subs:
                del self._subscribers[topic]

        return unsubscribe

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe`` but the handler is removed after its first call.

        The subscription is removed *before* the handler runs, so a handler
        that raises is still gone, and an event that the handler itself
        publishes cannot re-trigger it. Returns an unsubscribe function that
        can be used to cancel the handler before it has fired.
        """

        def wrapper(event_topic: str, payload: Any) -> None:
            unsubscribe()
            handler(event_topic, payload)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed to exactly the string ``topic``.

        Matching is on the subscription key as given, so
        ``unsubscribe_all("orders.*")`` removes that wildcard subscription
        and nothing else, and ``unsubscribe_all("orders.created")`` leaves
        ``orders.*`` subscriptions in place. Calling this for a topic with no
        subscribers is a no-op. Because ``publish`` dispatches from a
        snapshot, calling this inside a handler does not affect handlers
        already selected for the current event.
        """
        self._subscribers.pop(topic, None)

    def on_error(self, callback: ErrorCallback | None) -> None:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        While a callback is registered, a handler that raises does not stop
        dispatch: the exception goes to the callback and the remaining
        handlers for the event still run. Pass ``None`` to remove the callback
        and restore propagating behaviour.
        """
        self._error_callback = callback

    def publish(self, topic: str, payload: Any) -> None:
        """Dispatch ``payload`` to every handler matching ``topic``, then return.

        Handlers run immediately, highest priority first and otherwise in
        subscription order. Events published by a
        handler are handled in full before that handler's ``publish`` call
        returns, so once this method returns every side effect of the event,
        including cascaded events, has happened.
        """
        self._published += 1
        self._published_by_topic[topic] = self._published_by_topic.get(topic, 0) + 1
        # _matching returns a snapshot, so subscribing/unsubscribing inside a
        # handler does not disturb dispatch of this event.
        for sub in self._matching(topic):
            self._handled += 1
            try:
                sub.handler(topic, payload)
            except Exception as exc:
                if self._error_callback is None:
                    raise
                self._error_callback(topic, payload, exc)

    def flush(self) -> None:
        """No-op, kept for backward compatibility.

        Every event is fully handled by the time ``publish`` returns, so there
        is never anything pending to flush.
        """

    def stats(self) -> dict[str, Any]:
        """Return counters as a fresh dict.

        ``published`` is the number of ``publish`` calls, ``handled`` the number
        of handler invocations (including ones that raised), and ``by_topic``
        maps each published topic to its publish count.
        """
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._published_by_topic),
        }

    def _matching(self, topic: str) -> list[_Subscription]:
        """Return the subscriptions matching ``topic`` in dispatch order.

        Dispatch order is highest priority first, then subscription order.
        """
        matches = list(self._subscribers.get(topic, ()))
        # Every dotted prefix of the topic yields a candidate wildcard key:
        # for "a.b.c" that is "a.*" and "a.b.*".
        end = topic.find(".")
        while end != -1:
            matches.extend(self._subscribers.get(topic[:end] + WILDCARD_SUFFIX, ()))
            end = topic.find(".", end + 1)
        if len(matches) > 1:
            matches.sort(key=lambda s: s.sort_key)
        return matches
