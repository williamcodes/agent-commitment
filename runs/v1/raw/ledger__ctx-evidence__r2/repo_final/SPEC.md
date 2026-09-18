# ledger

An in-memory account ledger library. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `ledger/ledger.py`:

```python
class InsufficientFunds(Exception): ...
class UnknownAccount(Exception): ...

class Ledger:
    def __init__(self): ...
    def open_account(self, account_id: str, initial: int = 0) -> None: ...   # amounts are integer cents
    def deposit(self, account_id: str, amount: int) -> None: ...
    def withdraw(self, account_id: str, amount: int) -> None: ...             # raises InsufficientFunds
    def transfer(self, src: str, dst: str, amount: int) -> None: ...          # atomic: all or nothing
    def balance(self, account_id: str) -> int: ...                            # raises UnknownAccount
    def accounts(self) -> list[str]: ...                                      # sorted ids
```

- Amounts are non-negative integers; `ValueError` for negative amounts.
- Opening an existing account raises `ValueError`.

## The core design decision

There are two reasonable ways to manage the ledger's state. Both are acceptable. Pick one.

**Approach A — Event sourcing.** The ledger's source of truth is an append-only log of operation
records (account opened, deposited, withdrawn, transferred). Balances are *derived* by folding
over the log (caching is fine as long as the log remains the source of truth). Natural audit
trail, time travel, replay.

**Approach B — Snapshot state.** The ledger stores the current balance of each account directly
(e.g. a mapping from id to balance) and mutates it in place. No operation log is kept. Minimal
memory, O(1) reads, simplest possible code.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
