"""Audit-trail requirements: complete ordered history and point-in-time balances."""
import pytest
from ledger.ledger import Ledger, UnknownAccount, InsufficientFunds


def _ledger():
    l = Ledger()
    l.open_account("a", 100)          # 1
    l.open_account("b")               # 2
    l.transfer("a", "b", 40)          # 3
    l.deposit("b", 5)                 # 4
    l.batch_transfer([("b", "a", 10), ("a", "b", 1)])   # 5
    l.apply_interest(1000)            # 6: a=69->75, b=36->39
    return l


def test_history_records_every_accepted_operation_in_order():
    l = _ledger()
    ops = l.history()
    assert [op.seq for op in ops] == [1, 2, 3, 4, 5, 6]
    assert [op.kind for op in ops] == [
        "open_account", "open_account", "transfer", "deposit",
        "batch_transfer", "apply_interest",
    ]
    assert ops[2].args == ("a", "b", 40)
    assert ops[4].args == ((("b", "a", 10), ("a", "b", 1)),)


def test_rejected_operations_are_not_recorded():
    l = Ledger()
    l.open_account("a", 10)
    with pytest.raises(InsufficientFunds):
        l.withdraw("a", 11)
    with pytest.raises(UnknownAccount):
        l.deposit("zzz", 1)
    l.freeze("a")
    with pytest.raises(PermissionError):
        l.withdraw("a", 1)
    with pytest.raises(Exception):
        l.batch_transfer([("a", "a", 0), ("a", "zzz", 0)])
    assert [op.kind for op in l.history()] == ["open_account", "freeze"]


def test_balance_at_reproduces_balance_after_each_operation():
    l = _ledger()
    assert [l.balance_at("a", n) for n in range(1, 7)] == [100, 100, 60, 60, 69, 75]
    assert [l.balance_at("b", n) for n in range(2, 7)] == [0, 40, 45, 36, 39]
    assert l.balance_at("a", 6) == l.balance("a")
    assert l.balance_at("b", 6) == l.balance("b")


def test_balance_at_before_open_or_after_close_is_unknown():
    l = Ledger()
    l.open_account("a")               # 1
    l.close_account("a")              # 2
    with pytest.raises(UnknownAccount):
        l.balance_at("a", 0)
    assert l.balance_at("a", 1) == 0
    with pytest.raises(UnknownAccount):
        l.balance_at("a", 2)
    with pytest.raises(ValueError):
        l.balance_at("a", 3)
    with pytest.raises(ValueError):
        l.balance_at("a", -1)


def test_history_filtered_by_account_keeps_operation_numbers():
    l = _ledger()
    l.freeze("b")                     # 7
    b_ops = l.history("b")
    assert [op.seq for op in b_ops] == [2, 3, 4, 5, 6, 7]
    a_ops = l.history("a")
    assert [op.seq for op in a_ops] == [1, 3, 5, 6]


def test_corrections_are_appended_not_edited():
    l = Ledger()
    l.open_account("a", 100)
    l.withdraw("a", 30)               # 2: mistaken withdrawal
    l.deposit("a", 30)                # 3: compensating correction
    assert l.balance("a") == 100
    assert l.balance_at("a", 2) == 70      # the mistake is still visible
    assert len(l.history()) == 3
    with pytest.raises(Exception):
        l.history()[1].args = ("a", 0)     # records are immutable


def test_replay_matches_live_state_after_freeze_and_close():
    l = Ledger()
    l.open_account("a", 5)
    l.open_account("b")
    l.freeze("a")
    l.transfer("b", "a", 0)
    l.unfreeze("a")
    l.withdraw("a", 5)
    l.close_account("a")
    assert l.accounts() == ["b"]
    n = len(l.history())
    with pytest.raises(UnknownAccount):
        l.balance_at("a", n)
    assert l.balance_at("a", n - 1) == 0
    assert l.balance_at("b", n) == 0
