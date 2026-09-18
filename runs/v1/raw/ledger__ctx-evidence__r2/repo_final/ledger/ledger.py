"""In-memory account ledger.

Design: event sourcing (SPEC.md "Approach A").

The source of truth is ``Ledger._log``, an append-only list of ``Event``
records. The current balances and frozen flags live in a cached projection
(``Ledger._state``) that is updated by applying each event as it is appended;
the projection can be rebuilt at any time by folding the log from the start,
and ``balance_at`` folds a prefix of the log to answer "what was the balance
after operation N?".

Every public mutating method follows the same pattern: build an event,
validate it against the current projection, append it to the log, then apply
it to the projection. Because validation happens before the append, replaying
the log never fails, and a rejected operation leaves both the log and the
projection untouched. Corrections are therefore always new events; nothing
ever edits history.

Amounts are integer cents.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


@dataclass(frozen=True, slots=True)
class Event:
    """One immutable operation record in the ledger's log.

    ``seq`` is the 1-based operation number. ``payload`` is kind-specific:

    ==================  ===========================================
    kind                payload
    ==================  ===========================================
    ``open``            ``(account_id, initial)``
    ``deposit``         ``(account_id, amount)``
    ``withdraw``        ``(account_id, amount)``
    ``transfer``        ``(src, dst, amount)``
    ``batch_transfer``  ``((src, dst, amount), ...)``
    ``apply_interest``  ``(basis_points,)``
    ``close``           ``(account_id,)``
    ``set_overdraft``   ``(account_id, limit)``
    ``freeze``          ``(account_id,)``
    ``unfreeze``        ``(account_id,)``
    ==================  ===========================================
    """

    seq: int
    kind: str
    payload: tuple

    def touches(self, account_id: str) -> bool:
        """True if this event can affect ``account_id``'s balance or status."""
        if self.kind == "apply_interest":
            return True
        if self.kind == "batch_transfer":
            return any(account_id in (s, d) for s, d, _ in self.payload)
        if self.kind == "transfer":
            return account_id in self.payload[:2]
        return self.payload[0] == account_id


@dataclass(slots=True)
class _State:
    """Cached projection of the log: current balances and frozen flags."""

    balances: dict[str, int] = field(default_factory=dict)
    frozen: set[str] = field(default_factory=set)
    overdraft: dict[str, int] = field(default_factory=dict)  # absent -> 0

    def copy(self) -> _State:
        return _State(dict(self.balances), set(self.frozen), dict(self.overdraft))

    # -- lookups -----------------------------------------------------------

    def require(self, account_id: str) -> int:
        try:
            return self.balances[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def require_debitable(self, account_id: str, amount: int) -> int:
        """Return the balance if ``amount`` may be taken out of the account."""
        current = self.require(account_id)
        if account_id in self.frozen:
            raise PermissionError(f"account {account_id!r} is frozen")
        limit = self.overdraft.get(account_id, 0)
        if amount > current + limit:
            raise InsufficientFunds(
                f"account {account_id!r}: balance {current}, overdraft limit "
                f"{limit}, requested {amount}"
            )
        return current

    # -- event application -------------------------------------------------

    def apply(self, event: Event) -> None:
        """Validate ``event`` against this state and, if valid, apply it.

        Each branch checks every precondition before mutating anything, so a
        raised exception leaves the state exactly as it was.
        """
        kind, p = event.kind, event.payload
        if kind == "open":
            account_id, initial = p
            _check_amount(initial)
            if account_id in self.balances:
                raise ValueError(f"account already exists: {account_id!r}")
            self.balances[account_id] = initial
        elif kind == "deposit":
            account_id, amount = p
            _check_amount(amount)
            self.balances[account_id] = self.require(account_id) + amount
        elif kind == "withdraw":
            account_id, amount = p
            _check_amount(amount)
            current = self.require_debitable(account_id, amount)
            self.balances[account_id] = current - amount
        elif kind == "transfer":
            self._transfer(*p)
        elif kind == "batch_transfer":
            # Transfers within a batch are applied in order, so later ones
            # may spend funds received from earlier ones. Validate the whole
            # batch on a scratch copy, then commit the copy.
            scratch = self.copy()
            for src, dst, amount in p:
                scratch._transfer(src, dst, amount)
            self.balances, self.frozen, self.overdraft = (
                scratch.balances, scratch.frozen, scratch.overdraft
            )
        elif kind == "apply_interest":
            (bp,) = p
            _check_amount(bp)
            for account_id, current in self.balances.items():
                if current > 0:
                    self.balances[account_id] = current + (current * bp) // 10_000
        elif kind == "close":
            (account_id,) = p
            if self.require(account_id) != 0:
                raise ValueError(
                    f"account {account_id!r} has non-zero balance; cannot close"
                )
            del self.balances[account_id]
            self.frozen.discard(account_id)
            self.overdraft.pop(account_id, None)
        elif kind == "set_overdraft":
            account_id, limit = p
            _check_amount(limit)
            self.require(account_id)
            self.overdraft[account_id] = limit
        elif kind == "freeze":
            (account_id,) = p
            self.require(account_id)
            self.frozen.add(account_id)
        elif kind == "unfreeze":
            (account_id,) = p
            self.require(account_id)
            self.frozen.discard(account_id)
        else:  # pragma: no cover - guards against corrupt logs
            raise ValueError(f"unknown event kind: {kind!r}")

    def _transfer(self, src: str, dst: str, amount: int) -> None:
        _check_amount(amount)
        src_balance = self.require_debitable(src, amount)
        self.require(dst)
        self.balances[src] = src_balance - amount
        self.balances[dst] += amount


def _check_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError(f"amount must be an int, got {type(amount).__name__}")
    if amount < 0:
        raise ValueError(f"amount must be non-negative, got {amount}")


class Ledger:
    def __init__(self) -> None:
        self._log: list[Event] = []
        self._state = _State()

    def _commit(self, kind: str, *payload) -> None:
        """Validate and apply a new event, appending it to the log."""
        event = Event(len(self._log) + 1, kind, payload)
        self._state.apply(event)  # raises without touching state if invalid
        self._log.append(event)

    # -- account lifecycle -------------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        self._commit("open", account_id, initial)

    def close_account(self, account_id: str) -> None:
        self._commit("close", account_id)

    def freeze(self, account_id: str) -> None:
        self._commit("freeze", account_id)

    def unfreeze(self, account_id: str) -> None:
        self._commit("unfreeze", account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._state.require(account_id)
        return account_id in self._state.frozen

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow debits to take the balance down to ``-limit`` (default 0).

        Lowering the limit below an existing overdraft is allowed; it only
        constrains future debits.
        """
        self._commit("set_overdraft", account_id, limit)

    def overdraft_limit(self, account_id: str) -> int:
        self._state.require(account_id)
        return self._state.overdraft.get(account_id, 0)

    # -- money movement ----------------------------------------------------

    def deposit(self, account_id: str, amount: int) -> None:
        self._commit("deposit", account_id, amount)

    def withdraw(self, account_id: str, amount: int) -> None:
        self._commit("withdraw", account_id, amount)

    def transfer(self, src: str, dst: str, amount: int) -> None:
        self._commit("transfer", src, dst, amount)

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply all transfers in order as one operation, or none at all."""
        self._commit("batch_transfer", *(tuple(t) for t in transfers))

    def apply_interest(self, basis_points: int) -> None:
        """Credit every positive balance with floor(balance * bp / 10000)."""
        self._commit("apply_interest", basis_points)

    # -- queries -----------------------------------------------------------

    def balance(self, account_id: str) -> int:
        return self._state.require(account_id)

    def accounts(self) -> list[str]:
        return sorted(self._state.balances)

    def balances(self) -> dict[str, int]:
        """A fresh dict of every account's current balance."""
        return dict(self._state.balances)

    def total_assets(self) -> int:
        return sum(self._state.balances.values())

    # -- audit -------------------------------------------------------------

    @property
    def operation_count(self) -> int:
        """Number of operations recorded so far (the latest ``Event.seq``)."""
        return len(self._log)

    def history(self, account_id: str | None = None) -> list[Event]:
        """All operations in order, optionally only those touching one account."""
        if account_id is None:
            return list(self._log)
        return [e for e in self._log if e.touches(account_id)]

    def balance_at(self, account_id: str, op_number: int) -> int:
        """Balance of ``account_id`` immediately after operation ``op_number``.

        ``op_number`` is 1-based; ``0`` means "before any operation". Raises
        ``UnknownAccount`` if the account did not exist at that point and
        ``ValueError`` if ``op_number`` is out of range.
        """
        if not 0 <= op_number <= len(self._log):
            raise ValueError(
                f"op_number must be in [0, {len(self._log)}], got {op_number}"
            )
        state = _State()
        for event in self._log[:op_number]:
            state.apply(event)
        return state.require(account_id)
