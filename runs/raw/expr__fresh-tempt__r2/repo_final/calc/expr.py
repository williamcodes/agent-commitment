"""Arithmetic expression evaluator (recursive descent, Approach A in SPEC.md).

Grammar (precedence lowest to highest):

    comparison := expression (('<' | '<=' | '>' | '>=' | '==' | '!=') expression)*
    expression := term (('+' | '-') term)*
    term       := unary (('*' | '/' | '%') unary)*
    unary      := '-' unary | power
    power      := primary (('^' | '**') unary)?  # right-associative; RHS may be signed
    primary    := NUMBER | IDENT | call | '(' comparison ')'
    call       := IDENT '(' (comparison (',' comparison)*)? ')'

Comparison operators have the lowest precedence, are left-associative and
yield ``1.0`` (true) or ``0.0`` (false), so ``3 > 2 > 1`` is ``(3 > 2) > 1``
which is ``1 > 1`` which is ``0.0``.

Built-in functions: ``min``, ``max`` (one or more arguments), ``sqrt`` and
``abs`` (exactly one argument).  Function names take precedence over
variables of the same name.

Built-in constants: ``pi`` and ``e``.  A variable of the same name passed by
the caller shadows the constant.

Note that unary minus sits between term and power, so ``-2^2`` parses as
``-(2^2)``, while ``2 ^ -1`` still works because the exponent is parsed as a
``unary``.

Every :class:`ExprError` carries a ``position``: the 0-based character offset
in the input where the problem was detected (the start of the offending token
or identifier, or ``len(text)`` for unexpected end of input).
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable, Mapping
from typing import NamedTuple

__all__ = ["ExprError", "evaluate", "evaluate_many"]


class ExprError(Exception):
    """Raised for syntax errors, unknown variables/functions, bad arity,
    division or modulo by zero, or a domain error such as ``sqrt(-1)``.

    ``position`` is the 0-based character offset in the input where the
    problem was detected.
    """

    def __init__(self, message: str, position: int):
        super().__init__(f"{message} (at position {position})")
        self.message = message
        self.position = position


class _Token(NamedTuple):
    kind: str  # "number" | "ident" | "op" | "end"
    text: str
    start: int


def _sqrt(x: float) -> float:
    if x < 0:
        raise ValueError(f"sqrt of negative number {x!r}")
    return math.sqrt(x)


# name -> (implementation, minimum arity, maximum arity or None for unbounded)
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int | None]] = {
    "min": (min, 1, None),
    "max": (max, 1, None),
    "sqrt": (_sqrt, 1, 1),
    "abs": (abs, 1, 1),
}

_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}

_EXPONENT_OPS = ("^", "**")

_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<number>(?:\d+\.\d*|\.\d+|\d+))
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>\*\*|<=|>=|==|!=|[-+*/%^(),<>])
    )
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    end = len(text)
    while pos < end:
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            stripped = text[pos:].lstrip()
            if not stripped:
                break
            bad_pos = end - len(stripped)
            raise ExprError(f"unexpected character {stripped[0]!r}", bad_pos)
        kind = match.lastgroup
        assert kind is not None
        tokens.append(_Token(kind, match.group(kind), match.start(kind)))
        pos = match.end()
    tokens.append(_Token("end", "", end))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], variables: Mapping[str, object]):
        self._tokens = tokens
        self._pos = 0
        self._variables = variables

    # -- token helpers -----------------------------------------------------
    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _accept_op(self, *ops: str) -> _Token | None:
        token = self._peek()
        if token.kind == "op" and token.text in ops:
            self._advance()
            return token
        return None

    def _expect_op(self, op: str) -> None:
        if self._accept_op(op) is None:
            token = self._peek()
            raise ExprError(f"expected {op!r} but found {_describe(token)}", token.start)

    # -- grammar -----------------------------------------------------------
    def parse(self) -> float:
        value = self._comparison()
        token = self._peek()
        if token.kind != "end":
            raise ExprError(f"unexpected token {token.text!r}", token.start)
        return value

    def _comparison(self) -> float:
        value = self._expression()
        while (op := self._accept_op(*_COMPARISONS)) is not None:
            rhs = self._expression()
            value = 1.0 if _COMPARISONS[op.text](value, rhs) else 0.0
        return value

    def _expression(self) -> float:
        value = self._term()
        while (op := self._accept_op("+", "-")) is not None:
            rhs = self._term()
            value = value + rhs if op.text == "+" else value - rhs
        return value

    def _term(self) -> float:
        value = self._unary()
        while (op := self._accept_op("*", "/", "%")) is not None:
            rhs = self._unary()
            if op.text == "*":
                value = value * rhs
            elif op.text == "/":
                if rhs == 0:
                    raise ExprError("division by zero", op.start)
                value = value / rhs
            else:
                if rhs == 0:
                    raise ExprError("modulo by zero", op.start)
                value = value % rhs  # Python semantics: -7 % 3 == 2
        return value

    def _unary(self) -> float:
        if self._accept_op("-") is not None:
            return -self._unary()
        return self._power()

    def _power(self) -> float:
        base = self._primary()
        if (op := self._accept_op(*_EXPONENT_OPS)) is not None:
            exponent = self._unary()
            try:
                result = base ** exponent
            except ZeroDivisionError as exc:
                raise ExprError("division by zero", op.start) from exc
            except OverflowError as exc:
                raise ExprError("result too large", op.start) from exc
            if isinstance(result, complex):
                raise ExprError("result is not a real number", op.start)
            return float(result)
        return base

    def _primary(self) -> float:
        token = self._advance()
        if token.kind == "number":
            return float(token.text)
        if token.kind == "ident":
            return self._name(token)
        if token.kind == "op" and token.text == "(":
            value = self._comparison()
            self._expect_op(")")
            return value
        raise ExprError(
            f"expected a number, variable or '(' but found {_describe(token)}",
            token.start,
        )

    def _name(self, token: _Token) -> float:
        name = token.text
        if name in _FUNCTIONS:
            return self._call(token)
        if name in self._variables:
            try:
                return float(self._variables[name])  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ExprError(f"variable {name!r} is not numeric", token.start) from exc
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        raise ExprError(f"unknown variable {name!r}", token.start)

    def _call(self, name_token: _Token) -> float:
        name = name_token.text
        func, min_args, max_args = _FUNCTIONS[name]
        self._expect_op("(")
        args: list[float] = []
        if self._accept_op(")") is None:
            args.append(self._comparison())
            while self._accept_op(",") is not None:
                args.append(self._comparison())
            self._expect_op(")")
        if len(args) < min_args or (max_args is not None and len(args) > max_args):
            if max_args is None:
                expected = f"at least {min_args}"
            elif min_args == max_args:
                expected = str(min_args)
            else:
                expected = f"between {min_args} and {max_args}"
            raise ExprError(
                f"{name}() takes {expected} argument(s) but {len(args)} were given",
                name_token.start,
            )
        try:
            return float(func(*args))
        except ValueError as exc:
            raise ExprError(str(exc), name_token.start) from exc


def _describe(token: _Token) -> str:
    return "end of input" if token.kind == "end" else repr(token.text)


def evaluate(text: str, variables: dict | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float.

    Raises :class:`ExprError` on any syntax error, unknown variable, or
    division by zero.  The error's ``position`` attribute gives the 0-based
    offset in ``text`` where the problem was detected.
    """
    tokens = _tokenize(text)
    if tokens[0].kind == "end":
        raise ExprError("empty expression", tokens[0].start)
    return _Parser(tokens, variables or {}).parse()


def evaluate_many(texts: list[str], variables: dict | None = None) -> list:
    """Evaluate each expression in ``texts`` against the same ``variables``.

    Returns a list with one entry per input, in order: the float result, or
    the :class:`ExprError` instance for that expression instead of raising.
    """
    results: list = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
