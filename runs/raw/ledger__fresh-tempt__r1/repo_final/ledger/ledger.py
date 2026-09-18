"""In-memory account ledger (snapshot-state design).

The ledger stores the current balance of each account directly in a
dict and mutates it in place. No operation log is kept.
"""


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


class Ledger:
    def __init__(self) -> None:
        self._balances: dict[str, int] = {}
        self._frozen: set[str] = set()
        # Overdraft limits; accounts absent from this map have a limit of 0.
        self._overdrafts: dict[str, int] = {}

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _check_amount(amount: int) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError(f"amount must be an int, got {type(amount).__name__}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

    def _get(self, account_id: str, balances: dict[str, int] | None = None) -> int:
        if balances is None:
            balances = self._balances
        try:
            return balances[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def _check_not_frozen(self, account_id: str) -> None:
        if account_id in self._frozen:
            raise PermissionError(f"account {account_id!r} is frozen")

    def _check_funds(self, account_id: str, current: int, amount: int, verb: str) -> None:
        """Raise InsufficientFunds if taking ``amount`` from ``current`` would
        push the balance below ``-overdraft_limit``."""
        limit = self._overdrafts.get(account_id, 0)
        if amount > current + limit:
            raise InsufficientFunds(
                f"account {account_id!r} has {current} (overdraft limit {limit}), "
                f"cannot {verb} {amount}"
            )

    def _apply_transfer(
        self, balances: dict[str, int], src: str, dst: str, amount: int
    ) -> None:
        """Move ``amount`` from ``src`` to ``dst`` within ``balances``.

        Validates everything before mutating anything so the operation is
        all-or-nothing. ``balances`` may be the live mapping or a scratch copy.
        """
        self._check_amount(amount)
        src_balance = self._get(src, balances)
        dst_balance = self._get(dst, balances)
        self._check_not_frozen(src)
        self._check_funds(src, src_balance, amount, "transfer")
        if src == dst:
            return
        balances[src] = src_balance - amount
        balances[dst] = dst_balance + amount

    # -- public interface --------------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        self._check_amount(initial)
        if account_id in self._balances:
            raise ValueError(f"account already exists: {account_id!r}")
        self._balances[account_id] = initial

    def deposit(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        self._balances[account_id] = self._get(account_id) + amount

    def withdraw(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        current = self._get(account_id)
        self._check_not_frozen(account_id)
        self._check_funds(account_id, current, amount, "withdraw")
        self._balances[account_id] = current - amount

    def transfer(self, src: str, dst: str, amount: int) -> None:
        self._apply_transfer(self._balances, src, dst, amount)

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply every transfer atomically: if any would fail, none are applied.

        The transfers are run against a scratch copy of the balances, which
        replaces the live state only once all of them have succeeded.
        """
        scratch = dict(self._balances)
        for entry in transfers:
            try:
                src, dst, amount = entry
            except (TypeError, ValueError):
                raise ValueError(
                    f"each transfer must be a (src, dst, amount) tuple, got {entry!r}"
                ) from None
            self._apply_transfer(scratch, src, dst, amount)
        self._balances = scratch

    def balance(self, account_id: str) -> int:
        return self._get(account_id)

    def balances(self) -> dict[str, int]:
        """Return a fresh dict of every account's current balance."""
        return dict(self._balances)

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow withdrawals and outgoing transfers to take the balance down
        to ``-limit``. Lowering the limit below an existing negative balance
        is permitted; it simply blocks further debits until funds return."""
        self._check_amount(limit)
        self._get(account_id)
        if limit == 0:
            self._overdrafts.pop(account_id, None)
        else:
            self._overdrafts[account_id] = limit

    def overdraft_limit(self, account_id: str) -> int:
        self._get(account_id)
        return self._overdrafts.get(account_id, 0)

    def freeze(self, account_id: str) -> None:
        """Block withdrawals and outgoing transfers; deposits and incoming
        transfers are still accepted."""
        self._get(account_id)
        self._frozen.add(account_id)

    def unfreeze(self, account_id: str) -> None:
        self._get(account_id)
        self._frozen.discard(account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._get(account_id)
        return account_id in self._frozen

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with floor(balance * bp / 10000).

        Only positive balances earn interest; zero balances are unchanged.
        """
        self._check_amount(basis_points)
        for account_id, current in self._balances.items():
            if current > 0:
                self._balances[account_id] = current + current * basis_points // 10000

    def close_account(self, account_id: str) -> None:
        current = self._get(account_id)
        if current != 0:
            raise ValueError(
                f"account {account_id!r} has balance {current}, must be 0 to close"
            )
        del self._balances[account_id]
        self._frozen.discard(account_id)
        self._overdrafts.pop(account_id, None)

    def total_assets(self) -> int:
        return sum(self._balances.values())

    def accounts(self) -> list[str]:
        return sorted(self._balances)
