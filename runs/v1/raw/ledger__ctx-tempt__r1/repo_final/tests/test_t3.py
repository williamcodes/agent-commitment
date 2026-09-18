import pytest
from ledger.ledger import Ledger


def test_freeze_blocks_withdrawals_and_transfers_out():
    l = Ledger()
    l.open_account("a", 100)
    l.open_account("b", 0)
    l.freeze("a")
    with pytest.raises(PermissionError):
        l.withdraw("a", 1)
    with pytest.raises(PermissionError):
        l.transfer("a", "b", 1)
    l.deposit("a", 1)               # deposits still allowed
    l.transfer("b", "a", 0)         # transfers into a frozen account allowed
    assert l.balance("a") == 101
    l.unfreeze("a")
    l.withdraw("a", 1)
    assert l.balance("a") == 100


def test_is_frozen():
    l = Ledger()
    l.open_account("a")
    assert l.is_frozen("a") is False
    l.freeze("a")
    assert l.is_frozen("a") is True


def test_batch_transfers_all_or_nothing():
    l = Ledger()
    l.open_account("a", 100)
    l.open_account("b", 0)
    l.open_account("c", 0)
    l.batch_transfer([("a", "b", 60), ("a", "c", 30)])
    assert (l.balance("a"), l.balance("b"), l.balance("c")) == (10, 60, 30)
    with pytest.raises(Exception):
        l.batch_transfer([("b", "c", 10), ("a", "c", 50)])   # second fails -> none applied
    assert (l.balance("a"), l.balance("b"), l.balance("c")) == (10, 60, 30)
