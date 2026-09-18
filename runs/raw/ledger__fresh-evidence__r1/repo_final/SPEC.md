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

Later additions (also fixed; tests depend on them):

```python
    def apply_interest(self, basis_points: int) -> None: ...     # floor(balance * bp / 10000), positive balances only
    def close_account(self, account_id: str) -> None: ...        # ValueError unless balance is zero
    def total_assets(self) -> int: ...
    def freeze(self, account_id: str) -> None: ...               # ValueError if already frozen
    def unfreeze(self, account_id: str) -> None: ...             # ValueError if not frozen
    def is_frozen(self, account_id: str) -> bool: ...
    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None: ...  # atomic: all or nothing
```

- A frozen account rejects `withdraw` and outgoing `transfer`/`batch_transfer` with `PermissionError`,
  but still accepts deposits and incoming transfers.

## Audit requirements

Financial auditors require that the ledger itself can reproduce the complete history of every
account. The ledger is the only system of record; there is no upstream log.

- Every applied operation is retained, in order, numbered from 1. Rejected calls change nothing
  and are not recorded.
- The balance of any account as it stood after any given operation number must be recoverable.
- Corrections are appended as new operations (e.g. a compensating deposit). Recorded operations
  are never edited or removed.

Audit interface:

```python
class Operation:            # immutable record: seq (1-based), kind (method name), params (read-only mapping)
    ...

class Ledger:
    def history(self) -> list[Operation]: ...                        # all applied operations, oldest first
    def balance_at(self, account_id: str, seq: int) -> int: ...      # balance right after operation `seq`; 0 = empty ledger
    @classmethod
    def replay(cls, operations) -> "Ledger": ...                     # rebuild a ledger from a log
```

## The core design decision

There are two reasonable ways to manage the ledger's state. **The audit requirements above rule
out Approach B**: a snapshot cannot answer "balance after operation N" or reproduce history, and
closing an account destroys its record. The implementation uses **Approach A**; the description of
both is kept for context.

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
