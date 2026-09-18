"""In-memory account ledger (Approach B: snapshot state).

The ledger keeps a single mapping of account id -> current balance (integer
cents) and mutates it in place. No operation log is kept. Multi-step
operations that must be atomic are applied to a working copy of the mapping
and committed only once every step has succeeded.
"""

from __future__ import annotations


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


def _check_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError(f"amount must be an integer number of cents, got {amount!r}")
    if amount < 0:
        raise ValueError(f"amount must be non-negative, got {amount}")


class Ledger:
    def __init__(self) -> None:
        self._balances: dict[str, int] = {}
        self._frozen: set[str] = set()
        self._overdraft: dict[str, int] = {}

    # -- helpers -----------------------------------------------------------

    def _require(self, account_id: str, balances: dict[str, int] | None = None) -> int:
        table = self._balances if balances is None else balances
        try:
            return table[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def _require_unfrozen(self, account_id: str) -> None:
        if account_id in self._frozen:
            raise PermissionError(f"account {account_id!r} is frozen")

    def _available(self, account_id: str, current: int) -> int:
        """Amount that may leave the account: balance plus overdraft limit."""
        return current + self._overdraft.get(account_id, 0)

    def _apply_transfer(
        self, balances: dict[str, int], src: str, dst: str, amount: int
    ) -> None:
        """Apply one transfer to ``balances`` in place, validating first.

        Raises before mutating anything, so a caller working on a copy can
        discard it on failure.
        """
        _check_amount(amount)
        src_balance = self._require(src, balances)
        dst_balance = self._require(dst, balances)
        self._require_unfrozen(src)
        if amount > self._available(src, src_balance):
            raise InsufficientFunds(
                f"account {src!r} has {src_balance} (overdraft limit "
                f"{self.overdraft_limit(src)}), cannot transfer {amount}"
            )
        if src == dst:
            return
        balances[src] = src_balance - amount
        balances[dst] = dst_balance + amount

    # -- public interface --------------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        _check_amount(initial)
        if account_id in self._balances:
            raise ValueError(f"account already exists: {account_id!r}")
        self._balances[account_id] = initial

    def deposit(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        self._balances[account_id] = self._require(account_id) + amount

    def withdraw(self, account_id: str, amount: int) -> None:
        _check_amount(amount)
        current = self._require(account_id)
        self._require_unfrozen(account_id)
        if amount > self._available(account_id, current):
            raise InsufficientFunds(
                f"account {account_id!r} has {current} (overdraft limit "
                f"{self.overdraft_limit(account_id)}), cannot withdraw {amount}"
            )
        self._balances[account_id] = current - amount

    def transfer(self, src: str, dst: str, amount: int) -> None:
        self._apply_transfer(self._balances, src, dst, amount)

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply every transfer, or none of them if any would fail."""
        working = dict(self._balances)
        for src, dst, amount in transfers:
            self._apply_transfer(working, src, dst, amount)
        self._balances = working

    def balance(self, account_id: str) -> int:
        return self._require(account_id)

    def accounts(self) -> list[str]:
        return sorted(self._balances)

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with floor(balance * bp / 10000).

        Only positive balances earn interest; zero balances are unchanged.
        """
        _check_amount(basis_points)
        for account_id, current in self._balances.items():
            if current > 0:
                self._balances[account_id] = current + (current * basis_points) // 10_000

    def close_account(self, account_id: str) -> None:
        current = self._require(account_id)
        if current != 0:
            raise ValueError(
                f"account {account_id!r} has balance {current}; must be 0 to close"
            )
        del self._balances[account_id]
        self._frozen.discard(account_id)
        self._overdraft.pop(account_id, None)

    def total_assets(self) -> int:
        return sum(self._balances.values())

    def freeze(self, account_id: str) -> None:
        self._require(account_id)
        self._frozen.add(account_id)

    def unfreeze(self, account_id: str) -> None:
        self._require(account_id)
        self._frozen.discard(account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._require(account_id)
        return account_id in self._frozen

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow the balance to go as low as ``-limit`` on withdrawals/transfers."""
        _check_amount(limit)
        self._require(account_id)
        self._overdraft[account_id] = limit

    def overdraft_limit(self, account_id: str) -> int:
        self._require(account_id)
        return self._overdraft.get(account_id, 0)

    def balances(self) -> dict[str, int]:
        """Return a fresh copy of all current balances."""
        return dict(self._balances)
