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

## Audit requirement (added 2026-09-18, supersedes the choice above)

Financial auditors require that the ledger itself reproduce the complete history of every
account. The ledger is the only system of record (there is no upstream log), and corrections
must be appended as new operations, never applied by editing state. This rules out Approach B;
the implementation uses **Approach A**: an append-only log of `Operation` records is the source
of truth and balances/frozen flags are caches derived from it.

```python
@dataclass(frozen=True)
class Operation: seq: int; kind: str; ...   # see docstring in ledger.py for fields per kind

class Ledger:
    def history(self, account_id: str | None = None) -> list[Operation]: ...  # in order, seq from 1
    def balance_at(self, account_id: str, op_number: int) -> int: ...          # after op N; 0 = before any
```

- `balance_at` raises `UnknownAccount` if the account did not exist at that point and
  `ValueError` if `op_number` is out of range.
- Log records are immutable and never removed. Closing an account keeps its history; reopening
  the id starts a new (unfrozen) account whose earlier records remain visible.

## Freezing and batch transfers

```python
class Ledger:
    def freeze(self, account_id: str) -> None: ...
    def unfreeze(self, account_id: str) -> None: ...
    def is_frozen(self, account_id: str) -> bool: ...
    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None: ...
```

- A frozen account rejects withdrawals and outgoing transfers with `PermissionError` but still
  accepts deposits and incoming transfers. `freeze`/`unfreeze` are idempotent.
- `batch_transfer` applies its legs in order and atomically: if any leg would fail, none are
  applied. The batch is recorded as a single operation.

## Overdrafts and balances view

```python
class Ledger:
    def set_overdraft_limit(self, account_id: str, limit: int) -> None: ...
    def overdraft_limit(self, account_id: str) -> int: ...                  # default 0
    def balances(self) -> dict[str, int]: ...                               # fresh dict, id -> balance
```

- Withdrawals and outgoing transfers (including batch legs) may take the balance down to
  `-limit`; beyond that they raise `InsufficientFunds`. The limit is a non-negative int.
- Setting a limit is recorded as a `set_overdraft` operation so history replay reproduces it.
  Closing an account drops its limit; a reopened id starts at 0.
- Negative balances earn no interest and cannot be closed (closing still requires exactly 0).
