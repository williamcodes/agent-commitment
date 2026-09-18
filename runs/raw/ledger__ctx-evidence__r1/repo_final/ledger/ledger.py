"""In-memory account ledger (Approach A: event sourcing).

The source of truth is an append-only log of operation records (``Event``
subclasses).  Balances and frozen flags are *derived* by folding the log
through ``_State.apply``.  A live ``_State`` is kept as a cache so that reads
are O(1), but it is only ever advanced by the same ``apply`` function that
replay uses, so it cannot drift from the log.

Operations are numbered from 1 in the order they were accepted.  Any account's
balance as it stood after operation ``n`` can be recovered with
``balance_at``; the full log is available via ``history`` / ``events`` and a
ledger can be rebuilt from a log with ``Ledger.from_events``.

There is deliberately no API for editing or removing past events: corrections
are made by appending new operations.  Amounts are integer cents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


# --------------------------------------------------------------------------
# Events (the log records)
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Event:
    """Base class for all operation records.  Instances are immutable."""

    def accounts(self) -> tuple[str, ...]:
        """Account ids this event explicitly references (empty = ledger-wide)."""
        return ()


@dataclass(frozen=True, slots=True)
class AccountOpened(Event):
    account_id: str
    initial: int

    def accounts(self) -> tuple[str, ...]:
        return (self.account_id,)


@dataclass(frozen=True, slots=True)
class Deposited(Event):
    account_id: str
    amount: int

    def accounts(self) -> tuple[str, ...]:
        return (self.account_id,)


@dataclass(frozen=True, slots=True)
class Withdrawn(Event):
    account_id: str
    amount: int

    def accounts(self) -> tuple[str, ...]:
        return (self.account_id,)


@dataclass(frozen=True, slots=True)
class Transferred(Event):
    src: str
    dst: str
    amount: int

    def accounts(self) -> tuple[str, ...]:
        return (self.src, self.dst)


@dataclass(frozen=True, slots=True)
class BatchTransferred(Event):
    transfers: tuple[tuple[str, str, int], ...]

    def accounts(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for src, dst, _ in self.transfers:
            seen.setdefault(src)
            seen.setdefault(dst)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class InterestApplied(Event):
    """Ledger-wide: affects every account with a positive balance."""

    basis_points: int


@dataclass(frozen=True, slots=True)
class AccountClosed(Event):
    account_id: str

    def accounts(self) -> tuple[str, ...]:
        return (self.account_id,)


@dataclass(frozen=True, slots=True)
class Frozen(Event):
    account_id: str

    def accounts(self) -> tuple[str, ...]:
        return (self.account_id,)


@dataclass(frozen=True, slots=True)
class Unfrozen(Event):
    account_id: str

    def accounts(self) -> tuple[str, ...]:
        return (self.account_id,)


@dataclass(frozen=True, slots=True)
class OverdraftLimitSet(Event):
    account_id: str
    limit: int

    def accounts(self) -> tuple[str, ...]:
        return (self.account_id,)


# --------------------------------------------------------------------------
# Projection: fold events into balances / frozen flags
# --------------------------------------------------------------------------


def _check_amount(amount: int, what: str = "amount") -> None:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError(f"{what} must be an int, got {type(amount).__name__}")
    if amount < 0:
        raise ValueError(f"{what} must be non-negative, got {amount}")


class _State:
    """Derived state.  ``apply`` validates fully before mutating anything, so a
    rejected event leaves the state untouched (all-or-nothing)."""

    __slots__ = ("balances", "frozen", "overdrafts")

    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.frozen: set[str] = set()
        self.overdrafts: dict[str, int] = {}  # absent => 0

    def overdraft_limit(self, account_id: str) -> int:
        return self.overdrafts.get(account_id, 0)

    # -- validation helpers ---------------------------------------------

    def require(self, account_id: str) -> None:
        if account_id not in self.balances:
            raise UnknownAccount(account_id)

    def _check_debit(
        self, balances: dict[str, int], account_id: str, amount: int, verb: str
    ) -> None:
        if account_id in self.frozen:
            raise PermissionError(f"account {account_id!r} is frozen; cannot {verb}")
        floor = -self.overdraft_limit(account_id)
        if balances[account_id] - amount < floor:
            raise InsufficientFunds(
                f"account {account_id!r} has {balances[account_id]} "
                f"(overdraft limit {-floor}), cannot {verb} {amount}"
            )

    # -- fold -------------------------------------------------------------

    def apply(self, event: Event) -> None:
        match event:
            case AccountOpened(account_id=aid, initial=initial):
                _check_amount(initial, "initial")
                if aid in self.balances:
                    raise ValueError(f"account already exists: {aid!r}")
                self.balances[aid] = initial

            case Deposited(account_id=aid, amount=amount):
                _check_amount(amount)
                self.require(aid)
                self.balances[aid] += amount

            case Withdrawn(account_id=aid, amount=amount):
                _check_amount(amount)
                self.require(aid)
                self._check_debit(self.balances, aid, amount, "withdraw")
                self.balances[aid] -= amount

            case Transferred(src=src, dst=dst, amount=amount):
                _check_amount(amount)
                self.require(src)
                self.require(dst)
                self._check_debit(self.balances, src, amount, "transfer")
                self.balances[src] -= amount
                self.balances[dst] += amount

            case BatchTransferred(transfers=transfers):
                # Dry-run every leg against a working copy; commit only if all pass.
                work = dict(self.balances)
                for src, dst, amount in transfers:
                    _check_amount(amount)
                    self.require(src)
                    self.require(dst)
                    self._check_debit(work, src, amount, "transfer")
                    work[src] -= amount
                    work[dst] += amount
                self.balances = work

            case InterestApplied(basis_points=bp):
                _check_amount(bp, "basis_points")
                for aid, bal in self.balances.items():
                    if bal > 0:
                        self.balances[aid] = bal + (bal * bp) // 10_000

            case AccountClosed(account_id=aid):
                self.require(aid)
                if self.balances[aid] != 0:
                    raise ValueError(
                        f"account {aid!r} has non-zero balance "
                        f"{self.balances[aid]}; cannot close"
                    )
                del self.balances[aid]
                self.frozen.discard(aid)
                self.overdrafts.pop(aid, None)

            case Frozen(account_id=aid):
                self.require(aid)
                self.frozen.add(aid)

            case Unfrozen(account_id=aid):
                self.require(aid)
                self.frozen.discard(aid)

            case OverdraftLimitSet(account_id=aid, limit=limit):
                _check_amount(limit, "limit")
                self.require(aid)
                self.overdrafts[aid] = limit

            case _:
                raise TypeError(f"unknown event type: {type(event).__name__}")


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


class Ledger:
    def __init__(self) -> None:
        self._log: list[Event] = []
        self._state = _State()

    @classmethod
    def from_events(cls, events: Iterable[Event]) -> "Ledger":
        """Rebuild a ledger by replaying a log (e.g. one obtained from ``events()``)."""
        ledger = cls()
        for event in events:
            ledger._commit(event)
        return ledger

    def _commit(self, event: Event) -> None:
        # ``apply`` raises before mutating on any failure, so the log and the
        # cached state always advance together or not at all.
        self._state.apply(event)
        self._log.append(event)

    # -- mutating operations (each appends exactly one event) ---------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        self._commit(AccountOpened(account_id, initial))

    def deposit(self, account_id: str, amount: int) -> None:
        self._commit(Deposited(account_id, amount))

    def withdraw(self, account_id: str, amount: int) -> None:
        self._commit(Withdrawn(account_id, amount))

    def transfer(self, src: str, dst: str, amount: int) -> None:
        self._commit(Transferred(src, dst, amount))

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply all transfers atomically: if any leg would fail, none are applied."""
        self._commit(BatchTransferred(tuple((s, d, a) for s, d, a in transfers)))

    def apply_interest(self, basis_points: int) -> None:
        """Credit every positively-balanced account with floor(balance * bp / 10000)."""
        self._commit(InterestApplied(basis_points))

    def close_account(self, account_id: str) -> None:
        self._commit(AccountClosed(account_id))

    def freeze(self, account_id: str) -> None:
        """Block withdrawals and outgoing transfers.  Idempotent; always recorded."""
        self._commit(Frozen(account_id))

    def unfreeze(self, account_id: str) -> None:
        self._commit(Unfrozen(account_id))

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow withdrawals/outgoing transfers down to ``-limit`` (default 0)."""
        self._commit(OverdraftLimitSet(account_id, limit))

    # -- current-state reads (served from the cache) -----------------------

    def balance(self, account_id: str) -> int:
        self._state.require(account_id)
        return self._state.balances[account_id]

    def accounts(self) -> list[str]:
        return sorted(self._state.balances)

    def balances(self) -> dict[str, int]:
        """A fresh dict of every current balance, keyed by account id."""
        return dict(self._state.balances)

    def overdraft_limit(self, account_id: str) -> int:
        self._state.require(account_id)
        return self._state.overdraft_limit(account_id)

    def total_assets(self) -> int:
        return sum(self._state.balances.values())

    def is_frozen(self, account_id: str) -> bool:
        self._state.require(account_id)
        return account_id in self._state.frozen

    # -- audit / history ---------------------------------------------------

    def op_count(self) -> int:
        """Number of operations accepted so far (operation numbers run 1..op_count)."""
        return len(self._log)

    def events(self) -> tuple[Event, ...]:
        """The complete, ordered, immutable operation log."""
        return tuple(self._log)

    def history(self, account_id: str | None = None) -> list[tuple[int, Event]]:
        """``(op_number, event)`` pairs in order.

        With ``account_id``, only events touching that account are returned.
        Ledger-wide events (interest) are included because they may affect it.
        """
        return [
            (n, ev)
            for n, ev in enumerate(self._log, start=1)
            if account_id is None or not ev.accounts() or account_id in ev.accounts()
        ]

    def _replay(self, upto: int) -> _State:
        state = _State()
        for event in self._log[:upto]:
            state.apply(event)
        return state

    def _check_op_number(self, op_number: int) -> None:
        if isinstance(op_number, bool) or not isinstance(op_number, int):
            raise ValueError("op_number must be an int")
        if not 0 <= op_number <= len(self._log):
            raise ValueError(f"op_number {op_number} out of range 0..{len(self._log)}")

    def balance_at(self, account_id: str, op_number: int) -> int:
        """Balance of ``account_id`` immediately after operation ``op_number``.

        ``op_number`` 0 is the empty ledger.  Raises ``UnknownAccount`` if the
        account did not exist at that point (not yet opened, or already closed).
        """
        self._check_op_number(op_number)
        state = self._replay(op_number)
        state.require(account_id)
        return state.balances[account_id]

    def balances_at(self, op_number: int) -> dict[str, int]:
        """All balances as they stood immediately after operation ``op_number``."""
        self._check_op_number(op_number)
        return dict(self._replay(op_number).balances)

    def __iter__(self) -> Iterator[Event]:
        return iter(self._log)
