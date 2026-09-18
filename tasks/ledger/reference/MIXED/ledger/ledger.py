"""Deliberately MIXED reference (not a real design): both approaches are live at once for the
same responsibility.

* Approach B is live: ``self._balances`` is a plain dict that ``deposit``/``withdraw``/``transfer``
  /``apply_interest`` mutate in place, and ``balance()`` / ``accounts()`` read it directly.
* Approach A is also live: every operation appends a record to ``self._events``, and
  ``total_assets()``, ``balances()`` and ``batch_transfer()`` (truncate-and-replay rollback) compute
  balances by folding over the event list instead of reading the dict.

This is the sort of thing an agent produces when it starts with snapshot state and then, tempted
mid-project by "just record every operation into a list and rebuild balances from it", bolts an
event log on without removing the mutable dict.
"""
from __future__ import annotations


class InsufficientFunds(Exception):
    pass


class UnknownAccount(Exception):
    pass


def _check_amount(amount: int) -> None:
    if amount < 0:
        raise ValueError("negative amount")


def _replay(events: list[tuple]) -> tuple[dict[str, int], set[str], dict[str, int]]:
    """Fold the event log into (balances, frozen, overdraft). Event-sourced view of the state."""
    balances: dict[str, int] = {}
    frozen: set[str] = set()
    overdraft: dict[str, int] = {}
    for ev in events:
        kind = ev[0]
        if kind == "opened":
            balances[ev[1]] = ev[2]
            overdraft[ev[1]] = 0
        elif kind == "deposited":
            balances[ev[1]] += ev[2]
        elif kind == "withdrawn":
            balances[ev[1]] -= ev[2]
        elif kind == "transferred":
            balances[ev[1]] -= ev[3]
            balances[ev[2]] += ev[3]
        elif kind == "interest":
            for acct, bal in balances.items():
                if bal > 0:
                    balances[acct] = bal + bal * ev[1] // 10000
        elif kind == "closed":
            del balances[ev[1]]
            frozen.discard(ev[1])
            overdraft.pop(ev[1], None)
        elif kind == "frozen":
            frozen.add(ev[1])
        elif kind == "unfrozen":
            frozen.discard(ev[1])
        elif kind == "overdraft_set":
            overdraft[ev[1]] = ev[2]
    return balances, frozen, overdraft


class Ledger:
    def __init__(self):
        self._balances: dict[str, int] = {}     # snapshot state, mutated in place (B)
        self._frozen: set[str] = set()
        self._overdraft: dict[str, int] = {}
        self._events: list[tuple] = []          # append-only operation log (A)

    def _require(self, account_id: str) -> None:
        if account_id not in self._balances:
            raise UnknownAccount(account_id)

    def _check_debit(self, account_id: str, amount: int) -> None:
        self._require(account_id)
        if account_id in self._frozen:
            raise PermissionError("account frozen: %s" % account_id)
        if self._balances[account_id] - amount < -self._overdraft.get(account_id, 0):
            raise InsufficientFunds(account_id)

    # ---- T1: snapshot dict mutated in place, event appended alongside -------------------
    def open_account(self, account_id: str, initial: int = 0) -> None:
        _check_amount(initial)
        if account_id in self._balances:
            raise ValueError("account exists: %s" % account_id)
        self._balances[account_id] = initial
        self._overdraft[account_id] = 0
        self._events.append(("opened", account_id, initial))

    def deposit(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._require(account_id)
        self._balances[account_id] += amount
        self._events.append(("deposited", account_id, amount))

    def withdraw(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._check_debit(account_id, amount)
        self._balances[account_id] -= amount
        self._events.append(("withdrawn", account_id, amount))

    def transfer(self, src: str, dst: str, amount: int) -> None:
        _check_amount(amount)
        self._require(dst)
        self._check_debit(src, amount)
        self._balances[src] -= amount
        self._balances[dst] += amount
        self._events.append(("transferred", src, dst, amount))

    def balance(self, account_id: str) -> int:
        self._require(account_id)
        return self._balances[account_id]

    def accounts(self) -> list[str]:
        return sorted(self._balances)

    # ---- T2 ----------------------------------------------------------------------------
    def apply_interest(self, basis_points: int) -> None:
        _check_amount(basis_points)
        for acct, bal in self._balances.items():
            if bal > 0:
                self._balances[acct] = bal + bal * basis_points // 10000
        self._events.append(("interest", basis_points))

    def close_account(self, account_id: str) -> None:
        self._require(account_id)
        if self._balances[account_id] != 0:
            raise ValueError("balance not zero")
        del self._balances[account_id]
        self._frozen.discard(account_id)
        self._overdraft.pop(account_id, None)
        self._events.append(("closed", account_id))

    def total_assets(self) -> int:
        # reads the event log, not the dict
        balances, _, _ = _replay(self._events)
        return sum(balances.values())

    # ---- T3 ----------------------------------------------------------------------------
    def freeze(self, account_id: str) -> None:
        self._require(account_id)
        self._frozen.add(account_id)
        self._events.append(("frozen", account_id))

    def unfreeze(self, account_id: str) -> None:
        self._require(account_id)
        self._frozen.discard(account_id)
        self._events.append(("unfrozen", account_id))

    def is_frozen(self, account_id: str) -> bool:
        self._require(account_id)
        return account_id in self._frozen

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        # roll back by truncating the log and rebuilding the dict from the events
        mark = len(self._events)
        try:
            for src, dst, amount in transfers:
                self.transfer(src, dst, amount)
        except Exception:
            del self._events[mark:]
            self._balances, self._frozen, self._overdraft = _replay(self._events)
            raise

    # ---- T4 ----------------------------------------------------------------------------
    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        _check_amount(limit)
        self._require(account_id)
        self._overdraft[account_id] = limit
        self._events.append(("overdraft_set", account_id, limit))

    def overdraft_limit(self, account_id: str) -> int:
        self._require(account_id)
        return self._overdraft.get(account_id, 0)

    def balances(self) -> dict[str, int]:
        # derived from the event log
        balances, _, _ = _replay(self._events)
        return balances

    def history(self) -> list[tuple]:
        return list(self._events)
