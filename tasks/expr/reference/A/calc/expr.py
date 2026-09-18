"""Arithmetic expression evaluator, Approach A: recursive descent.

One function per precedence level, calling each other recursively over a token list:

    comparison := additive (('<'|'<='|'>'|'>='|'=='|'!=') additive)*
    additive   := multiplicative (('+'|'-') multiplicative)*
    multiplicative := unary (('*'|'/'|'%') unary)*
    unary      := '-' unary | power
    power      := primary ('^' unary)?          # right-associative; exponent may be unary
    primary    := NUMBER | IDENT | IDENT '(' args ')' | '(' comparison ')'

Values are computed as the parse proceeds.
"""
from __future__ import annotations

import math
import re


class ExprError(Exception):
    def __init__(self, message: str, position: int):
        super().__init__(f"{message} at position {position}")
        self.position = position


_CONSTANTS = {"pi": math.pi, "e": math.e}


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
    i = 0
    n = len(text)
    while i < n:
        m = _TOKEN_RE.match(text, i)
        if not m or m.end() == i:
            # skip whitespace then report
            j = i
            while j < n and text[j].isspace():
                j += 1
            if j >= n:
                break
            raise ExprError(f"unexpected character {text[j]!r}", j)
        kind = m.lastgroup
        tok_text = m.group(kind)
        tokens.append(_Token(kind, "^" if tok_text == "**" else tok_text, m.start(kind)))
        i = m.end()
    tokens.append(_Token("end", "", n))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], variables: dict):
        self.tokens = tokens
        self.i = 0
        self.variables = variables

    # --- token helpers -------------------------------------------------------
    def peek(self) -> _Token:
        return self.tokens[self.i]

    def advance(self) -> _Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def at_op(self, *ops) -> bool:
        tok = self.peek()
        return tok.kind == "op" and tok.text in ops

    def expect_op(self, op: str) -> _Token:
        tok = self.peek()
        if tok.kind == "op" and tok.text == op:
            return self.advance()
        if tok.kind == "end":
            raise ExprError(f"unexpected end of input, expected {op!r}", tok.pos)
        raise ExprError(f"unexpected token {tok.text!r}, expected {op!r}", tok.pos)

    # --- grammar levels ------------------------------------------------------
    def parse_comparison(self) -> float:
        value = self.parse_additive()
        while self.at_op("<", "<=", ">", ">=", "==", "!="):
            op = self.advance().text
            rhs = self.parse_additive()
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

    def parse_additive(self) -> float:
        value = self.parse_multiplicative()
        while self.at_op("+", "-"):
            op = self.advance().text
            rhs = self.parse_multiplicative()
            value = value + rhs if op == "+" else value - rhs
        return value

    def parse_multiplicative(self) -> float:
        value = self.parse_unary()
        while self.at_op("*", "/", "%"):
            tok = self.advance()
            rhs = self.parse_unary()
            if tok.text == "*":
                value = value * rhs
            elif tok.text == "/":
                if rhs == 0:
                    raise ExprError("division by zero", tok.pos)
                value = value / rhs
            else:
                if rhs == 0:
                    raise ExprError("modulo by zero", tok.pos)
                value = value % rhs
        return value

    def parse_unary(self) -> float:
        if self.at_op("-"):
            self.advance()
            return -self.parse_unary()
        return self.parse_power()

    def parse_power(self) -> float:
        base = self.parse_primary()
        if self.at_op("^"):
            tok = self.advance()
            exponent = self.parse_unary()   # right-assoc; exponent may carry unary minus
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
    tokens = _tokenize(text)
    return _Parser(tokens, variables or {}).parse()


def evaluate_many(texts: list[str], variables: dict | None = None) -> list:
    out = []
    for t in texts:
        try:
            out.append(evaluate(t, variables))
        except ExprError as e:
            out.append(e)
    return out
