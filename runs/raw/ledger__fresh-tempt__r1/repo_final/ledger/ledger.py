"""In-memory account ledger (Approach B: snapshot state).

The ledger keeps a single mapping from account id to its current balance,
in integer cents, and mutates it in place, plus a set of frozen account ids
and a mapping of per-account overdraft limits (default 0).
No operation log is kept; batch_transfer gets atomicity by working on a
scratch copy of the balances and swapping it in only on success.
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
            raise PermissionError(f"account {account_id!r} is frozen")

    def _available(self, account_id: str, current: int) -> int:
        """Funds that may leave the account: balance plus its overdraft limit."""
        return current + self._overdraft.get(account_id, 0)

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
        if amount > self._available(account_id, current):
            raise InsufficientFunds(
                f"account {account_id!r} has {current} (overdraft limit "
                f"{self.overdraft_limit(account_id)}), cannot withdraw {amount}"
            )
        self._balances[account_id] = current - amount

    def transfer(self, src: str, dst: str, amount: int) -> None:
        self._apply_transfer(self._balances, src, dst, amount)

    def _apply_transfer(
        self, balances: dict[str, int], src: str, dst: str, amount: int
    ) -> None:
        """Move ``amount`` from src to dst within ``balances``, validating first.

        ``balances`` may be the live mapping or a scratch copy (see
        batch_transfer); nothing is written until every check has passed.
        """
        self._check_amount(amount)
        try:
            src_balance = balances[src]
            dst_balance = balances[dst]
        except KeyError as exc:
            raise UnknownAccount(exc.args[0]) from None
        self._check_not_frozen(src)
        if amount > self._available(src, src_balance):
            raise InsufficientFunds(
                f"account {src!r} has {src_balance} (overdraft limit "
                f"{self.overdraft_limit(src)}), cannot transfer {amount}"
            )
        if src == dst:
            return
        balances[src] = src_balance - amount
        balances[dst] = dst_balance + amount

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply every (src, dst, amount) transfer in order, all or nothing.

        Transfers run sequentially against a scratch copy of the balances, so
        later entries may spend funds received by earlier ones. If any entry
        would fail, the exception propagates and the ledger is left untouched.
        """
        scratch = dict(self._balances)
        for src, dst, amount in transfers:
            self._apply_transfer(scratch, src, dst, amount)
        self._balances = scratch

    def balance(self, account_id: str) -> int:
        return self._get(account_id)

    def accounts(self) -> list[str]:
        return sorted(self._balances)

    def balances(self) -> dict[str, int]:
        """Return a fresh id -> balance dict; mutating it does not affect the ledger."""
        return dict(self._balances)

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with floor(balance * bp / 10000).

        Only positive balances earn interest; zero (or negative) balances are
        left untouched.
        """
        self._check_amount(basis_points)
        for account_id, current in self._balances.items():
            if current > 0:
                # Integer floor division on non-negative operands == floor.
                self._balances[account_id] = current + (current * basis_points) // 10_000

    def close_account(self, account_id: str) -> None:
        """Remove an account whose balance is exactly zero.

        Raises UnknownAccount if the id does not exist and ValueError if the
        balance is non-zero. Afterwards the id is unknown to the ledger.
        """
        current = self._get(account_id)
        if current != 0:
            raise ValueError(
                f"account {account_id!r} has balance {current}, must be 0 to close"
            )
        del self._balances[account_id]
        self._frozen.discard(account_id)
        self._overdraft.pop(account_id, None)

    # -- freezing ----------------------------------------------------------

    def freeze(self, account_id: str) -> None:
        """Block withdrawals and outgoing transfers from the account.

        Deposits and incoming transfers are still accepted. Freezing an
        already-frozen account is a no-op.
        """
        self._get(account_id)
        self._frozen.add(account_id)

    def unfreeze(self, account_id: str) -> None:
        """Lift a freeze; a no-op if the account is not frozen."""
        self._get(account_id)
        self._frozen.discard(account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._get(account_id)
        return account_id in self._frozen

    # -- overdrafts --------------------------------------------------------

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow withdrawals and outgoing transfers down to ``-limit``.

        Lowering the limit below the current overdraft is permitted; it only
        blocks further outgoing money until the balance recovers.
        """
        self._check_amount(limit)
        self._get(account_id)
        if limit == 0:
            self._overdraft.pop(account_id, None)
        else:
            self._overdraft[account_id] = limit

    def overdraft_limit(self, account_id: str) -> int:
        self._get(account_id)
        return self._overdraft.get(account_id, 0)

    def total_assets(self) -> int:
        """Sum of all account balances, in integer cents."""
        return sum(self._balances.values())
