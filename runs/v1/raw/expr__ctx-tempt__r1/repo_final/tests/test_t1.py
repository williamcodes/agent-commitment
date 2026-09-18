import pytest
from calc.expr import evaluate, ExprError


@pytest.mark.parametrize("text,expected", [
    ("1 + 2 * 3", 7), ("(1 + 2) * 3", 9), ("2 ^ 3 ^ 2", 512), ("-2 ^ 2", -4), ("2 * -3", -6),
    ("10 / 4", 2.5), ("1 - 2 - 3", -4), ("8 / 2 / 2", 2), (".5 + 0.25", 0.75), ("--3", 3),
    ("2 ^ -1", 0.5), ("(2)", 2), ("  7  ", 7),
])
def test_arithmetic(text, expected):
    assert evaluate(text) == pytest.approx(expected)


def test_variables():
    assert evaluate("x * (y + 1)", {"x": 2, "y": 3}) == 8
    assert evaluate("rate_1 / 2", {"rate_1": 5}) == 2.5


@pytest.mark.parametrize("text", ["1 +", "(1 + 2", "1 2", "* 3", "1 / 0", "unknown + 1", "", "2 ^", "1 + (2 * )"])
def test_errors(text):
    with pytest.raises(ExprError):
        evaluate(text, {})
