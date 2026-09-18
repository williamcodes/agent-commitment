import pytest
from ledger.ledger import Ledger, InsufficientFunds, UnknownAccount


def test_open_deposit_withdraw():
    l = Ledger()
    l.open_account("a", 100)
    l.deposit("a", 50)
    l.withdraw("a", 30)
    assert l.balance("a") == 120


def test_insufficient_funds_leaves_balance_unchanged():
    l = Ledger()
    l.open_account("a", 10)
    with pytest.raises(InsufficientFunds):
        l.withdraw("a", 11)
    assert l.balance("a") == 10


def test_transfer_atomic():
    l = Ledger()
    l.open_account("a", 100)
    l.open_account("b")
    l.transfer("a", "b", 40)
    assert (l.balance("a"), l.balance("b")) == (60, 40)
    with pytest.raises(InsufficientFunds):
        l.transfer("a", "b", 1000)
    assert (l.balance("a"), l.balance("b")) == (60, 40)


def test_unknown_and_duplicate_accounts():
    l = Ledger()
    with pytest.raises(UnknownAccount):
        l.balance("nope")
    with pytest.raises(UnknownAccount):
        l.deposit("nope", 1)
    l.open_account("a")
    with pytest.raises(ValueError):
        l.open_account("a")
    with pytest.raises(ValueError):
        l.deposit("a", -1)


def test_accounts_sorted():
    l = Ledger()
    for i in ["c", "a", "b"]:
        l.open_account(i)
    assert l.accounts() == ["a", "b", "c"]
