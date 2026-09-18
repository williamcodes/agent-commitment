"""Audit requirements: full ordered history, balance after any operation,
replay from the log, and an append-only (never edited) record."""

import pytest
from types import MappingProxyType

from ledger.ledger import Ledger, InsufficientFunds, Operation, UnknownAccount


def _sample_ledger() -> Ledger:
    l = Ledger()
    l.open_account("a", 100)                        # 1
    l.open_account("b")                             # 2
    l.transfer("a", "b", 40)                        # 3
    l.freeze("a")                                   # 4
    with pytest.raises(PermissionError):
        l.withdraw("a", 1)                          # rejected: not recorded
    l.deposit("a", 5)                               # 5
    l.apply_interest(150)                           # 6  (65 and 40 both round to 0)
    l.batch_transfer([("b", "a", 10), ("b", "a", 5)])  # 7
    with pytest.raises(InsufficientFunds):
        l.batch_transfer([("b", "a", 10), ("b", "a", 1000)])  # rejected
    l.unfreeze("a")                                 # 8
    l.withdraw("a", 80)                             # 9
    l.close_account("a")                            # 10
    return l


def test_history_lists_every_applied_operation_in_order():
    l = _sample_ledger()
    ops = l.history()
    assert [op.seq for op in ops] == list(range(1, 11))
    assert [op.kind for op in ops] == [
        "open_account", "open_account", "transfer", "freeze", "deposit",
        "apply_interest", "batch_transfer", "unfreeze", "withdraw", "close_account",
    ]
    assert ops[2].params == {"src": "a", "dst": "b", "amount": 40}
    assert ops[6].params == {"transfers": (("b", "a", 10), ("b", "a", 5))}


def test_balance_at_any_operation_number():
    l = _sample_ledger()
    assert l.balance_at("a", 1) == 100
    assert (l.balance_at("a", 3), l.balance_at("b", 3)) == (60, 40)
    assert l.balance_at("a", 5) == 65
    assert (l.balance_at("a", 7), l.balance_at("b", 7)) == (80, 25)
    assert l.balance_at("a", 9) == 0
    assert l.balance_at("b", 10) == l.balance("b") == 25


def test_balance_at_respects_account_lifetime_and_range():
    l = _sample_ledger()
    with pytest.raises(UnknownAccount):
        l.balance_at("a", 0)        # before it was opened
    with pytest.raises(UnknownAccount):
        l.balance_at("a", 10)       # after it was closed
    with pytest.raises(ValueError):
        l.balance_at("a", 11)
    with pytest.raises(ValueError):
        l.balance_at("a", -1)


def test_replay_reproduces_state_and_log():
    l = _sample_ledger()
    r = Ledger.replay(l.history())
    assert r.history() == l.history()
    assert r.accounts() == l.accounts()
    assert r.total_assets() == l.total_assets()
    assert r.is_frozen("b") is False


def test_records_are_immutable_and_tampered_logs_are_rejected():
    l = _sample_ledger()
    op = l.history()[0]
    with pytest.raises(Exception):
        op.seq = 99
    with pytest.raises(TypeError):
        op.params["initial"] = 1
    # history() hands out a copy; mutating it does not touch the ledger
    l.history().clear()
    assert len(l.history()) == 10
    # gap in sequence numbers
    with pytest.raises(ValueError):
        Ledger.replay([Operation(2, "open_account", MappingProxyType({"account_id": "x", "initial": 0}))])
    # kind that is not a ledger operation
    with pytest.raises(ValueError):
        Ledger.replay([Operation(1, "balance", MappingProxyType({"account_id": "x"}))])


def test_corrections_are_new_operations():
    l = Ledger()
    l.open_account("a", 100)
    l.withdraw("a", 30)             # suppose this was a mistake
    l.deposit("a", 30)              # correction is appended, never edited in
    assert [op.kind for op in l.history()] == ["open_account", "withdraw", "deposit"]
    assert l.balance_at("a", 2) == 70
    assert l.balance_at("a", 3) == 100


def test_freeze_state_is_cleared_on_close_and_reopen():
    l = Ledger()
    l.open_account("a")
    l.freeze("a")
    with pytest.raises(ValueError):
        l.freeze("a")               # already frozen
    l.close_account("a")
    l.open_account("a")
    assert l.is_frozen("a") is False
    with pytest.raises(ValueError):
        l.unfreeze("a")             # not frozen
