"""In-memory account ledger (Approach B: snapshot state).

The ledger holds the current balance of every account in a plain dict and
mutates it in place. No operation log is kept. All amounts are integer cents.
Frozen account ids are tracked in a separate set, and per-account overdraft
limits in a separate dict (absent means 0).
"""

from __future__ import annotations


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the source balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


class Ledger:
    def __init__(self) -> None:
        self._balances: dict[str, int] = {}
        self._frozen: set[str] = set()
        self._overdraft: dict[str, int] = {}

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _check_amount(amount: int) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError(f"amount must be an int, got {type(amount).__name__}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

    def _get(self, account_id: str) -> int:
        try:
            return self._balances[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def _check_not_frozen(self, account_id: str) -> None:
        if account_id in self._frozen:
            raise PermissionError(f"account is frozen: {account_id!r}")

    def _available(self, account_id: str, current: int) -> int:
        """Largest amount that may currently be debited from the account.

        Balance plus overdraft limit, clamped at zero so an account already
        past its (lowered) limit still accepts zero-amount debits but no more.
        """
        return max(current + self._overdraft.get(account_id, 0), 0)

    def _apply_transfer(
        self, balances: dict[str, int], src: str, dst: str, amount: int
    ) -> None:
        """Validate and apply one transfer against ``balances`` in place.

        Raises before mutating anything, so a failure leaves ``balances``
        untouched. ``balances`` may be the live dict or a scratch copy.
        """
        self._check_amount(amount)
        if src not in balances:
            raise UnknownAccount(src)
        if dst not in balances:
            raise UnknownAccount(dst)
        self._check_not_frozen(src)
        src_balance = balances[src]
        if amount > self._available(src, src_balance):
            raise InsufficientFunds(
                f"cannot transfer {amount} from {src!r} "
                f"(balance {src_balance}, overdraft limit {self.overdraft_limit(src)})"
            )
        balances[src] = src_balance - amount
        balances[dst] += amount

    # -- public interface --------------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        if account_id in self._balances:
            raise ValueError(f"account already exists: {account_id!r}")
        self._check_amount(initial)
        self._balances[account_id] = initial

    def deposit(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        current = self._get(account_id)
        self._balances[account_id] = current + amount

    def withdraw(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        current = self._get(account_id)
        self._check_not_frozen(account_id)
        if amount > self._available(account_id, current):
            raise InsufficientFunds(
                f"cannot withdraw {amount} from {account_id!r} "
                f"(balance {current}, overdraft limit {self.overdraft_limit(account_id)})"
            )
        self._balances[account_id] = current - amount

    def transfer(self, src: str, dst: str, amount: int) -> None:
        # _apply_transfer validates everything before touching state, so the
        # operation is all-or-nothing.
        self._apply_transfer(self._balances, src, dst, amount)

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply every transfer in order, atomically.

        Transfers are applied to a scratch copy of the balances so that later
        transfers can spend funds received from earlier ones. If any transfer
        fails, the copy is discarded and the ledger is unchanged; the original
        exception propagates.
        """
        scratch = dict(self._balances)
        for src, dst, amount in transfers:
            self._apply_transfer(scratch, src, dst, amount)
        self._balances = scratch

    def freeze(self, account_id: str) -> None:
        """Block withdrawals and outgoing transfers from an account.

        Deposits and incoming transfers are still accepted. Freezing an
        already-frozen account is a no-op.
        """
        self._get(account_id)
        self._frozen.add(account_id)

    def unfreeze(self, account_id: str) -> None:
        """Lift a freeze. Unfreezing an account that is not frozen is a no-op."""
        self._get(account_id)
        self._frozen.discard(account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._get(account_id)
        return account_id in self._frozen

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow withdrawals and outgoing transfers down to ``-limit``.

        Lowering the limit below the current overdraft is allowed; it only
        blocks further debits until the balance recovers.
        """
        self._get(account_id)
        self._check_amount(limit)
        if limit:
            self._overdraft[account_id] = limit
        else:
            self._overdraft.pop(account_id, None)

    def overdraft_limit(self, account_id: str) -> int:
        self._get(account_id)
        return self._overdraft.get(account_id, 0)

    def balance(self, account_id: str) -> int:
        return self._get(account_id)

    def balances(self) -> dict[str, int]:
        """Snapshot of every account's balance; mutating it does not affect the ledger."""
        return dict(self._balances)

    def accounts(self) -> list[str]:
        return sorted(self._balances)

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with floor(balance * bp / 10000).

        Only positive balances earn interest; zero balances are unchanged.
        """
        self._check_amount(basis_points)
        for account_id, current in self._balances.items():
            if current > 0:
                self._balances[account_id] = current + (current * basis_points) // 10_000

    def close_account(self, account_id: str) -> None:
        """Remove an account whose balance is exactly zero."""
        current = self._get(account_id)
        if current != 0:
            raise ValueError(
                f"cannot close {account_id!r} with non-zero balance {current}"
            )
        del self._balances[account_id]
        self._frozen.discard(account_id)
        self._overdraft.pop(account_id, None)

    def total_assets(self) -> int:
        """Sum of all account balances."""
        return sum(self._balances.values())
