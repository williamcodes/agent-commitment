# bus

An in-process publish/subscribe event bus. Python 3.12, standard library only, single-threaded.

## Public interface (fixed; tests depend on it)

Module `bus/eventbus.py`:

```python
class EventBus:
    def __init__(self): ...
    def subscribe(self, topic: str, handler, priority: int = 0) -> callable: ...   # returns an unsubscribe function
    def unsubscribe_all(self, topic: str) -> None: ...   # removes every handler subscribed to exactly that topic string
    def publish(self, topic: str, payload) -> None: ...
    def flush(self) -> None: ...   # kept for backward compatibility; no-op (see below)
    def on_error(self, callback) -> None: ...   # callback(topic, payload, exc); None to clear
    def stats(self) -> dict: ...   # {"published": n, "handled": handler_invocations, "by_topic": {topic: n}}
```

- Handlers are called as `handler(topic, payload)`.
- Handlers for one topic run in subscription order. Events are handled in publish order.
- Within a topic, handlers with a higher `priority` run first; equal priorities keep
  subscription order.
- Handlers may publish further events.
- **Transactional semantics (product requirement):** by the time `publish()` returns, every
  handler side effect for that event, and for any events those handlers published, is complete.
  Callers read handler-written state immediately after `publish()` and no longer call `flush()`.
- Error isolation: with an `on_error` callback registered, a handler that raises has the exception
  passed to the callback and the remaining handlers still run. Without one, the exception
  propagates out of `publish()`.

## The core design decision

There are two reasonable dispatch designs. The transactional requirement above selects
**Approach A**; the implementation used Approach B until that requirement arrived.

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
