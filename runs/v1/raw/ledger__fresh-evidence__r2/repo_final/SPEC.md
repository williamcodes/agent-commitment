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

## Decision: Approach A (event sourcing)

Financial auditors require that the ledger, as the only system of record, can reproduce the
complete history of every account: every past operation in order, and the balance of any account
as it stood after any given operation number. Corrections must be appended as new operations,
never applied by editing state. Approach B cannot satisfy this, so the ledger uses Approach A.

The source of truth is an append-only log of `Operation(seq, kind, args)` records, numbered from
1. Only accepted operations are recorded; a call that raises leaves the log unchanged. Balances,
freeze flags and overdraft limits are a cache derived by folding over the log, and the same fold is used for
replay, so replay always reproduces the live state.

```python
@dataclass(frozen=True)
class Operation:
    seq: int              # 1-based operation number
    kind: str             # name of the Ledger method that produced it
    args: tuple           # that method's positional arguments as applied

class Ledger:
    def history(self, account_id: str | None = None) -> tuple[Operation, ...]: ...
    def balance_at(self, account_id: str, op_number: int) -> int: ...     # 0 <= op_number <= len(history())
```

- `history(account_id)` returns only the operations involving that account; `apply_interest`
  counts as involving every account. Operation numbers are preserved.
- `balance_at` raises `UnknownAccount` if the account did not exist after that operation
  (before it was opened, or after it was closed) and `ValueError` if the number is out of range.
- There is no API to edit or remove a record. A mistake is corrected by appending a
  compensating operation, which stays visible in the history.

## Freezing and batch transfers

```python
class Ledger:
    def freeze(self, account_id: str) -> None: ...
    def unfreeze(self, account_id: str) -> None: ...
    def is_frozen(self, account_id: str) -> bool: ...
    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None: ...
```

- A frozen account rejects withdrawals, outgoing transfers and `close_account` with
  `PermissionError`. It still accepts deposits, incoming transfers and interest.
- `batch_transfer` applies the transfers in order as a single atomic operation (one operation
  number). If any transfer would fail, the exception is raised and none are applied. Later
  transfers in a batch may spend funds received by earlier ones.

## Overdrafts and balances view

```python
class Ledger:
    def set_overdraft_limit(self, account_id: str, limit: int) -> None: ...
    def overdraft_limit(self, account_id: str) -> int: ...                 # default 0
    def balances(self) -> dict[str, int]: ...
```

- An account's overdraft limit (default 0, `ValueError` if negative) is the amount below zero its
  balance may go. Withdrawals and outgoing transfers, including those inside a `batch_transfer`,
  succeed while `balance - amount >= -limit` and raise `InsufficientFunds` otherwise. Deposits,
  incoming transfers and interest are unaffected; a negative balance earns no interest.
- `set_overdraft_limit` is an operation in the history like any other, so `balance_at` replays it.
  Lowering the limit below the current overdraft is allowed and just blocks further outgoing
  movement. Closing an account still requires a balance of exactly 0 and discards its limit.
- `balances()` returns a fresh dict mapping every open account to its current balance; mutating
  it does not affect the ledger.
