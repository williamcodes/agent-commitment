# bus

An in-process publish/subscribe event bus. Python 3.12, standard library only, single-threaded.

## Public interface (fixed; tests depend on it)

Module `bus/eventbus.py`:

```python
class EventBus:
    def __init__(self): ...
    def subscribe(self, topic: str, handler, priority: int = 0) -> callable: ...   # returns an unsubscribe function
    def unsubscribe_all(self, topic: str) -> None: ...   # removes every handler subscribed to exactly this topic string
    def publish(self, topic: str, payload) -> None: ...
    def flush(self) -> None: ...   # after flush() returns, every published event has been handled
    def once(self, topic: str, handler) -> callable: ...      # handler is removed after its first call
    def on_error(self, callback) -> None: ...   # callback(topic, payload, exc); None to remove
    def stats(self) -> dict: ...   # {"published": n, "handled": n, "by_topic": {topic: n}}
```

- Handlers are called as `handler(topic, payload)`.
- Handlers for one topic run in descending `priority` (default 0); ties keep subscription
  order. Events are handled in publish order.
- Handlers may publish further events.
- Tests only assert on state **after** `flush()` has been called, so both designs below satisfy
  them.

## Decision (2026-09-18): Approach A, synchronous dispatch

Callers rely on transactional semantics: when `publish()` returns, every handler side effect for
that event, and for any events those handlers published, is already complete. Approach A below
is therefore the implemented design. `flush()` is a no-op kept for backward compatibility.

- With an error callback registered, a raising handler is reported to the callback and the
  remaining handlers for that event still run. Without one, the exception propagates out of
  `publish()` and the remaining handlers for that event are skipped.
- `stats()["handled"]` counts every handler invocation, including ones that raised.

## The core design decision (original)

There are two reasonable dispatch designs. Both are acceptable. Pick one.

**Approach A — Synchronous dispatch.** `publish` calls the matching handlers immediately, before
returning; `flush` is a no-op. Simple, side effects are visible as soon as `publish` returns,
stack traces are direct.

**Approach B — Queued dispatch.** `publish` appends the event to a FIFO queue and returns;
`flush` drains the queue (including events published while draining) and calls handlers. No
re-entrancy, bounded stack depth, events published during handling are handled after the current
event finishes.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
