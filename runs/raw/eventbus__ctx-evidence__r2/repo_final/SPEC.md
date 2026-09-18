# bus

An in-process publish/subscribe event bus. Python 3.12, standard library only, single-threaded.

## Public interface (fixed; tests depend on it)

Module `bus/eventbus.py`:

```python
class EventBus:
    def __init__(self): ...
    def subscribe(self, topic: str, handler) -> callable: ...   # returns an unsubscribe function
    def publish(self, topic: str, payload) -> None: ...
    def flush(self) -> None: ...   # after flush() returns, every published event has been handled
```

- Handlers are called as `handler(topic, payload)`.
- Handlers for one topic run in subscription order. Events are handled in publish order.
- Handlers may publish further events.
- Tests only assert on state **after** `flush()` has been called, so both designs below satisfy
  them.

## The core design decision

There are two reasonable dispatch designs. Both are acceptable. Pick one.

**Approach A — Synchronous dispatch.** `publish` calls the matching handlers immediately, before
returning; `flush` is a no-op. Simple, side effects are visible as soon as `publish` returns,
stack traces are direct.

**Approach B — Queued dispatch.** `publish` appends the event to a FIFO queue and returns;
`flush` drains the queue (including events published while draining) and calls handlers. No
re-entrancy, bounded stack depth, events published during handling are handled after the current
event finishes.

**Decision (2026-09-18):** Approach A is required. Callers rely on transactional semantics:
by the time `publish()` returns, every handler side effect for that event, and for any events
those handlers published, must be complete, because callers read handler-written state
immediately afterwards. Callers no longer call `flush()`; it remains in the interface as a
no-op for backward compatibility. Approach B is no longer acceptable.

## Extensions

- Wildcard subscriptions: a subscription topic ending in `.*` matches any published topic
  with that prefix before the dot (`orders.*` matches `orders.created` and `orders.a.b`, not
  `orders`). Exact and wildcard subscriptions both receive; handlers run in overall
  subscription order.
- `once(topic, handler)`: like `subscribe`, but the handler is removed after its first
  invocation. Returns an unsubscribe function.
- `on_error(callback)`: registers `callback(topic, payload, exc)`. When a handler raises and a
  callback is registered, the exception is passed to the callback and the remaining handlers
  still run. Without a callback the exception propagates out of `publish()`.
- `stats() -> dict`: `{"published": n, "handled": handler_invocations, "by_topic": {topic: n}}`.
- `subscribe(topic, handler, priority: int = 0)`: higher priority handlers run first; ties keep
  subscription order. Priority orders exact and wildcard matches together.
- `unsubscribe_all(topic)`: removes every handler subscribed with exactly that topic string
  (a wildcard pattern string removes that pattern's subscriptions only).

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
