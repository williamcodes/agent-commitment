"""In-memory account ledger (Approach B: snapshot state).

The ledger holds the current balance of each account directly in a dict
and mutates it in place. Amounts are integer cents.
"""


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


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
            raise ValueError(f"amount must be an integer, got {amount!r}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

    def _require(self, account_id: str) -> int:
        try:
            return self._balances[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def _debit(self, balances: dict[str, int], account_id: str, amount: int) -> None:
        """Debit ``account_id`` in ``balances``, enforcing freeze and funds rules."""
        if account_id in self._frozen:
            raise PermissionError(f"account is frozen: {account_id!r}")
        current = balances[account_id]
        limit = self._overdraft.get(account_id, 0)
        if current - amount < -limit:
            raise InsufficientFunds(
                f"cannot debit {amount} from {account_id!r} "
                f"(balance {current}, overdraft limit {limit})"
            )
        balances[account_id] = current - amount

    # -- public API --------------------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        self._check_amount(initial)
        if account_id in self._balances:
            raise ValueError(f"account already exists: {account_id!r}")
        self._balances[account_id] = initial

    def deposit(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        current = self._require(account_id)
        self._balances[account_id] = current + amount

    def withdraw(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        self._require(account_id)
        self._debit(self._balances, account_id, amount)

    def transfer(self, src: str, dst: str, amount: int) -> None:
        self.batch_transfer([(src, dst, amount)])

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply all transfers atomically: if any would fail, none are applied.

        The transfers are applied in order to a scratch copy of the balances,
        which is committed only once every one of them has succeeded.
        """
        scratch = dict(self._balances)
        for src, dst, amount in transfers:
            self._check_amount(amount)
            self._require(src)
            self._require(dst)
            self._debit(scratch, src, amount)
            scratch[dst] += amount
        self._balances = scratch

    def balance(self, account_id: str) -> int:
        return self._require(account_id)

    def accounts(self) -> list[str]:
        return sorted(self._balances)

    def apply_interest(self, basis_points: int) -> None:
        """Credit every positively-balanced account with floor(balance * bp / 10000)."""
        self._check_amount(basis_points)
        for account_id, current in self._balances.items():
            if current > 0:
                self._balances[account_id] = current + current * basis_points // 10000

    def close_account(self, account_id: str) -> None:
        current = self._require(account_id)
        if current != 0:
            raise ValueError(
                f"cannot close {account_id!r}: balance is {current}, must be 0"
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
        """Allow debits to take the balance down to ``-limit``."""
        self._check_amount(limit)
        self._require(account_id)
        self._overdraft[account_id] = limit

    def overdraft_limit(self, account_id: str) -> int:
        self._require(account_id)
        return self._overdraft.get(account_id, 0)

    def balances(self) -> dict[str, int]:
        """Return a fresh snapshot of all current balances."""
        return dict(self._balances)
