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
    def on_error(self, callback) -> None: ...   # callback(topic, payload, exc); see "Errors" below
    def stats(self) -> dict: ...   # {"published": n, "handled": handler_invocations, "by_topic": {topic: n}}
```

- Handlers are called as `handler(topic, payload)`.
- Handlers for one topic run in subscription order. Events are handled in publish order.
- `subscribe(..., priority=n)`: within a topic, higher-priority handlers run first; ties keep
  subscription order. The default priority is 0.
- `unsubscribe_all(topic)` removes every handler subscribed to exactly that topic string. It is
  a literal match, so it does not expand wildcards.
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

## Chosen design: Approach A (synchronous)

Callers rely on transactional semantics: by the time `publish()` returns, every handler side
effect for that event, and for any events those handlers published, is complete, because the
caller immediately reads state written by the handlers. Synchronous dispatch gives that
guarantee for every `publish()` call, including nested ones made from inside a handler.
`flush()` is a no-op kept only for backward compatibility; callers no longer need to call it.

## Errors

- With an error callback registered via `on_error`, a raising handler is reported as
  `callback(topic, payload, exc)` and the remaining handlers for that event still run.
- Without one, the exception propagates out of `publish()` and the remaining handlers for that
  event are skipped.
- `stats()["handled"]` counts handler invocations, including ones that raised.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
