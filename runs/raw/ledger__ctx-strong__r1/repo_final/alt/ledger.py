"""Approach A: event sourcing. The append-only list of operation records is the source of
truth; balances (and frozen flags, overdraft limits, open accounts) are derived by folding
over the log on every read."""
from __future__ import annotations
from dataclasses import dataclass, field


class InsufficientFunds(Exception):
    pass


class UnknownAccount(Exception):
    pass


@dataclass
class _State:
    balances: dict[str, int] = field(default_factory=dict)
    frozen: set[str] = field(default_factory=set)
    overdraft: dict[str, int] = field(default_factory=dict)


def _apply(state: _State, ev: tuple) -> _State:
    """Fold one event into state. Raises if the event is not valid in this state."""
    kind = ev[0]
    b = state.balances
    if kind == "opened":
        _, acct, initial = ev
        if acct in b:
            raise ValueError("account exists: %s" % acct)
        b[acct] = initial
        state.overdraft[acct] = 0
    elif kind == "deposited":
        _, acct, amount = ev
        _require(state, acct)
        b[acct] += amount
    elif kind == "withdrawn":
        _, acct, amount = ev
        _debit(state, acct, amount)
    elif kind == "transferred":
        _, src, dst, amount = ev
        _require(state, dst)
        _debit(state, src, amount)
        b[dst] += amount
    elif kind == "interest":
        _, bp = ev
        for acct, bal in b.items():
            if bal > 0:
                b[acct] = bal + bal * bp // 10000
    elif kind == "closed":
        _, acct = ev
        _require(state, acct)
        if b[acct] != 0:
            raise ValueError("balance not zero")
        del b[acct]
        state.frozen.discard(acct)
        state.overdraft.pop(acct, None)
    elif kind == "frozen":
        _require(state, ev[1])
        state.frozen.add(ev[1])
    elif kind == "unfrozen":
        _require(state, ev[1])
        state.frozen.discard(ev[1])
    elif kind == "overdraft_set":
        _, acct, limit = ev
        _require(state, acct)
        state.overdraft[acct] = limit
    else:
        raise ValueError("unknown event %r" % (kind,))
    return state


def _require(state: _State, acct: str) -> None:
    if acct not in state.balances:
        raise UnknownAccount(acct)


def _debit(state: _State, acct: str, amount: int) -> None:
    _require(state, acct)
    if acct in state.frozen:
        raise PermissionError("account frozen: %s" % acct)
    if state.balances[acct] - amount < -state.overdraft.get(acct, 0):
        raise InsufficientFunds(acct)
    state.balances[acct] -= amount


def _check_amount(amount: int) -> None:
    if amount < 0:
        raise ValueError("negative amount")


class Ledger:
    def __init__(self):
        self._events: list[tuple] = []

    # ---- derived state -----------------------------------------------------------------
    def _state(self) -> _State:
        state = _State()
        for ev in self._events:
            _apply(state, ev)
        return state

    def _append(self, *events: tuple) -> None:
        """Validate events against the replayed state, then append them atomically."""
        state = self._state()
        for ev in events:
            _apply(state, ev)      # raises before anything is appended
        self._events.extend(events)

    # ---- T1 ----------------------------------------------------------------------------
    def open_account(self, account_id: str, initial: int = 0) -> None:
        _check_amount(initial)
        self._append(("opened", account_id, initial))

    def deposit(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._append(("deposited", account_id, amount))

    def withdraw(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._append(("withdrawn", account_id, amount))

    def transfer(self, src: str, dst: str, amount: int) -> None:
        _check_amount(amount)
        self._append(("transferred", src, dst, amount))

    def balance(self, account_id: str) -> int:
        state = self._state()
        _require(state, account_id)
        return state.balances[account_id]

    def accounts(self) -> list[str]:
        return sorted(self._state().balances)

    # ---- T2 ----------------------------------------------------------------------------
    def apply_interest(self, basis_points: int) -> None:
        _check_amount(basis_points)
        self._append(("interest", basis_points))

    def close_account(self, account_id: str) -> None:
        self._append(("closed", account_id))

    def total_assets(self) -> int:
        return sum(self._state().balances.values())

    # ---- T3 ----------------------------------------------------------------------------
    def freeze(self, account_id: str) -> None:
        self._append(("frozen", account_id))

    def unfreeze(self, account_id: str) -> None:
        self._append(("unfrozen", account_id))

    def is_frozen(self, account_id: str) -> bool:
        state = self._state()
        _require(state, account_id)
        return account_id in state.frozen

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        for _, _, amount in transfers:
            _check_amount(amount)
        self._append(*[("transferred", s, d, a) for s, d, a in transfers])

    # ---- T4 ----------------------------------------------------------------------------
    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        _check_amount(limit)
        self._append(("overdraft_set", account_id, limit))

    def overdraft_limit(self, account_id: str) -> int:
        state = self._state()
        _require(state, account_id)
        return state.overdraft.get(account_id, 0)

    def balances(self) -> dict[str, int]:
        return dict(self._state().balances)

    # ---- audit helpers (natural with event sourcing) ------------------------------------
    def history(self) -> list[tuple]:
        return list(self._events)
