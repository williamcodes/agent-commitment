"""Arithmetic expression evaluator (Approach A: recursive descent).

Grammar (one function per precedence level):

    comparison := expression (('<' | '<=' | '>' | '>=' | '==' | '!=') expression)*
    expression := term (('+' | '-') term)*
    term       := unary (('*' | '/' | '%') unary)*
    unary      := '-' unary | power
    power      := primary (('^' | '**') unary)?  # right-associative
    primary    := NUMBER | call | IDENT | '(' comparison ')'
    call       := IDENT '(' [comparison (',' comparison)*] ')'

Comparisons have the lowest precedence, are left-associative, and yield
``1.0`` or ``0.0``.

Placing ``unary`` above ``power`` makes ``-2^2`` parse as ``-(2^2)``, while
letting the exponent's right operand be a ``unary`` allows ``2 ^ -1``.

Every token carries its 0-based character offset in the input, and every
``ExprError`` reports the offset where the problem was detected.
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
    division or modulo by zero, and domain errors such as ``sqrt(-1)``.

    ``position`` is the 0-based character offset in the input where the
    problem was detected: the start of the offending token or identifier,
    or ``len(text)`` for unexpected end of input.
    """

    def __init__(self, message: str, position: int | None = None):
        super().__init__(message)
        self.message = message
        self.position = position

    def __str__(self) -> str:
        if self.position is None:
            return self.message
        return f"{self.message} (at position {self.position})"


class Token(NamedTuple):
    kind: str   # "number" | "ident" | "op" | "eof"
    value: str
    pos: int    # 0-based offset of the token's first character


_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<number>\d+\.\d*|\.\d+|\d+)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>\*\*|<=|>=|==|!=|[-+*/%^(),<>])
    )
    """,
    re.VERBOSE,
)

# Operator spellings that are pure aliases of another operator.
_OP_ALIASES = {"**": "^"}


def _tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            # Either an invalid character or only trailing whitespace remains.
            stripped = text[pos:].lstrip()
            if not stripped:
                break
            bad_pos = len(text) - len(stripped)
            raise ExprError(f"unexpected character {text[bad_pos]!r}", bad_pos)
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "op":
            value = _OP_ALIASES.get(value, value)
        tokens.append(Token(kind, value, match.start(kind)))
        pos = match.end()
    tokens.append(Token("eof", "", len(text)))
    return tokens


# -- comparison operators ----------------------------------------------------

_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


# -- built-in names ----------------------------------------------------------

_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}


def _sqrt(x: float) -> float:
    if x < 0:
        raise ExprError(f"sqrt of negative number {x}")
    return math.sqrt(x)


# name -> (implementation, min_args, max_args or None for unbounded)
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int | None]] = {
    "min": (min, 1, None),
    "max": (max, 1, None),
    "sqrt": (_sqrt, 1, 1),
    "abs": (abs, 1, 1),
}


def _call_function(name: str, args: list[float], pos: int) -> float:
    try:
        func, min_args, max_args = _FUNCTIONS[name]
    except KeyError:
        raise ExprError(f"unknown function {name!r}", pos) from None
    n = len(args)
    if n < min_args or (max_args is not None and n > max_args):
        if max_args is None:
            expected = f"at least {min_args}"
        elif min_args == max_args:
            expected = str(min_args)
        else:
            expected = f"between {min_args} and {max_args}"
        raise ExprError(f"{name}() takes {expected} argument(s) but {n} were given", pos)
    try:
        return float(func(*args))
    except ExprError as exc:
        if exc.position is None:
            exc.position = pos
        raise


class _Parser:
    def __init__(self, tokens: list[Token], variables: Mapping[str, float]):
        self._tokens = tokens
        self._pos = 0
        self._variables = variables

    # -- token helpers -----------------------------------------------------
    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _accept_op(self, *ops: str) -> Token | None:
        token = self._peek()
        if token.kind == "op" and token.value in ops:
            self._advance()
            return token
        return None

    def _expect_op(self, op: str) -> None:
        if self._accept_op(op) is None:
            token = self._peek()
            raise ExprError(f"expected {op!r} but found {self._describe(token)}", token.pos)

    @staticmethod
    def _describe(token: Token) -> str:
        return "end of input" if token.kind == "eof" else repr(token.value)

    # -- grammar -----------------------------------------------------------
    def parse(self) -> float:
        value = self._comparison()
        token = self._peek()
        if token.kind != "eof":
            raise ExprError(f"unexpected token {token.value!r}", token.pos)
        return value

    def _comparison(self) -> float:
        value = self._expression()
        while (op := self._accept_op(*_COMPARISONS)) is not None:
            rhs = self._expression()
            value = 1.0 if _COMPARISONS[op.value](value, rhs) else 0.0
        return value

    def _expression(self) -> float:
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
                    raise ExprError("division by zero", op.pos)
                value = value / rhs
            else:
                if rhs == 0:
                    raise ExprError("modulo by zero", op.pos)
                value = value % rhs  # Python semantics: -7 % 3 == 2
        return value

    def _unary(self) -> float:
        if self._accept_op("-") is not None:
            return -self._unary()
        return self._power()

    def _power(self) -> float:
        base = self._primary()
        if (op := self._accept_op("^")) is not None:
            exponent = self._unary()  # right-associative; permits ``2 ^ -1``
            try:
                result = base ** exponent
            except ZeroDivisionError as exc:
                raise ExprError("division by zero", op.pos) from exc
            except OverflowError as exc:
                raise ExprError("result too large", op.pos) from exc
            if isinstance(result, complex):
                raise ExprError("result is not a real number", op.pos)
            return result
        return base

    def _primary(self) -> float:
        token = self._advance()
        if token.kind == "number":
            return float(token.value)
        if token.kind == "ident":
            if self._accept_op("(") is not None:
                return self._call(token)
            return self._lookup(token)
        if token.kind == "op" and token.value == "(":
            inner = self._comparison()
            self._expect_op(")")
            return inner
        raise ExprError(
            f"expected a number, variable or '(' but found {self._describe(token)}", token.pos
        )

    def _lookup(self, token: Token) -> float:
        """Resolve an identifier: caller-supplied variables shadow constants."""
        name = token.value
        if name in self._variables:
            return float(self._variables[name])
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        raise ExprError(f"unknown variable {name!r}", token.pos)

    def _call(self, name_token: Token) -> float:
        """Parse the argument list after ``name(`` and apply the function."""
        args: list[float] = []
        if self._accept_op(")") is None:
            args.append(self._comparison())
            while self._accept_op(",") is not None:
                args.append(self._comparison())
            self._expect_op(")")
        return _call_function(name_token.value, args, name_token.pos)


def evaluate(text: str, variables: Mapping[str, float] | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float.

    Raises ExprError (with a ``.position`` offset) for syntax errors, unknown
    variables or functions, wrong arity, division/modulo by zero, or domain
    errors.
    """
    if not isinstance(text, str):
        raise ExprError("expression must be a string", 0)
    return _Parser(_tokenize(text), variables or {}).parse()


def evaluate_many(
    texts: list[str], variables: Mapping[str, float] | None = None
) -> list[float | ExprError]:
    """Evaluate each expression against the same variables.

    Returns one entry per input: the value, or the ExprError instance that
    would have been raised. Errors never propagate.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
