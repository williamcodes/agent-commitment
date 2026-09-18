"""Arithmetic expression evaluator (recursive descent, Approach A in SPEC.md).

Grammar (highest precedence at the bottom):

    expr     := additive (CMP additive)*     # CMP is one of < <= > >= == !=; left-assoc
    additive := term (('+' | '-') term)*
    term     := unary (('*' | '/' | '%') unary)*
    unary    := '-' unary | power
    power    := primary ('^' unary)?         # right-associative; exponent may be signed
    primary  := NUMBER | IDENT | call | '(' expr ')'
    call     := IDENT '(' (expr (',' expr)*)? ')'

Unary minus sits between the multiplicative level and '^', so ``-2^2`` parses
as ``-(2^2)`` while ``2 ^ -1`` is still allowed via the ``unary`` on the right
of ``^``.

``%`` is modulo with Python semantics (``-7 % 3 == 2``) at the same precedence
as ``*`` and ``/``. ``**`` is an alias for ``^`` (the lexer normalises it, so
the grammar only ever sees ``^``). Built-in functions (``min``, ``max``,
``sqrt``, ``abs``) are called with ``name(arg, ...)``; each argument is a full
expression. The constants ``pi`` and ``e`` are available as identifiers; a
caller-supplied variable of the same name shadows the constant.

Comparison operators (``< <= > >= == !=``) have the lowest precedence, are
left-associative, and yield ``1.0`` for true and ``0.0`` for false, so
``3 > 2 > 1`` is ``(3 > 2) > 1`` which is ``1 > 1`` which is ``0.0``.

``evaluate_many`` evaluates a list of expressions against one shared
``variables`` mapping and returns a list of results, substituting the
``ExprError`` instance for any expression that fails instead of raising.

Every ``ExprError`` carries a ``position``: the 0-based character offset in the
input where the problem was detected (the start of the offending token, or
``len(text)`` for an unexpected end of input).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping

__all__ = ["ExprError", "evaluate", "evaluate_many"]


class ExprError(Exception):
    """Raised for syntax errors, unknown variables/functions, bad arity, or division by zero.

    ``position`` is the 0-based character offset in the input where the problem
    was detected.
    """

    def __init__(self, message: str, position: int | None = None):
        super().__init__(message)
        self.position = position

    def __str__(self) -> str:
        message = self.args[0] if self.args else ""
        if self.position is None:
            return message
        return f"{message} (at position {self.position})"


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>(?:\d+\.\d*|\.\d+|\d+))
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\*\*|<=|>=|==|!=|[-+*/%^(),<>])
    """,
    re.VERBOSE,
)

# Operator spellings that are pure aliases; normalised away in the lexer.
_OP_ALIASES = {"**": "^"}

# Comparison operators: all at the same (lowest) precedence level, left-associative.
_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

# A token is (kind, value, start offset).
Token = tuple[str, str, int]


def _tokenize(text: str) -> list[Token]:
    """Return a list of (kind, value, position) tokens, terminated by an EOF marker."""
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise ExprError(f"unexpected character {text[pos]!r}", pos)
        kind = match.lastgroup
        if kind != "ws":
            value = match.group()
            if kind == "op":
                value = _OP_ALIASES.get(value, value)
            tokens.append((kind, value, pos))
        pos = match.end()
    tokens.append(("eof", "", len(text)))
    return tokens


# ---------------------------------------------------------------------------
# Built-ins
# ---------------------------------------------------------------------------

_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


def _sqrt(x: float) -> float:
    if x < 0:
        raise ExprError(f"sqrt of negative number {x!r}")
    return math.sqrt(x)


def _variadic(name: str, fn: Callable[..., float]) -> Callable[..., float]:
    def call(*args: float) -> float:
        if not args:
            raise ExprError(f"{name}() expects at least one argument")
        return fn(*args)

    return call


# name -> (function, arity); arity None means "one or more".
_FUNCTIONS: dict[str, tuple[Callable[..., float], int | None]] = {
    "min": (_variadic("min", min), None),
    "max": (_variadic("max", max), None),
    "sqrt": (_sqrt, 1),
    "abs": (abs, 1),
}


# ---------------------------------------------------------------------------
# Parser / evaluator
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[Token], variables: Mapping[str, object]):
        self._tokens = tokens
        self._pos = 0
        self._variables = variables

    # -- token helpers ------------------------------------------------------

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _accept(self, *values: str) -> Token | None:
        """Consume and return the next token if it is one of the given operators."""
        token = self._peek()
        if token[0] == "op" and token[1] in values:
            self._pos += 1
            return token
        return None

    def _expect(self, value: str) -> None:
        if self._accept(value) is None:
            raise self._unexpected(f"expected {value!r} but found")

    def _unexpected(self, prefix: str) -> ExprError:
        """Build an error about the current token, positioned at its start."""
        kind, value, start = self._peek()
        found = "end of input" if kind == "eof" else repr(value)
        return ExprError(f"{prefix} {found}", start)

    # -- grammar ------------------------------------------------------------

    def parse(self) -> float:
        result = self._expr()
        if self._peek()[0] != "eof":
            raise self._unexpected("unexpected token")
        return result

    def _expr(self) -> float:
        result = self._additive()
        while (op := self._accept(*_COMPARISONS)) is not None:
            rhs = self._additive()
            result = 1.0 if _COMPARISONS[op[1]](result, rhs) else 0.0
        return result

    def _additive(self) -> float:
        result = self._term()
        while (op := self._accept("+", "-")) is not None:
            rhs = self._term()
            result = result + rhs if op[1] == "+" else result - rhs
        return result

    def _term(self) -> float:
        result = self._unary()
        while (op := self._accept("*", "/", "%")) is not None:
            rhs = self._unary()
            if op[1] == "*":
                result = result * rhs
            elif op[1] == "/":
                if rhs == 0:
                    raise ExprError("division by zero", op[2])
                result = result / rhs
            else:
                if rhs == 0:
                    raise ExprError("modulo by zero", op[2])
                result = result % rhs
        return result

    def _unary(self) -> float:
        if self._accept("-") is not None:
            return -self._unary()
        return self._power()

    def _power(self) -> float:
        base = self._primary()
        if (op := self._accept("^")) is not None:
            exponent = self._unary()  # right-assoc; allows a signed exponent
            try:
                result = base**exponent
            except ZeroDivisionError as exc:
                raise ExprError("division by zero", op[2]) from exc
            except OverflowError as exc:
                raise ExprError("result too large", op[2]) from exc
            if isinstance(result, complex):
                raise ExprError("result is not a real number", op[2])
            return result
        return base

    def _primary(self) -> float:
        kind, value, start = self._peek()
        if kind == "num":
            self._advance()
            return float(value)
        if kind == "ident":
            self._advance()
            if self._peek()[:2] == ("op", "("):
                return self._call(value, start)
            return self._lookup(value, start)
        if kind == "op" and value == "(":
            self._advance()
            result = self._expr()
            self._expect(")")
            return result
        raise self._unexpected("expected a number, variable, or '(' but found")

    def _lookup(self, name: str, start: int) -> float:
        """Resolve an identifier: caller variables first, then built-in constants."""
        if name in self._variables:
            raw = self._variables[name]
        elif name in _CONSTANTS:
            raw = _CONSTANTS[name]
        else:
            raise ExprError(f"unknown variable {name!r}", start)
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise ExprError(f"variable {name!r} is not numeric", start) from exc

    def _call(self, name: str, start: int) -> float:
        """Parse ``'(' args ')'`` following a function name and apply the function.

        Errors about the call itself (unknown name, arity, domain errors raised
        by the function) are positioned at the function name.
        """
        try:
            fn, arity = _FUNCTIONS[name]
        except KeyError:
            raise ExprError(f"unknown function {name!r}", start) from None
        self._expect("(")
        args: list[float] = []
        if self._accept(")") is None:
            args.append(self._expr())
            while self._accept(",") is not None:
                args.append(self._expr())
            self._expect(")")
        if arity is not None and len(args) != arity:
            raise ExprError(
                f"{name}() expects {arity} argument{'s' if arity != 1 else ''}, got {len(args)}",
                start,
            )
        try:
            return float(fn(*args))
        except ExprError as exc:
            if exc.position is None:
                exc.position = start
            raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate(text: str, variables: dict | None = None) -> float:
    """Evaluate an arithmetic expression and return the result as a float.

    Raises ``ExprError`` on any syntax error, unknown variable, or division by zero.
    The error's ``position`` attribute gives the 0-based offset of the problem.
    """
    return _Parser(_tokenize(text), variables or {}).parse()


def evaluate_many(texts: list[str], variables: dict | None = None) -> list:
    """Evaluate each expression in ``texts`` against the same ``variables``.

    Returns a list with one entry per input, in order: the float result, or
    the ``ExprError`` instance (not raised) for an expression that failed.
    """
    results: list[float | ExprError] = []
    for text in texts:
        try:
            results.append(evaluate(text, variables))
        except ExprError as exc:
            results.append(exc)
    return results
