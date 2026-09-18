"""Approach B: snapshot state. Current balances live in a dict and are mutated in place.
No operation log is kept."""
from __future__ import annotations


class InsufficientFunds(Exception):
    pass


class UnknownAccount(Exception):
    pass


def _check_amount(amount: int) -> None:
    if amount < 0:
        raise ValueError("negative amount")


class Ledger:
    def __init__(self):
        self._balances: dict[str, int] = {}
        self._frozen: set[str] = set()
        self._overdraft: dict[str, int] = {}

    def _require(self, account_id: str) -> None:
        if account_id not in self._balances:
            raise UnknownAccount(account_id)

    def _check_debit(self, account_id: str, amount: int) -> None:
        self._require(account_id)
        if account_id in self._frozen:
            raise PermissionError("account frozen: %s" % account_id)
        if self._balances[account_id] - amount < -self._overdraft.get(account_id, 0):
            raise InsufficientFunds(account_id)

    # ---- T1 ----------------------------------------------------------------------------
    def open_account(self, account_id: str, initial: int = 0) -> None:
        _check_amount(initial)
        if account_id in self._balances:
            raise ValueError("account exists: %s" % account_id)
        self._balances[account_id] = initial
        self._overdraft[account_id] = 0

    def deposit(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._require(account_id)
        self._balances[account_id] += amount

    def withdraw(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._check_debit(account_id, amount)
        self._balances[account_id] -= amount

    def transfer(self, src: str, dst: str, amount: int) -> None:
        _check_amount(amount)
        self._require(dst)
        self._check_debit(src, amount)
        self._balances[src] -= amount
        self._balances[dst] += amount

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

    def close_account(self, account_id: str) -> None:
        self._require(account_id)
        if self._balances[account_id] != 0:
            raise ValueError("balance not zero")
        del self._balances[account_id]
        self._frozen.discard(account_id)
        self._overdraft.pop(account_id, None)

    def total_assets(self) -> int:
        return sum(self._balances.values())

    # ---- T3 ----------------------------------------------------------------------------
    def freeze(self, account_id: str) -> None:
        self._require(account_id)
        self._frozen.add(account_id)

    def unfreeze(self, account_id: str) -> None:
        self._require(account_id)
        self._frozen.discard(account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._require(account_id)
        return account_id in self._frozen

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        # apply to a copy; swap in only if everything succeeded
        saved = dict(self._balances)
        try:
            for src, dst, amount in transfers:
                self.transfer(src, dst, amount)
        except Exception:
            self._balances = saved
            raise

    # ---- T4 ----------------------------------------------------------------------------
    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        _check_amount(limit)
        self._require(account_id)
        self._overdraft[account_id] = limit

    def overdraft_limit(self, account_id: str) -> int:
        self._require(account_id)
        return self._overdraft.get(account_id, 0)

    def balances(self) -> dict[str, int]:
        return dict(self._balances)
