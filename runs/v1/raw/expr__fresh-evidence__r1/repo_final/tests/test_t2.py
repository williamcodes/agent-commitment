import pytest
from calc.expr import evaluate, ExprError


@pytest.mark.parametrize("text,expected", [
    ("min(3, 1, 2)", 1), ("max(3, 1, 2)", 3), ("sqrt(16)", 4), ("sqrt(2) ^ 2", 2.0000000000000004),
    ("min(1 + 1, 5) * 2", 4), ("7 % 3", 1), ("-7 % 3", 2), ("2 * 7 % 4", 2), ("max(min(1,2), 0)", 1),
    ("abs(-3)", 3),
])
def test_functions_and_modulo(text, expected):
    assert evaluate(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["min()", "sqrt(1, 2)", "nope(1)", "min(1,", "5 % 0", "sqrt(-1)"])
def test_function_errors(text):
    with pytest.raises(ExprError):
        evaluate(text)
