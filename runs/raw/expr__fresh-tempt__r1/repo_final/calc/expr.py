"""Arithmetic expression evaluator (recursive descent, Approach A).

Grammar (highest precedence at the bottom):

    compare := expr (('<' | '<=' | '>' | '>=' | '==' | '!=') expr)*
    expr    := term (('+' | '-') term)*
    term    := unary (('*' | '/' | '%') unary)*
    unary   := '-' unary | power
    power   := primary (('^' | '**') unary)?   # right-associative
    primary := NUMBER | call | IDENT | '(' expr ')'
    call    := IDENT '(' (expr (',' expr)*)? ')'

Unary minus sits between the multiplicative level and the exponent level,
so ``-2^2`` parses as ``-(2^2)``. The exponent of ``^`` is itself a ``unary``
so ``2 ^ -1`` is allowed and chains such as ``2^3^2`` associate to the right.
``**`` is an alias for ``^`` and the two may be mixed freely.
``%`` is modulo with Python semantics (``-7 % 3 == 2``). Comparison operators
have the lowest precedence, are left-associative, and yield ``1.0`` when true
and ``0.0`` when false, so ``3 > 2 > 1`` is ``(3 > 2) > 1 == 0.0``. Built-in functions are
``min``, ``max`` (one or more arguments), ``sqrt`` and ``abs`` (one argument).
The constants ``pi`` and ``e`` are predefined; entries in the caller's
``variables`` mapping shadow them.

Every ``ExprError`` carries a ``position``: the 0-based character offset in
the input where the problem was detected (the start of the offending token or
identifier, the operator for arithmetic failures, or ``len(text)`` when the
input ended unexpectedly).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import NamedTuple


class ExprError(Exception):
    """Raised for syntax errors, unknown variables/functions, bad arity, and math errors.

    ``position`` is the 0-based offset into the input text where the error was detected.
    """

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} at position {position}")
        self.message = message
        self.position = position


class _Token(NamedTuple):
    kind: str
    value: str
    start: int


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+))
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\*\*|<=|>=|==|!=|[-+*/%^(),<>])
    """,
    re.VERBOSE,
)

# Operator spellings that are pure aliases of another operator.
_OP_ALIASES = {"**": "^"}

_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


def _sqrt(x: float) -> float:
    if x < 0:
        raise ValueError(f"sqrt of negative number {x}")
    return math.sqrt(x)


# name -> (implementation, min arity, max arity or None for unbounded)
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int | None]] = {
    "min": (lambda *args: min(args), 1, None),
    "max": (lambda *args: max(args), 1, None),
    "sqrt": (_sqrt, 1, 1),
    "abs": (abs, 1, 1),
}


def _arity_message(name: str, n: int, *, min_args: int, max_args: int | None) -> str | None:
    if n < min_args or (max_args is not None and n > max_args):
        if max_args is None:
            want = f"at least {min_args}"
        elif min_args == max_args:
            want = str(min_args)
        else:
            want = f"between {min_args} and {max_args}"
        return f"{name}() takes {want} argument(s) but {n} were given"
    return None


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = match.lastgroup
        assert kind is not None
        if kind != "ws":
            value = match.group()
            if kind == "op":
                value = _OP_ALIASES.get(value, value)
            tokens.append(_Token(kind, value, pos))
        pos = match.end()
    tokens.append(_Token("eof", "", len(text)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], variables: Mapping[str, float]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._variables = variables

    # -- token helpers -------------------------------------------------------

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _accept_op(self, *ops: str) -> _Token | None:
        token = self._peek()
        if token.kind == "op" and token.value in ops:
            self._advance()
            return token
        return None

    def _expect_op(self, op: str) -> None:
        if self._accept_op(op) is None:
            token = self._peek()
            raise ExprError(f"expected {op!r} but found {self._describe(token)}", token.start)

    @staticmethod
    def _describe(token: _Token) -> str:
        return "end of input" if token.kind == "eof" else repr(token.value)

    # -- grammar -------------------------------------------------------------

    def parse(self) -> float:
        value = self._compare()
        token = self._peek()
        if token.kind != "eof":
            raise ExprError(f"unexpected token {token.value!r}", token.start)
        return value

    def _compare(self) -> float:
        value = self._expr()
        while (op := self._accept_op(*_COMPARISONS)) is not None:
            rhs = self._expr()
            value = 1.0 if _COMPARISONS[op.value](value, rhs) else 0.0
        return value

    def _expr(self) -> float:
        value = self._term()
        while (op := self._accept_op("+", "-")) is not None:
            rhs = self._term()
            value = value + rhs if op.value == "+" else value - rhs
        return value

    def _term(self) -> float:
        value = self._unary()
        while (op := self._accept_op("*", "/", "%")) is not None:
            rhs = self._unary()
            if op.value == "*":
                value = value * rhs
            elif op.value == "/":
                if rhs == 0:
                    raise ExprError("division by zero", op.start)
                value = value / rhs
            else:
                if rhs == 0:
                    raise ExprError("modulo by zero", op.start)
                value = value % rhs
        return value

    def _unary(self) -> float:
        if self._accept_op("-") is not None:
            return -self._unary()
        return self._power()

    def _power(self) -> float:
        base = self._primary()
        if (op := self._accept_op("^")) is not None:
            exponent = self._unary()
            try:
                return float(base**exponent)
            except (OverflowError, ZeroDivisionError) as exc:
                raise ExprError(f"cannot compute {base} ^ {exponent}: {exc}", op.start) from exc
        return base

    def _primary(self) -> float:
        token = self._advance()
        if token.kind == "number":
            return float(token.value)
        if token.kind == "ident":
            if self._peek().kind == "op" and self._peek().value == "(":
                return self._call(token)
            return self._lookup(token)
        if token.kind == "op" and token.value == "(":
            inner = self._compare()
            self._expect_op(")")
            return inner
        raise ExprError(
            f"expected a number, variable, or '(' but found {self._describe(token)}", token.start
        )

    def _lookup(self, token: _Token) -> float:
        name = token.value
        if name in self._variables:
            return float(self._variables[name])
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        raise ExprError(f"unknown variable {name!r}", token.start)

    def _call(self, name_token: _Token) -> float:
        name = name_token.value
        self._expect_op("(")
        args: list[float] = []
        if self._accept_op(")") is None:
            args.append(self._compare())
            while self._accept_op(",") is not None:
                args.append(self._compare())
            self._expect_op(")")
        try:
            func, min_args, max_args = _FUNCTIONS[name]
        except KeyError:
            raise ExprError(f"unknown function {name!r}", name_token.start) from None
        if (problem := _arity_message(name, len(args), min_args=min_args, max_args=max_args)):
            raise ExprError(problem, name_token.start)
        try:
            return float(func(*args))
        except ValueError as exc:
            raise ExprError(str(exc), name_token.start) from exc


def evaluate(text: str, variables: Mapping[str, float] | None = None) -> float:
    """Evaluate ``text`` and return the result as a float.

    ``variables`` maps identifier names to numeric values and shadows the
    built-in constants ``pi`` and ``e``. Raises ``ExprError`` (with a
    ``position`` attribute) on any syntax error, unknown variable or function,
    wrong argument count, division or modulo by zero, or square root of a
    negative number.
    """
    parser = _Parser(_tokenize(text), variables if variables is not None else {})
    return parser.parse()


def evaluate_many(
    texts: list[str], variables: Mapping[str, float] | None = None
) -> list[float | ExprError]:
    """Evaluate each expression in ``texts`` against the same ``variables``.

    Returns one entry per input, in order: the float result, or the
    ``ExprError`` instance that ``evaluate`` would have raised for that
    expression. Errors never propagate, so a bad expression does not prevent
    the remaining ones from being evaluated.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
