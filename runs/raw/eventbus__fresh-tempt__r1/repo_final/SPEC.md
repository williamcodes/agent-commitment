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

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
