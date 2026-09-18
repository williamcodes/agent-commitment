"""In-memory account ledger.

Design: Approach A (event sourcing).

The source of truth is an append-only log of ``Operation`` records. Every
successful state-changing call (open, deposit, withdraw, transfer, interest,
close, freeze, unfreeze, batch transfer, overdraft limit) is validated,
applied, and then appended to the log as one record. The current balances,
frozen set and overdraft limits are a cache derived from the log; they can be
rebuilt at any time with ``Ledger.replay`` and are never edited directly.

Audit guarantees:

* ``history()`` returns every applied operation, in order, numbered from 1.
* ``balance_at(account_id, seq)`` returns an account's balance as it stood
  immediately after operation ``seq`` (``seq == 0`` is the empty ledger).
* Records are immutable and the log is never rewritten. Corrections are made
  by appending new operations (e.g. a compensating deposit or withdrawal).
* Rejected calls (insufficient funds, frozen account, unknown account, ...)
  do not change state and are not recorded.

Balances are integer cents. Amounts must be non-negative ints.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


@dataclass(frozen=True, slots=True)
class Operation:
    """One applied ledger operation.

    ``kind`` is the name of the ``Ledger`` method that produced it and
    ``params`` are the keyword arguments that reproduce it, so a log can be
    replayed with ``getattr(ledger, kind)(**params)``.
    """

    seq: int
    kind: str
    params: Mapping[str, Any]

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
        return f"Operation(seq={self.seq}, kind={self.kind!r}, {args})"


class Ledger:
    # Method names that may appear as Operation.kind. Replay refuses anything
    # else so a tampered log cannot invoke arbitrary methods.
    _OPERATION_KINDS = frozenset(
        {
            "open_account",
            "deposit",
            "withdraw",
            "transfer",
            "apply_interest",
            "close_account",
            "freeze",
            "unfreeze",
            "batch_transfer",
            "set_overdraft_limit",
        }
    )

    def __init__(self) -> None:
        self._log: list[Operation] = []
        # Derived caches; rebuilt from _log by replay().
        self._balances: dict[str, int] = {}
        self._frozen: set[str] = set()
        # Accounts absent from this mapping have the default limit of 0.
        self._overdraft: dict[str, int] = {}

    # -- audit / history -------------------------------------------------

    @classmethod
    def replay(cls, operations: Iterable[Operation]) -> Ledger:
        """Rebuild a ledger by re-applying ``operations`` in order.

        Each operation goes through the same public method (and validation)
        that produced it originally, so the result is exactly the state the
        original ledger had after the last record. Sequence numbers must be
        contiguous from 1; a gap or duplicate raises ``ValueError``.
        """
        ledger = cls()
        for op in operations:
            expected = len(ledger._log) + 1
            if op.seq != expected:
                raise ValueError(f"expected operation seq {expected}, got {op.seq}")
            if op.kind not in cls._OPERATION_KINDS:
                raise ValueError(f"unknown operation kind: {op.kind!r}")
            getattr(ledger, op.kind)(**op.params)
        return ledger

    def history(self) -> list[Operation]:
        """All applied operations, oldest first. ``seq`` runs from 1."""
        return list(self._log)

    def balance_at(self, account_id: str, seq: int) -> int:
        """Balance of ``account_id`` immediately after operation ``seq``.

        ``seq == 0`` is the state before any operation. Raises ``ValueError``
        if ``seq`` is out of range and ``UnknownAccount`` if the account did
        not exist (not yet opened, or already closed) at that point.
        """
        if isinstance(seq, bool) or not isinstance(seq, int):
            raise ValueError(f"seq must be an int, got {type(seq).__name__}")
        if not 0 <= seq <= len(self._log):
            raise ValueError(f"seq must be between 0 and {len(self._log)}, got {seq}")
        return Ledger.replay(self._log[:seq]).balance(account_id)

    def _record(self, kind: str, **params: Any) -> None:
        """Append an operation record. Only called after a successful apply."""
        self._log.append(Operation(len(self._log) + 1, kind, MappingProxyType(params)))

    # -- validation helpers ---------------------------------------------

    @staticmethod
    def _check_amount(amount: int) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError(f"amount must be an int, got {type(amount).__name__}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

    def _require(self, account_id: str, balances: Mapping[str, int] | None = None) -> None:
        if account_id not in (self._balances if balances is None else balances):
            raise UnknownAccount(account_id)

    def _check_debit(self, account_id: str, amount: int, balances: Mapping[str, int], verb: str) -> None:
        """Validate that ``amount`` may leave ``account_id`` given ``balances``."""
        self._check_amount(amount)
        self._require(account_id, balances)
        if account_id in self._frozen:
            raise PermissionError(f"account {account_id!r} is frozen, cannot {verb}")
        limit = self._overdraft.get(account_id, 0)
        if balances[account_id] - amount < -limit:
            raise InsufficientFunds(
                f"account {account_id!r} has {balances[account_id]} "
                f"(overdraft limit {limit}), cannot {verb} {amount}"
            )

    # -- public API ------------------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        self._check_amount(initial)
        if account_id in self._balances:
            raise ValueError(f"account already exists: {account_id!r}")
        self._balances[account_id] = initial
        self._record("open_account", account_id=account_id, initial=initial)

    def deposit(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        self._require(account_id)
        self._balances[account_id] += amount
        self._record("deposit", account_id=account_id, amount=amount)

    def withdraw(self, account_id: str, amount: int) -> None:
        self._check_debit(account_id, amount, self._balances, "withdraw")
        self._balances[account_id] -= amount
        self._record("withdraw", account_id=account_id, amount=amount)

    def transfer(self, src: str, dst: str, amount: int) -> None:
        # Validate everything up front so the operation is all-or-nothing.
        self._check_debit(src, amount, self._balances, "transfer")
        self._require(dst)
        self._balances[src] -= amount
        self._balances[dst] += amount
        self._record("transfer", src=src, dst=dst, amount=amount)

    def batch_transfer(self, transfers: Iterable[tuple[str, str, int]]) -> None:
        """Apply every transfer, or none of them.

        The batch is dry-run against a copy of the balances; only if every
        transfer validates is the copy committed. Recorded as one operation.
        """
        transfers = tuple((src, dst, amount) for src, dst, amount in transfers)
        scratch = dict(self._balances)
        for src, dst, amount in transfers:
            self._check_debit(src, amount, scratch, "transfer")
            self._require(dst, scratch)
            scratch[src] -= amount
            scratch[dst] += amount
        self._balances = scratch
        self._record("batch_transfer", transfers=transfers)

    def balance(self, account_id: str) -> int:
        self._require(account_id)
        return self._balances[account_id]

    def balances(self) -> dict[str, int]:
        """Current balance of every open account, as a fresh dict."""
        return dict(self._balances)

    def accounts(self) -> list[str]:
        return sorted(self._balances)

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow withdrawals and outgoing transfers down to ``-limit``.

        The limit is a non-negative int (default 0). Lowering it below the
        current overdraft is allowed; it only restricts further debits.
        """
        self._check_amount(limit)
        self._require(account_id)
        self._overdraft[account_id] = limit
        self._record("set_overdraft_limit", account_id=account_id, limit=limit)

    def overdraft_limit(self, account_id: str) -> int:
        self._require(account_id)
        return self._overdraft.get(account_id, 0)

    def freeze(self, account_id: str) -> None:
        """Block withdrawals and outgoing transfers. Deposits and incoming
        transfers remain allowed. Freezing a frozen account is an error."""
        self._require(account_id)
        if account_id in self._frozen:
            raise ValueError(f"account {account_id!r} is already frozen")
        self._frozen.add(account_id)
        self._record("freeze", account_id=account_id)

    def unfreeze(self, account_id: str) -> None:
        self._require(account_id)
        if account_id not in self._frozen:
            raise ValueError(f"account {account_id!r} is not frozen")
        self._frozen.discard(account_id)
        self._record("unfreeze", account_id=account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._require(account_id)
        return account_id in self._frozen

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with floor(balance * bp / 10000).

        Only positive balances earn interest; zero balances are unchanged.
        Each account's credit depends only on its own balance, so replaying
        this record is deterministic regardless of account order.
        """
        self._check_amount(basis_points)
        for account_id, bal in self._balances.items():
            if bal > 0:
                self._balances[account_id] = bal + (bal * basis_points) // 10_000
        self._record("apply_interest", basis_points=basis_points)

    def close_account(self, account_id: str) -> None:
        self._require(account_id)
        if self._balances[account_id] != 0:
            raise ValueError(
                f"account {account_id!r} has balance {self._balances[account_id]}, "
                "must be zero to close"
            )
        del self._balances[account_id]
        self._frozen.discard(account_id)
        self._overdraft.pop(account_id, None)
        self._record("close_account", account_id=account_id)

    def total_assets(self) -> int:
        return sum(self._balances.values())
