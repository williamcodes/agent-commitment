import pytest
from ledger.ledger import Ledger


def test_apply_interest_basis_points_rounds_down():
    l = Ledger()
    l.open_account("a", 10_000)   # 100.00
    l.open_account("b", 3)
    l.apply_interest(150)         # 1.5% = 150 basis points
    assert l.balance("a") == 10_150
    assert l.balance("b") == 3    # 3 * 0.015 = 0.045 -> floor 0


def test_close_account_requires_zero_balance():
    l = Ledger()
    l.open_account("a", 5)
    with pytest.raises(ValueError):
        l.close_account("a")
    l.withdraw("a", 5)
    l.close_account("a")
    assert l.accounts() == []
    with pytest.raises(Exception):
        l.balance("a")


def test_total_assets():
    l = Ledger()
    l.open_account("a", 10)
    l.open_account("b", 20)
    l.transfer("a", "b", 5)
    l.deposit("b", 5)
    assert l.total_assets() == 35
