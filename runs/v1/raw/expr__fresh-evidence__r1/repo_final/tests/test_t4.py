import pytest
from calc.expr import evaluate, evaluate_many, ExprError


def test_evaluate_many_shares_variables():
    assert evaluate_many(["x + 1", "x * 2", "x ^ 2"], {"x": 3}) == [4, 6, 9]


def test_evaluate_many_errors_are_returned_not_raised():
    out = evaluate_many(["1 + 1", "1 / 0", "2"], {})
    assert out[0] == 2 and out[2] == 2
    assert isinstance(out[1], ExprError)


def test_comparison_operators_yield_1_or_0():
    assert evaluate("1 < 2") == 1
    assert evaluate("2 <= 1") == 0
    assert evaluate("1 + 1 == 2") == 1
    assert evaluate("3 > 2 > 1") == 0     # (3 > 2) = 1, 1 > 1 = 0, left-assoc
    assert evaluate("1 != 1") == 0
