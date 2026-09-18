"""Arithmetic expression evaluator, precedence climbing (hybrid of A and B).

Recursive-descent functions handle the unary / power / primary / call levels, but every
binary operator is handled by ONE table-driven loop, `_binary(min_prec)`, which consults the
`_BINARY_OPS` table (precedence, associativity, implementation) and recurses into itself for
the right-hand operand with a higher minimum precedence. There is no operator stack, no
output queue and no postfix stage. Adding a binary operator is a table entry.
"""
from __future__ import annotations

import math
import operator
import re


class ExprError(Exception):
    def __init__(self, message: str, position: int):
        super().__init__(f"{message} at position {position}")
        self.position = position


_CONSTANTS = {"pi": math.pi, "e": math.e}

LEFT, RIGHT = "left", "right"


def _div(pos, a, b):
    if b == 0:
        raise ExprError("division by zero", pos)
    return a / b


def _mod(pos, a, b):
    if b == 0:
        raise ExprError("modulo by zero", pos)
    return a % b


def _pow(pos, a, b):
    try:
        r = a ** b
    except ZeroDivisionError:
        raise ExprError("zero to a negative power", pos) from None
    except OverflowError:
        raise ExprError("result too large", pos) from None
    if isinstance(r, complex):
        raise ExprError("complex result", pos)
    return r


def _plain(fn):
    return lambda pos, a, b: fn(a, b)


def _cmp(fn):
    return lambda pos, a, b: float(fn(a, b))


# symbol -> (precedence, associativity, implementation(pos, lhs, rhs))
_BINARY_OPS = {
    "<": (0, LEFT, _cmp(operator.lt)),
    "<=": (0, LEFT, _cmp(operator.le)),
    ">": (0, LEFT, _cmp(operator.gt)),
    ">=": (0, LEFT, _cmp(operator.ge)),
    "==": (0, LEFT, _cmp(operator.eq)),
    "!=": (0, LEFT, _cmp(operator.ne)),
    "+": (1, LEFT, _plain(operator.add)),
    "-": (1, LEFT, _plain(operator.sub)),
    "*": (2, LEFT, _plain(operator.mul)),
    "/": (2, LEFT, _div),
    "%": (2, LEFT, _mod),
    "^": (4, RIGHT, _pow),
}
_UNARY_MINUS_PREC = 3          # looser than ^, tighter than * / %
_ALIASES = {"**": "^"}


def _fn_min(pos, args):
    if not args:
        raise ExprError("min() needs at least one argument", pos)
    return min(args)


def _fn_max(pos, args):
    if not args:
        raise ExprError("max() needs at least one argument", pos)
    return max(args)


def _fn_sqrt(pos, args):
    if len(args) != 1:
        raise ExprError("sqrt() takes exactly one argument", pos)
    if args[0] < 0:
        raise ExprError("sqrt() of a negative number", pos)
    return math.sqrt(args[0])


def _fn_abs(pos, args):
    if len(args) != 1:
        raise ExprError("abs() takes exactly one argument", pos)
    return abs(args[0])


_FUNCTIONS = {"min": _fn_min, "max": _fn_max, "sqrt": _fn_sqrt, "abs": _fn_abs}

_TOKEN_RE = re.compile(
    r"\s*(?:(?P<num>\d+\.\d*|\.\d+|\d+)|(?P<id>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>\*\*|<=|>=|==|!=|[-+*/%^<>(),]))"
)


class _Token:
    __slots__ = ("kind", "text", "pos")

    def __init__(self, kind, text, pos):
        self.kind = kind
        self.text = text
        self.pos = pos


def _tokenize(text: str) -> list[_Token]:
    tokens = []
    i, n = 0, len(text)
    while i < n:
        m = _TOKEN_RE.match(text, i)
        if not m or m.end() == i:
            j = i
            while j < n and text[j].isspace():
                j += 1
            if j >= n:
                break
            raise ExprError(f"unexpected character {text[j]!r}", j)
        kind = m.lastgroup
        tok = m.group(kind)
        tokens.append(_Token(kind, _ALIASES.get(tok, tok), m.start(kind)))
        i = m.end()
    tokens.append(_Token("end", "", n))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], variables: dict):
        self.tokens = tokens
        self.i = 0
        self.variables = variables

    def peek(self) -> _Token:
        return self.tokens[self.i]

    def advance(self) -> _Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def at_op(self, *symbols) -> bool:
        tok = self.peek()
        return tok.kind == "op" and tok.text in symbols

    def expect_op(self, symbol: str) -> _Token:
        tok = self.peek()
        if tok.kind == "op" and tok.text == symbol:
            return self.advance()
        if tok.kind == "end":
            raise ExprError(f"unexpected end of input, expected {symbol!r}", tok.pos)
        raise ExprError(f"unexpected token {tok.text!r}, expected {symbol!r}", tok.pos)

    # --- precedence climbing -------------------------------------------------
    def _binary(self, min_prec: int) -> float:
        """Parse `unary (BINOP unary)*` for all binary operators whose precedence is at
        least `min_prec`, driven by the `_BINARY_OPS` table."""
        lhs = self._unary()
        while True:
            tok = self.peek()
            entry = _BINARY_OPS.get(tok.text) if tok.kind == "op" else None
            if entry is None or entry[0] < min_prec:
                return lhs
            prec, assoc, fn = entry
            self.advance()
            next_min = prec + 1 if assoc == LEFT else prec
            rhs = self._binary(next_min)
            lhs = fn(tok.pos, lhs, rhs)

    def _unary(self) -> float:
        if self.at_op("-"):
            self.advance()
            # unary minus binds looser than ^: parse its operand at the ^ level and above
            return -self._binary(_UNARY_MINUS_PREC)
        return self._primary()

    def _primary(self) -> float:
        tok = self.peek()
        if tok.kind == "num":
            self.advance()
            return float(tok.text)
        if tok.kind == "id":
            self.advance()
            if self.at_op("("):
                return self._call(tok)
            if tok.text in self.variables:
                return float(self.variables[tok.text])
            if tok.text in _CONSTANTS:
                return _CONSTANTS[tok.text]
            raise ExprError(f"unknown variable {tok.text!r}", tok.pos)
        if self.at_op("("):
            self.advance()
            value = self._binary(0)
            self.expect_op(")")
            return value
        if tok.kind == "end":
            raise ExprError("unexpected end of input", tok.pos)
        raise ExprError(f"unexpected token {tok.text!r}", tok.pos)

    def _call(self, name_tok: _Token) -> float:
        self.expect_op("(")
        args: list[float] = []
        if not self.at_op(")"):
            args.append(self._binary(0))
            while self.at_op(","):
                self.advance()
                args.append(self._binary(0))
        self.expect_op(")")
        fn = _FUNCTIONS.get(name_tok.text)
        if fn is None:
            raise ExprError(f"unknown function {name_tok.text!r}", name_tok.pos)
        return fn(name_tok.pos, args)

    def parse(self) -> float:
        value = self._binary(0)
        tok = self.peek()
        if tok.kind != "end":
            raise ExprError(f"unexpected token {tok.text!r}", tok.pos)
        return float(value)


def evaluate(text: str, variables: dict | None = None) -> float:
    return _Parser(_tokenize(text), variables or {}).parse()


def evaluate_many(texts: list[str], variables: dict | None = None) -> list:
    out = []
    for t in texts:
        try:
            out.append(evaluate(t, variables))
        except ExprError as e:
            out.append(e)
    return out
