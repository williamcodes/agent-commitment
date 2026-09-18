"""In-memory account ledger (Approach A: event sourcing).

The source of truth is an append-only log of operation records. Balances and
frozen flags are caches derived by folding over that log; the caches are
never written except by applying a record that has been (or is about to be)
appended. This gives the audit properties the ledger is required to have:

* ``history()`` returns every past operation, in order, numbered from 1.
* ``balance_at(account, n)`` returns an account's balance as it stood after
  operation ``n``, by replaying the log.
* Nothing ever edits or removes a record. A correction is expressed by
  appending a new compensating operation (a deposit, withdrawal, transfer...).

Amounts are integer cents.
"""

from dataclasses import dataclass, field


class InsufficientFunds(Exception):
    """Raised when a withdrawal or transfer exceeds the available balance."""


class UnknownAccount(Exception):
    """Raised when an operation references an account that does not exist."""


@dataclass(frozen=True, slots=True)
class Operation:
    """One immutable entry in the ledger's log.

    ``seq`` is the 1-based operation number. Which of the optional fields are
    populated depends on ``kind``:

    - ``open``            account, amount (the initial balance)
    - ``deposit``         account, amount
    - ``withdraw``        account, amount
    - ``transfer``        src, dst, amount
    - ``batch_transfer``  legs (a tuple of (src, dst, amount) triples)
    - ``apply_interest``  basis_points
    - ``close``           account
    - ``freeze``          account
    - ``unfreeze``        account
    - ``set_overdraft``   account, amount (the new overdraft limit)
    """

    seq: int
    kind: str
    account: str | None = None
    amount: int | None = None
    src: str | None = None
    dst: str | None = None
    basis_points: int | None = None
    legs: tuple[tuple[str, str, int], ...] = field(default=())


class _State:
    """Mutable snapshot derived from a prefix of the log.

    ``apply`` validates an operation against the current snapshot and, only if
    it is valid, mutates the snapshot. Every check happens before any write so
    a rejected operation leaves the snapshot untouched.

    ``overdraft`` holds each account's overdraft limit; an account absent from
    it has the default limit of 0.
    """

    __slots__ = ("balances", "frozen", "overdraft")

    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.frozen: set[str] = set()
        self.overdraft: dict[str, int] = {}

    def copy(self) -> "_State":
        other = _State()
        other.balances = dict(self.balances)
        other.frozen = set(self.frozen)
        other.overdraft = dict(self.overdraft)
        return other

    # -- validation helpers -------------------------------------------------

    @staticmethod
    def _check_amount(amount: int) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError(f"amount must be an int, got {type(amount).__name__}")
        if amount < 0:
            raise ValueError(f"amount must be non-negative, got {amount}")

    def require(self, account_id: str) -> int:
        try:
            return self.balances[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def _require_unfrozen(self, account_id: str) -> None:
        if account_id in self.frozen:
            raise PermissionError(f"account {account_id!r} is frozen")

    def _debit_checks(self, account_id: str, amount: int, verb: str) -> int:
        """Shared checks for anything that moves money out of an account.

        The balance may go as low as ``-limit`` where ``limit`` is the
        account's overdraft limit (0 unless set).
        """
        self._check_amount(amount)
        current = self.require(account_id)
        self._require_unfrozen(account_id)
        available = current + self.overdraft.get(account_id, 0)
        if amount > available:
            raise InsufficientFunds(
                f"account {account_id!r} has {current} available {available}, "
                f"cannot {verb} {amount}"
            )
        return current

    # -- applying operations ------------------------------------------------

    def apply(self, op: Operation) -> None:
        getattr(self, f"_apply_{op.kind}")(op)

    def _apply_open(self, op: Operation) -> None:
        self._check_amount(op.amount)
        if op.account in self.balances:
            raise ValueError(f"account already exists: {op.account!r}")
        self.balances[op.account] = op.amount

    def _apply_deposit(self, op: Operation) -> None:
        self._check_amount(op.amount)
        current = self.require(op.account)
        self.balances[op.account] = current + op.amount

    def _apply_withdraw(self, op: Operation) -> None:
        current = self._debit_checks(op.account, op.amount, "withdraw")
        self.balances[op.account] = current - op.amount

    def _transfer(self, src: str, dst: str, amount: int) -> None:
        src_balance = self._debit_checks(src, amount, "transfer")
        self.require(dst)
        if src == dst:
            return
        self.balances[src] = src_balance - amount
        self.balances[dst] += amount

    def _apply_transfer(self, op: Operation) -> None:
        self._transfer(op.src, op.dst, op.amount)

    def _apply_batch_transfer(self, op: Operation) -> None:
        # Run every leg against a scratch copy; only if all succeed do we
        # adopt the result, so a failing leg leaves this snapshot untouched.
        scratch = self.copy()
        for src, dst, amount in op.legs:
            scratch._transfer(src, dst, amount)
        self.balances = scratch.balances

    def _apply_apply_interest(self, op: Operation) -> None:
        self._check_amount(op.basis_points)
        for account_id, current in self.balances.items():
            if current > 0:
                self.balances[account_id] = (
                    current + current * op.basis_points // 10_000
                )

    def _apply_close(self, op: Operation) -> None:
        current = self.require(op.account)
        if current != 0:
            raise ValueError(
                f"account {op.account!r} has balance {current}, must be 0 to close"
            )
        del self.balances[op.account]
        self.frozen.discard(op.account)
        self.overdraft.pop(op.account, None)

    def _apply_freeze(self, op: Operation) -> None:
        self.require(op.account)
        self.frozen.add(op.account)

    def _apply_unfreeze(self, op: Operation) -> None:
        self.require(op.account)
        self.frozen.discard(op.account)

    def _apply_set_overdraft(self, op: Operation) -> None:
        self._check_amount(op.amount)
        self.require(op.account)
        self.overdraft[op.account] = op.amount


class Ledger:
    def __init__(self) -> None:
        self._log: list[Operation] = []
        self._state = _State()  # cache: fold of self._log

    # -- the one write path -------------------------------------------------

    def _record(self, kind: str, **fields) -> None:
        """Validate and apply an operation, then append it to the log.

        The cache is only mutated by ``apply``, which raises before writing
        anything if the operation is invalid, so a failed call leaves both
        the log and the cache unchanged.
        """
        op = Operation(seq=len(self._log) + 1, kind=kind, **fields)
        self._state.apply(op)
        self._log.append(op)

    # -- public interface (SPEC.md) ----------------------------------------

    def open_account(self, account_id: str, initial: int = 0) -> None:
        self._record("open", account=account_id, amount=initial)

    def deposit(self, account_id: str, amount: int) -> None:
        self._record("deposit", account=account_id, amount=amount)

    def withdraw(self, account_id: str, amount: int) -> None:
        """Raises InsufficientFunds, or PermissionError if the account is frozen."""
        self._record("withdraw", account=account_id, amount=amount)

    def transfer(self, src: str, dst: str, amount: int) -> None:
        """Atomic. Raises PermissionError if ``src`` is frozen; a frozen ``dst``
        still accepts incoming funds."""
        self._record("transfer", src=src, dst=dst, amount=amount)

    def balance(self, account_id: str) -> int:
        return self._state.require(account_id)

    def accounts(self) -> list[str]:
        return sorted(self._state.balances)

    def balances(self) -> dict[str, int]:
        """A fresh dict of every open account's current balance.

        The result is a copy: mutating it does not affect the ledger.
        """
        return dict(self._state.balances)

    def apply_interest(self, basis_points: int) -> None:
        """Credit every account with floor(balance * bp / 10000).

        Only positive balances earn interest; a zero balance is unchanged.
        Integer floor division keeps every balance an exact number of cents.
        """
        self._record("apply_interest", basis_points=basis_points)

    def close_account(self, account_id: str) -> None:
        """Close an account whose balance is exactly zero.

        Raises UnknownAccount if the id does not exist and ValueError if the
        balance is non-zero. Afterwards the id is unknown and may be reopened
        (unfrozen); its earlier history remains in the log.
        """
        self._record("close", account=account_id)

    def total_assets(self) -> int:
        """Sum of all account balances."""
        return sum(self._state.balances.values())

    # -- freezing -----------------------------------------------------------

    def freeze(self, account_id: str) -> None:
        """Block withdrawals and outgoing transfers; deposits and incoming
        transfers continue to work. Idempotent."""
        self._record("freeze", account=account_id)

    def unfreeze(self, account_id: str) -> None:
        """Lift a freeze. Idempotent."""
        self._record("unfreeze", account=account_id)

    def is_frozen(self, account_id: str) -> bool:
        self._state.require(account_id)
        return account_id in self._state.frozen

    # -- overdrafts ---------------------------------------------------------

    def set_overdraft_limit(self, account_id: str, limit: int) -> None:
        """Allow withdrawals and outgoing transfers to take the balance down
        to ``-limit``. The limit is a non-negative int (ValueError otherwise)
        and is recorded in the log like any other operation. Lowering the
        limit below the current overdraft is allowed; it simply blocks
        further debits until the balance recovers. Closing an account drops
        its limit, so a reopened id starts at the default of 0.
        """
        self._record("set_overdraft", account=account_id, amount=limit)

    def overdraft_limit(self, account_id: str) -> int:
        """Current overdraft limit; 0 unless set. Raises UnknownAccount."""
        self._state.require(account_id)
        return self._state.overdraft.get(account_id, 0)

    # -- batch transfers ----------------------------------------------------

    def batch_transfer(self, transfers: list[tuple[str, str, int]]) -> None:
        """Apply every (src, dst, amount) transfer atomically, in order.

        Legs are evaluated sequentially, so a later leg may spend funds
        received by an earlier one. If any leg would fail, nothing is
        applied and the log is unchanged. The whole batch is recorded as a
        single operation.
        """
        legs = tuple((src, dst, amount) for src, dst, amount in transfers)
        self._record("batch_transfer", legs=legs)

    # -- audit / history ----------------------------------------------------

    def history(self, account_id: str | None = None) -> list[Operation]:
        """Every operation ever applied, in order, numbered from 1.

        With ``account_id``, only operations that touched that account are
        returned (interest runs are included since they touch every account).
        Operation numbers are preserved so results line up with ``balance_at``.
        """
        if account_id is None:
            return list(self._log)
        return [op for op in self._log if self._touches(op, account_id)]

    def balance_at(self, account_id: str, op_number: int) -> int:
        """Balance of ``account_id`` as it stood right after operation
        ``op_number`` (0 means before any operation).

        Raises UnknownAccount if the account did not exist at that point and
        ValueError if ``op_number`` is out of range. Computed by replaying
        the log, so it costs O(op_number).
        """
        if not 0 <= op_number <= len(self._log):
            raise ValueError(
                f"operation number must be in 0..{len(self._log)}, got {op_number}"
            )
        state = _State()
        for op in self._log[:op_number]:
            state.apply(op)
        return state.require(account_id)

    @staticmethod
    def _touches(op: Operation, account_id: str) -> bool:
        if op.kind == "apply_interest":
            return True
        if op.account == account_id or op.src == account_id or op.dst == account_id:
            return True
        return any(account_id in (src, dst) for src, dst, _ in op.legs)
