"""Arithmetic expression evaluator (recursive descent, Approach A in SPEC.md).

Grammar (highest binding last):

    expression := additive (("<" | "<=" | ">" | ">=" | "==" | "!=") additive)*
    additive   := term (("+" | "-") term)*
    term       := unary (("*" | "/" | "%") unary)*
    unary      := "-" unary | power
    power      := primary (("^" | "**") unary)?   # right-associative; RHS may be signed
    primary    := NUMBER | call | IDENT | "(" expression ")"
    call       := IDENT "(" [expression ("," expression)*] ")"

Unary minus lives between term and power so that ``-2^2`` parses as ``-(2^2)``,
while the exponent's right-hand side re-enters ``unary`` so ``2^-1`` is allowed.
Comparisons bind loosest, are left-associative, and yield ``1.0`` or ``0.0``.

Identifiers are resolved against the caller's ``variables`` first, then the
built-in constants ``pi`` and ``e``. An identifier directly followed by ``(``
is a call to one of the built-in functions.

Every :class:`ExprError` carries ``position``: the 0-based character offset in
the input where the problem was detected.
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable, Mapping

__all__ = ["ExprError", "evaluate", "evaluate_many"]


class ExprError(Exception):
    """Raised for syntax errors, unknown names, and domain errors such as division by zero.

    ``position`` is the 0-based character offset where the problem was detected:
    the start of the offending token or identifier, the operator for arithmetic
    errors, the function name for call errors, or ``len(text)`` for unexpected
    end of input.
    """

    def __init__(self, message: str, position: int):
        super().__init__(f"{message} at position {position}")
        self.message = message
        self.position = position


_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}


def _sqrt(x: float) -> float:
    if x < 0:
        raise ValueError(f"sqrt of negative number {x!r}")
    return math.sqrt(x)


# name -> (implementation, minimum arity, maximum arity or None for unbounded).
# Implementations may raise ValueError for domain errors; _call converts it to ExprError.
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int | None]] = {
    "min": (lambda *args: min(args), 1, None),
    "max": (lambda *args: max(args), 1, None),
    "sqrt": (_sqrt, 1, 1),
    "abs": (abs, 1, 1),
}

# Spellings that are accepted as another operator.
_ALIASES: dict[str, str] = {"**": "^"}

# Comparison operators: lowest precedence, left-associative, result is 1.0 or 0.0.
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
    (?P<ws>\s+)
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\*\*|<=|>=|==|!=|[-+*/%^<>(),])
    """,
    re.VERBOSE,
)

# A token is (kind, text, start offset). The list ends with an ("end", "", len(text)) sentinel.
_Token = tuple[str, str, int]


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = match.lastgroup
        if kind != "ws":
            value = match.group()
            tokens.append((kind, _ALIASES.get(value, value), pos))
        pos = match.end()
    tokens.append(("end", "", len(text)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], variables: Mapping[str, float]):
        self._tokens = tokens
        self._pos = 0
        self._variables = variables

    # -- token helpers -------------------------------------------------

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _accept(self, value: str) -> _Token | None:
        """Consume and return the current token if it is the operator ``value``."""
        token = self._peek()
        if token[0] == "op" and token[1] == value:
            self._pos += 1
            return token
        return None

    def _expect(self, value: str) -> None:
        if not self._accept(value):
            self._fail(f"expected {value!r} but found {self._describe()}")

    def _describe(self) -> str:
        kind, text, _ = self._peek()
        return "end of input" if kind == "end" else repr(text)

    def _fail(self, message: str) -> None:
        """Raise an ExprError anchored at the current token."""
        raise ExprError(message, self._peek()[2])

    # -- grammar -------------------------------------------------------

    def parse(self) -> float:
        value = self._expression()
        if self._peek()[0] != "end":
            self._fail(f"unexpected {self._describe()}")
        return value

    def _expression(self) -> float:
        value = self._additive()
        while True:
            kind, text, _ = self._peek()
            if kind == "op" and text in _COMPARISONS:
                self._advance()
                value = float(_COMPARISONS[text](value, self._additive()))
            else:
                return value

    def _additive(self) -> float:
        value = self._term()
        while True:
            if self._accept("+"):
                value += self._term()
            elif self._accept("-"):
                value -= self._term()
            else:
                return value

    def _term(self) -> float:
        value = self._unary()
        while True:
            if self._accept("*"):
                value *= self._unary()
            elif op := self._accept("/"):
                divisor = self._unary()
                if divisor == 0:
                    raise ExprError("division by zero", op[2])
                value /= divisor
            elif op := self._accept("%"):
                divisor = self._unary()
                if divisor == 0:
                    raise ExprError("modulo by zero", op[2])
                value %= divisor
            else:
                return value

    def _unary(self) -> float:
        if self._accept("-"):
            return -self._unary()
        return self._power()

    def _power(self) -> float:
        base = self._primary()
        if op := self._accept("^"):
            exponent = self._unary()  # right-associative, allows a signed exponent
            try:
                result = base ** exponent
            except ZeroDivisionError:
                raise ExprError("zero to a negative power", op[2]) from None
            except OverflowError:
                raise ExprError("result too large", op[2]) from None
            if isinstance(result, complex):
                raise ExprError("result is not a real number", op[2])
            return result
        return base

    def _primary(self) -> float:
        kind, text, pos = self._peek()
        if kind == "number":
            self._advance()
            return float(text)
        if kind == "ident":
            self._advance()
            if self._accept("("):
                return self._call(text, pos)
            return self._lookup(text, pos)
        if self._accept("("):
            value = self._expression()
            self._expect(")")
            return value
        self._fail(f"unexpected {self._describe()}")
        raise AssertionError("unreachable")

    def _lookup(self, name: str, pos: int) -> float:
        if name in self._variables:
            try:
                return float(self._variables[name])
            except (TypeError, ValueError):
                raise ExprError(f"variable {name!r} is not numeric", pos) from None
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        raise ExprError(f"unknown variable {name!r}", pos)

    def _call(self, name: str, pos: int) -> float:
        """Parse the argument list after ``name(`` and apply the built-in function.

        ``pos`` is the offset of the function name; call-related errors are reported there.
        """
        if name not in _FUNCTIONS:
            raise ExprError(f"unknown function {name!r}", pos)
        func, min_arity, max_arity = _FUNCTIONS[name]
        args: list[float] = []
        if not self._accept(")"):
            args.append(self._expression())
            while self._accept(","):
                args.append(self._expression())
            self._expect(")")
        if len(args) < min_arity or (max_arity is not None and len(args) > max_arity):
            expected = (
                f"at least {min_arity}" if max_arity is None
                else str(min_arity) if min_arity == max_arity
                else f"between {min_arity} and {max_arity}"
            )
            raise ExprError(f"{name}() takes {expected} argument(s), got {len(args)}", pos)
        try:
            return float(func(*args))
        except ValueError as exc:
            raise ExprError(str(exc), pos) from None


def evaluate(text: str, variables: dict | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float.

    Raises :class:`ExprError` on syntax errors, unknown names, or domain errors.
    """
    if not isinstance(text, str):
        raise ExprError("expression must be a string", 0)
    return _Parser(_tokenize(text), variables or {}).parse()


def evaluate_many(texts: list[str], variables: dict | None = None) -> list:
    """Evaluate each expression against the same ``variables``.

    Returns one entry per input: the float result, or the :class:`ExprError`
    instance for expressions that fail, so one bad expression does not stop the rest.
    """
    results: list = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
