import pytest
from ledger.ledger import Ledger


def test_overdraft_limit_allows_negative_up_to_limit():
    l = Ledger()
    l.open_account("a", 10)
    l.set_overdraft_limit("a", 25)
    l.withdraw("a", 30)
    assert l.balance("a") == -20
    with pytest.raises(Exception):
        l.withdraw("a", 6)
    assert l.balance("a") == -20


def test_overdraft_default_zero():
    l = Ledger()
    l.open_account("a", 1)
    with pytest.raises(Exception):
        l.withdraw("a", 2)
    assert l.overdraft_limit("a") == 0


def test_balances_dict():
    l = Ledger()
    l.open_account("a", 1)
    l.open_account("b", 2)
    assert l.balances() == {"a": 1, "b": 2}
