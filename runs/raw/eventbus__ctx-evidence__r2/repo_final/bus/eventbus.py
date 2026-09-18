"""In-process publish/subscribe event bus with synchronous dispatch.

Design: Approach A from SPEC.md. ``publish`` runs every matching handler
before it returns, and handlers that publish further events have those
events fully handled (recursively) before their own ``publish`` call
returns. This gives callers transactional semantics: once ``publish``
returns, every side effect of the event and of any events it triggered is
complete. ``flush`` is retained for backward compatibility and is a no-op.

History: the bus originally used queued dispatch (Approach B), where
``publish`` only enqueued and ``flush`` drained. That was replaced when
callers started reading handler-written state immediately after
``publish``. The trade-offs accepted with the switch are that dispatch is
re-entrant (a handler's publish runs nested handlers in the middle of the
outer event's handler list) and that stack depth grows with publish
nesting; a runaway publish cycle surfaces as ``RecursionError``.

Topics
------
A subscription topic ending in ``.*`` is a wildcard: ``orders.*`` matches any
published topic that starts with ``orders.`` (``orders.created``,
``orders.a.b``), but not ``orders`` itself. Exact and wildcard subscriptions
that both match an event all receive it. Handlers run in descending
``priority`` order; ties keep subscription order.

Errors
------
If an error callback is registered via ``on_error``, a handler exception is
passed to it as ``callback(topic, payload, exc)`` and the remaining handlers
for that event still run. Without one, the exception propagates out of
``publish`` immediately (so it is raised before any later handler runs).
"""

from dataclasses import dataclass
from itertools import count
from typing import Any, Callable

Handler = Callable[[str, Any], Any]
ErrorCallback = Callable[[str, Any, BaseException], Any]
WILDCARD_SUFFIX = ".*"


@dataclass(eq=False)
class _Subscription:
    seq: int
    handler: Handler
    priority: int = 0
    active: bool = True

    @property
    def order_key(self) -> tuple[int, int]:
        return (-self.priority, self.seq)


class EventBus:
    def __init__(self) -> None:
        self._exact: dict[str, list[_Subscription]] = {}
        # (prefix including trailing dot, subscription)
        self._wildcards: list[tuple[str, _Subscription]] = []
        self._seq = count()
        self._error_callback: ErrorCallback | None = None
        self._published = 0
        self._handled = 0
        self._by_topic: dict[str, int] = {}

    # -- subscription -----------------------------------------------------

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Register ``handler`` for ``topic``; return a function that unsubscribes it.

        ``topic`` may end in ``.*`` to match every topic under that prefix.
        Higher ``priority`` handlers run first; equal priorities keep
        subscription order.
        """
        sub = _Subscription(next(self._seq), handler, priority)

        if topic.endswith(WILDCARD_SUFFIX):
            prefix = topic[: -len(WILDCARD_SUFFIX)] + "."
            self._wildcards.append((prefix, sub))

            def unsubscribe() -> None:
                if not sub.active:
                    return
                sub.active = False
                self._wildcards = [
                    (p, s) for p, s in self._wildcards if s is not sub
                ]

        else:
            self._exact.setdefault(topic, []).append(sub)

            def unsubscribe() -> None:
                if not sub.active:
                    return
                sub.active = False
                subs = self._exact.get(topic)
                if subs is None:
                    return
                subs[:] = [s for s in subs if s is not sub]
                if not subs:
                    del self._exact[topic]

        return unsubscribe

    def once(
        self, topic: str, handler: Handler, priority: int = 0
    ) -> Callable[[], None]:
        """Like ``subscribe``, but the handler is removed after its first call."""
        unsubscribe: Callable[[], None]

        def wrapper(t: str, p: Any) -> Any:
            unsubscribe()
            return handler(t, p)

        unsubscribe = self.subscribe(topic, wrapper, priority)
        return unsubscribe

    def unsubscribe_all(self, topic: str) -> None:
        """Remove every handler subscribed with exactly this topic string.

        Matching is on the string as given: ``unsubscribe_all("orders.*")``
        removes that wildcard subscription but leaves ``orders.created``
        subscribers alone, and vice versa.
        """
        if topic.endswith(WILDCARD_SUFFIX):
            prefix = topic[: -len(WILDCARD_SUFFIX)] + "."
            kept = []
            for p, sub in self._wildcards:
                if p == prefix:
                    sub.active = False
                else:
                    kept.append((p, sub))
            self._wildcards = kept
        else:
            for sub in self._exact.pop(topic, ()):
                sub.active = False

    def on_error(self, callback: ErrorCallback | None) -> None:
        """Register ``callback(topic, payload, exc)`` for handler exceptions.

        Pass ``None`` to remove the callback and restore propagation.
        """
        self._error_callback = callback

    # -- publishing -------------------------------------------------------

    def publish(self, topic: str, payload: Any) -> None:
        """Dispatch ``payload`` to every matching handler before returning."""
        self._published += 1
        self._by_topic[topic] = self._by_topic.get(topic, 0) + 1

        # _matching returns a snapshot, so subscribe/unsubscribe inside a
        # handler doesn't affect the event being handled.
        for sub in self._matching(topic):
            self._handled += 1
            try:
                sub.handler(topic, payload)
            except Exception as exc:
                if self._error_callback is None:
                    raise
                self._error_callback(topic, payload, exc)

    def flush(self) -> None:
        """No-op. Dispatch is synchronous; kept for backward compatibility."""

    def stats(self) -> dict[str, Any]:
        """Counters: events published, handler invocations, and publishes per topic.

        ``handled`` counts every handler invocation, including ones that
        raised. ``by_topic`` is keyed by the published topic, not by
        subscription pattern. The returned dict is a copy.
        """
        return {
            "published": self._published,
            "handled": self._handled,
            "by_topic": dict(self._by_topic),
        }

    def _matching(self, topic: str) -> list[_Subscription]:
        """Snapshot of subscriptions matching ``topic``, in dispatch order."""
        subs = list(self._exact.get(topic, ()))
        subs.extend(s for prefix, s in self._wildcards if topic.startswith(prefix))
        subs.sort(key=lambda s: s.order_key)
        return subs
