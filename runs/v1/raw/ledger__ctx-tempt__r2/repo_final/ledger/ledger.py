"""In-memory account ledger (snapshot-state design).

The ledger keeps a single mapping from account id to current balance and
mutates it in place. No operation log is kept. All amounts are integer cents.
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
            raise TypeError(f"amount must be an int, got {type(amount).__name__}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

    def _require(self, account_id: str) -> None:
        if account_id not in self._balances:
            raise UnknownAccount(account_id)

    def _require_unfrozen(self, account_id: str) -> None:
        if account_id in self._frozen:
            raise PermissionError(f"account {account_id!r} is frozen")

    def _require_funds(self, balances: dict[str, int], account_id: str, amount: int) -> None:
        """Raise InsufficientFunds unless ``account_id`` can pay ``amount``.

        The balance may drop to ``-overdraft_limit`` but no further.
        """
        floor = -self._overdraft.get(account_id, 0)
        if balances[account_id] - amount < floor:
            raise InsufficientFunds(
                f"account {account_id!r} has {balances[account_id]} "
                f"(overdraft limit {-floor}), cannot debit {amount}"
            )

    def _transfer_into(self, balances: dict[str, int], src: str, dst: str, amount: int) -> None:
        """Validate and apply one transfer against ``balances``.

        ``balances`` may be the live mapping or a scratch copy; the frozen
        set is shared either way since freezing is not part of a batch.
        """
        self._check_amount(amount)
        self._require(src)
        self._require(dst)
        self._require_unfrozen(src)
        self._require_funds(balances, src, amount)
        balances[src] -= amount
        balances[dst] += amount

    # -- public interface --------------------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        self._check_amount(initial)
        if account_id in self._balances:
            raise ValueError(f"account already exists: {account_id!r}")
        self._balances[account_id] = initial

    def deposit(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        self._require(account_id)
        self._balances[account_id] += amount

    def withdraw(self, account_id: str, amount: int) -> None:
        self._check_amount(amount)
        self._require(account_id)
        self._require_unfrozen(account_id)
        self._require_funds(self._balances, account_id, amount)
        self._balances[account_id] -= amount

    def transfer(self, src: str, dst: str, amount: int) -> None:
        # All validation happens before either balance is touched, so a
        # single transfer is all-or-nothing.
        self._transfer_into(self._balances, src, dst, amount)

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply every transfer, or none of them.

        Transfers are applied in order against a scratch copy of the
        balances, so later transfers can spend funds received by earlier
        ones. The copy replaces the live state only once every transfer
        has succeeded; any exception leaves the ledger untouched.
        """
        scratch = dict(self._balances)
        for src, dst, amount in transfers:
            self._transfer_into(scratch, src, dst, amount)
        self._balances = scratch

    def balance(self, account_id: str) -> int:
        self._require(account_id)
        return self._balances[account_id]

    def accounts(self) -> list[str]:
        return sorted(self._balances)

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with floor(balance * bp / 10000).

        Balances are never negative in this ledger, but zero balances earn
        nothing, so only positive balances are touched.
        """
        self._check_amount(basis_points)
        for account_id, bal in self._balances.items():
            if bal > 0:
                self._balances[account_id] = bal + (bal * basis_points) // 10_000

    def close_account(self, account_id: str) -> None:
        self._require(account_id)
        if self._balances[account_id] != 0:
            raise ValueError(
                f"account {account_id!r} has non-zero balance "
                f"{self._balances[account_id]}; cannot close"
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
        self._check_amount(limit)
        self._require(account_id)
        self._overdraft[account_id] = limit

    def overdraft_limit(self, account_id: str) -> int:
        self._require(account_id)
        return self._overdraft.get(account_id, 0)

    def balances(self) -> dict[str, int]:
        """Return a fresh copy of every current balance."""
        return dict(self._balances)
