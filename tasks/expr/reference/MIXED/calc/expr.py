"""Arithmetic expression evaluator: deliberately MIXED (both strategies live at once).

The parser started as recursive descent (one function per grammar level). When `%` and the
comparison operators were added, the additive/multiplicative operators (`+ - * / %`) were
moved into a shunting-yard loop (`parse_arith`) driven by the `_BINOPS` table with an explicit
operator stack and an output list in postfix order, evaluated by `_eval_postfix`. The
comparison level, unary minus, `^`, primaries and calls are still recursive-descent functions,
and the shunting loop obtains its operands by calling `parse_unary`, which in turn recurses
back into `parse_comparison` for parenthesised sub-expressions. So the same responsibility
(binary operator precedence) is handled by both strategies at once.
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


def _plain(fn):
    return lambda pos, a, b: fn(a, b)


# symbol -> (precedence, associativity, implementation(pos, lhs, rhs)); shunting-yard table
_BINOPS = {
    "+": (1, LEFT, _plain(operator.add)),
    "-": (1, LEFT, _plain(operator.sub)),
    "*": (2, LEFT, _plain(operator.mul)),
    "/": (2, LEFT, _div),
    "%": (2, LEFT, _mod),
}
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


def _eval_postfix(rpn: list) -> float:
    """Evaluate ("val", x) / ("op", sym, pos) items with a value stack."""
    stack: list[float] = []
    for item in rpn:
        if item[0] == "val":
            stack.append(item[1])
        else:
            _, sym, pos = item
            if len(stack) < 2:
                raise ExprError("missing operand", pos)
            b = stack.pop()
            a = stack.pop()
            stack.append(_BINOPS[sym][2](pos, a, b))
    if len(stack) != 1:
        raise ExprError("malformed expression", 0)
    return stack[0]


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

    # --- recursive-descent levels --------------------------------------------
    def parse_comparison(self) -> float:
        value = self.parse_arith()
        while self.at_op("<", "<=", ">", ">=", "==", "!="):
            op = self.advance().text
            rhs = self.parse_arith()
            if op == "<":
                value = float(value < rhs)
            elif op == "<=":
                value = float(value <= rhs)
            elif op == ">":
                value = float(value > rhs)
            elif op == ">=":
                value = float(value >= rhs)
            elif op == "==":
                value = float(value == rhs)
            else:
                value = float(value != rhs)
        return value

    # --- shunting-yard level for + - * / % -----------------------------------
    def parse_arith(self) -> float:
        """Shunting-yard over the `_BINOPS` operators. Operands are produced by the
        recursive `parse_unary`, so unary minus and `^` keep their recursive handling."""
        output: list = []
        op_stack: list = []
        output.append(("val", self.parse_unary()))
        while True:
            tok = self.peek()
            if tok.kind != "op" or tok.text not in _BINOPS:
                break
            self.advance()
            prec, assoc, _ = _BINOPS[tok.text]
            while op_stack:
                top_prec, top_assoc, _ = _BINOPS[op_stack[-1].text]
                if top_prec > prec or (top_prec == prec and assoc == LEFT):
                    top = op_stack.pop()
                    output.append(("op", top.text, top.pos))
                else:
                    break
            op_stack.append(tok)
            output.append(("val", self.parse_unary()))
        while op_stack:
            top = op_stack.pop()
            output.append(("op", top.text, top.pos))
        return _eval_postfix(output)

    def parse_unary(self) -> float:
        if self.at_op("-"):
            self.advance()
            return -self.parse_unary()
        return self.parse_power()

    def parse_power(self) -> float:
        base = self.parse_primary()
        if self.at_op("^"):
            tok = self.advance()
            exponent = self.parse_unary()
            try:
                result = base ** exponent
            except ZeroDivisionError:
                raise ExprError("zero to a negative power", tok.pos) from None
            except OverflowError:
                raise ExprError("result too large", tok.pos) from None
            if isinstance(result, complex):
                raise ExprError("complex result", tok.pos)
            return result
        return base

    def parse_primary(self) -> float:
        tok = self.peek()
        if tok.kind == "num":
            self.advance()
            return float(tok.text)
        if tok.kind == "id":
            self.advance()
            if self.at_op("("):
                return self.parse_call(tok)
            if tok.text in self.variables:
                return float(self.variables[tok.text])
            if tok.text in _CONSTANTS:
                return _CONSTANTS[tok.text]
            raise ExprError(f"unknown variable {tok.text!r}", tok.pos)
        if self.at_op("("):
            self.advance()
            value = self.parse_comparison()
            self.expect_op(")")
            return value
        if tok.kind == "end":
            raise ExprError("unexpected end of input", tok.pos)
        raise ExprError(f"unexpected token {tok.text!r}", tok.pos)

    def parse_call(self, name_tok: _Token) -> float:
        self.expect_op("(")
        args: list[float] = []
        if not self.at_op(")"):
            args.append(self.parse_comparison())
            while self.at_op(","):
                self.advance()
                args.append(self.parse_comparison())
        self.expect_op(")")
        fn = _FUNCTIONS.get(name_tok.text)
        if fn is None:
            raise ExprError(f"unknown function {name_tok.text!r}", name_tok.pos)
        return fn(name_tok.pos, args)

    def parse(self) -> float:
        value = self.parse_comparison()
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
