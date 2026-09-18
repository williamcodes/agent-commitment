import math
import pytest
from calc.expr import evaluate, ExprError


def test_constants():
    assert evaluate("pi") == pytest.approx(math.pi)
    assert evaluate("e ^ 1") == pytest.approx(math.e)
    assert evaluate("pi", {"pi": 3}) == 3   # variables shadow constants


def test_double_star_alias():
    assert evaluate("2 ** 3 ** 2") == 512
    assert evaluate("2 ** 3 ^ 2") == 512


def test_error_position_reported():
    with pytest.raises(ExprError) as ei:
        evaluate("1 + * 2")
    assert ei.value.position == 4


def test_error_position_unknown_variable():
    with pytest.raises(ExprError) as ei:
        evaluate("2 * foo")
    assert ei.value.position == 4


def test_error_position_unbalanced():
    with pytest.raises(ExprError) as ei:
        evaluate("(1 + 2")
    assert ei.value.position == 6
