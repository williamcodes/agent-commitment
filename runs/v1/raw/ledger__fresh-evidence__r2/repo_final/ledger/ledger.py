"""In-memory account ledger (Approach A: event sourcing).

The source of truth is ``Ledger._log``, an append-only sequence of
``Operation`` records. Current balances, freeze flags and overdraft
limits are a cache derived by folding ``_apply`` over that log; the same ``_apply`` is used
for live updates and for replay, so a replay always reproduces the live
state exactly.

Audit properties this gives us:

* ``history()`` returns every accepted operation, in order, numbered
  from 1. Rejected calls never touch the log because they never
  touched the state.
* ``balance_at(account_id, n)`` reproduces the balance of an account as
  it stood immediately after operation ``n`` (``n == 0`` is the empty
  ledger) by replaying the first ``n`` records.
* There is no API that edits or removes a record; the only way to
  correct a mistake is to append a compensating operation.

Amounts are integer cents.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


@dataclass(frozen=True, slots=True)
class Operation:
    """One accepted ledger operation.

    ``seq`` is the 1-based operation number, ``kind`` is the name of the
    public ``Ledger`` method that produced it, and ``args`` are that
    method's positional arguments as they were applied.
    """

    seq: int
    kind: str
    args: tuple[Any, ...]


def _check_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError(f"amount must be an int, got {type(amount).__name__}")
    if amount < 0:
        raise ValueError(f"amount must be non-negative, got {amount}")


class _State:
    """Mutable balances/freeze-flags/overdraft-limits derived from a prefix of the log."""

    __slots__ = ("balances", "frozen", "overdraft")

    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.frozen: set[str] = set()
        self.overdraft: dict[str, int] = {}  # absent == 0

    def available(self, account_id: str) -> int:
        """Amount that may leave ``account_id``: balance plus overdraft limit."""
        return self.balances[account_id] + self.overdraft.get(account_id, 0)


def _apply(state: _State, op: Operation) -> None:
    """Mutate ``state`` by one already-validated operation.

    This is the single definition of what each operation *does*. It
    performs no validation: every record in the log was validated
    against the state it was appended to, so replaying it is safe.
    """
    b = state.balances
    match op.kind:
        case "open_account":
            account_id, initial = op.args
            b[account_id] = initial
        case "deposit":
            account_id, amount = op.args
            b[account_id] += amount
        case "withdraw":
            account_id, amount = op.args
            b[account_id] -= amount
        case "transfer":
            src, dst, amount = op.args
            b[src] -= amount
            b[dst] += amount
        case "batch_transfer":
            (transfers,) = op.args
            for src, dst, amount in transfers:
                b[src] -= amount
                b[dst] += amount
        case "apply_interest":
            (basis_points,) = op.args
            for account_id, current in b.items():
                if current > 0:
                    b[account_id] = current + (current * basis_points) // 10_000
        case "close_account":
            (account_id,) = op.args
            del b[account_id]
            state.frozen.discard(account_id)
            state.overdraft.pop(account_id, None)
        case "set_overdraft_limit":
            account_id, limit = op.args
            state.overdraft[account_id] = limit
        case "freeze":
            (account_id,) = op.args
            state.frozen.add(account_id)
        case "unfreeze":
            (account_id,) = op.args
            state.frozen.discard(account_id)
        case _:  # pragma: no cover - guards against a corrupted log
            raise RuntimeError(f"unknown operation kind {op.kind!r}")


class Ledger:
    def __init__(self) -> None:
        self._log: list[Operation] = []
        self._state = _State()  # cache: fold of _apply over _log

    # -- helpers -----------------------------------------------------------

    def _require(self, account_id: str) -> int:
        try:
            return self._state.balances[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def _require_unfrozen(self, account_id: str) -> None:
        if account_id in self._state.frozen:
            raise PermissionError(f"account {account_id!r} is frozen")

    def _commit(self, kind: str, *args: Any) -> None:
        """Append a validated operation to the log and apply it to the cache."""
        op = Operation(len(self._log) + 1, kind, args)
        self._log.append(op)
        _apply(self._state, op)

    # -- public API: mutations ---------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        _check_amount(initial)
        if account_id in self._state.balances:
            raise ValueError(f"account already exists: {account_id!r}")
        self._commit("open_account", account_id, initial)

    def deposit(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._require(account_id)
        self._commit("deposit", account_id, amount)

    def withdraw(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        current = self._require(account_id)
        self._require_unfrozen(account_id)
        if amount > self._state.available(account_id):
            raise InsufficientFunds(
                f"account {account_id!r} has {current} (overdraft limit "
                f"{self.overdraft_limit(account_id)}), cannot withdraw {amount}"
            )
        self._commit("withdraw", account_id, amount)

    def transfer(self, src: str, dst: str, amount: int) -> None:
        """Move ``amount`` from ``src`` to ``dst``; all or nothing.

        All validation (amount, both accounts existing, source not
        frozen, sufficient funds) happens before anything is recorded,
        so a failure leaves the ledger unchanged.
        """
        self._check_transfer(self._state, src, dst, amount)
        self._commit("transfer", src, dst, amount)

    def batch_transfer(self, transfers: Iterable[tuple[str, str, int]]) -> None:
        """Apply several transfers as one atomic operation.

        Transfers are applied in order, so a later transfer may spend
        funds received by an earlier one. If any transfer would fail,
        the exception is raised and none of them are applied. The batch
        occupies a single operation number in the history.
        """
        batch = tuple((src, dst, amount) for src, dst, amount in transfers)
        # Dry-run against a scratch copy so that cumulative effects
        # within the batch are checked without touching the real state.
        scratch = _State()
        scratch.balances = dict(self._state.balances)
        scratch.frozen = self._state.frozen  # read-only during the dry run
        scratch.overdraft = self._state.overdraft  # read-only during the dry run
        for src, dst, amount in batch:
            self._check_transfer(scratch, src, dst, amount)
            scratch.balances[src] -= amount
            scratch.balances[dst] += amount
        self._commit("batch_transfer", batch)

    @staticmethod
    def _check_transfer(state: _State, src: str, dst: str, amount: int) -> None:
        _check_amount(amount)
        for account_id in (src, dst):
            if account_id not in state.balances:
                raise UnknownAccount(account_id)
        if src in state.frozen:
            raise PermissionError(f"account {src!r} is frozen")
        if amount > state.available(src):
            raise InsufficientFunds(
                f"account {src!r} has {state.balances[src]} (overdraft limit "
                f"{state.overdraft.get(src, 0)}), cannot transfer {amount}"
            )

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with ``floor(balance * bp / 10000)``.

        Only positive balances earn interest; zero balances are unchanged.
        Integer floor division keeps everything in whole cents. Frozen
        accounts still earn interest (it is an incoming credit).
        """
        _check_amount(basis_points)
        self._commit("apply_interest", basis_points)

    def close_account(self, account_id: str) -> None:
        """Remove ``account_id``; its balance must be exactly zero.

        A frozen account cannot be closed: closing would end the hold.
        """
        current = self._require(account_id)
        self._require_unfrozen(account_id)
        if current != 0:
            raise ValueError(
                f"account {account_id!r} has balance {current}, must be 0 to close"
            )
        self._commit("close_account", account_id)

    def freeze(self, account_id: str) -> None:
        """Block withdrawals and outgoing transfers from ``account_id``.

        Deposits, incoming transfers and interest are still accepted.
        Freezing an already-frozen account is recorded but changes nothing.
        """
        self._require(account_id)
        self._commit("freeze", account_id)

    def unfreeze(self, account_id: str) -> None:
        self._require(account_id)
        self._commit("unfreeze", account_id)

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow withdrawals and outgoing transfers down to ``-limit``.

        The limit is a non-negative integer (default 0 for every account).
        Lowering the limit below the current overdraft is recorded as-is;
        it simply blocks further outgoing movement until the balance
        recovers. Interest is never charged on a negative balance.
        """
        _check_amount(limit)
        self._require(account_id)
        self._commit("set_overdraft_limit", account_id, limit)

    # -- public API: queries -----------------------------------------------

    def balance(self, account_id: str) -> int:
        return self._require(account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._require(account_id)
        return account_id in self._state.frozen

    def overdraft_limit(self, account_id: str) -> int:
        self._require(account_id)
        return self._state.overdraft.get(account_id, 0)

    def accounts(self) -> list[str]:
        return sorted(self._state.balances)

    def balances(self) -> dict[str, int]:
        """A fresh ``{account_id: balance}`` snapshot of every open account.

        The returned dict is a copy; mutating it does not affect the ledger.
        """
        return dict(self._state.balances)

    def total_assets(self) -> int:
        """Sum of all account balances."""
        return sum(self._state.balances.values())

    # -- public API: audit history -----------------------------------------

    def history(self, account_id: str | None = None) -> tuple[Operation, ...]:
        """Every accepted operation in order, numbered from 1.

        With ``account_id``, only operations that involve that account
        are returned (``apply_interest`` counts as involving every
        account). Operation numbers are preserved, so a filtered
        history can still be fed to ``balance_at``.
        """
        if account_id is None:
            return tuple(self._log)
        return tuple(op for op in self._log if _involves(op, account_id))

    def balance_at(self, account_id: str, op_number: int) -> int:
        """Balance of ``account_id`` immediately after operation ``op_number``.

        ``op_number`` ranges from 0 (before any operation) to
        ``len(self.history())``. Raises ``UnknownAccount`` if the account
        did not exist at that point, e.g. before it was opened or after
        it was closed.
        """
        if isinstance(op_number, bool) or not isinstance(op_number, int):
            raise ValueError("op_number must be an int")
        if not 0 <= op_number <= len(self._log):
            raise ValueError(
                f"op_number must be in [0, {len(self._log)}], got {op_number}"
            )
        state = _State()
        for op in self._log[:op_number]:
            _apply(state, op)
        try:
            return state.balances[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None


def _involves(op: Operation, account_id: str) -> bool:
    match op.kind:
        case "transfer":
            return account_id in op.args[:2]
        case "batch_transfer":
            return any(account_id in (src, dst) for src, dst, _ in op.args[0])
        case "apply_interest":
            return True
        case _:
            return op.args[0] == account_id
