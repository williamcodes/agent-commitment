"""Arithmetic expression evaluator, Approach B: shunting-yard.

A single loop over the token list, driven by the `_OPERATORS` table (precedence,
associativity, arity, implementation), moves tokens between an explicit operator stack and
an output list in postfix (RPN) order. A second, non-recursive loop evaluates the RPN with
a value stack. There are no recursive grammar functions.
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


def _binary(fn):
    return lambda pos, a, b: fn(a, b)


def _cmp(fn):
    return lambda pos, a, b: float(fn(a, b))


# symbol -> (precedence, associativity, arity, implementation(pos, *operands))
_OPERATORS = {
    "<": (0, LEFT, 2, _cmp(operator.lt)),
    "<=": (0, LEFT, 2, _cmp(operator.le)),
    ">": (0, LEFT, 2, _cmp(operator.gt)),
    ">=": (0, LEFT, 2, _cmp(operator.ge)),
    "==": (0, LEFT, 2, _cmp(operator.eq)),
    "!=": (0, LEFT, 2, _cmp(operator.ne)),
    "+": (1, LEFT, 2, _binary(operator.add)),
    "-": (1, LEFT, 2, _binary(operator.sub)),
    "*": (2, LEFT, 2, _binary(operator.mul)),
    "/": (2, LEFT, 2, _div),
    "%": (2, LEFT, 2, _mod),
    "neg": (3, RIGHT, 1, lambda pos, a: -a),      # unary minus: looser than ^, tighter than * /
    "^": (4, RIGHT, 2, _pow),
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


def _tokenize(text: str) -> list[tuple[str, str, int]]:
    """Return (kind, text, pos) triples; kind in {num, id, op}."""
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
        tokens.append((kind, _ALIASES.get(tok, tok), m.start(kind)))
        i = m.end()
    return tokens


def _to_rpn(tokens, end_pos: int, variables: dict) -> list:
    """Shunting-yard: convert the token list to postfix. Output items are
    ("val", number, pos), ("op", symbol, pos) or ("call", name, argc, pos)."""
    output: list = []
    op_stack: list = []          # entries: ("op", sym, pos) | ("(", pos) | ("fn", name, pos)
    arg_counts: list = []        # per open function paren: [commas, saw_operand]
    expect_operand = True

    def pop_op():
        item = op_stack.pop()
        output.append(("op", item[1], item[2]))

    for kind, text, pos in tokens:
        if kind == "num":
            if not expect_operand:
                raise ExprError(f"unexpected token {text!r}", pos)
            output.append(("val", float(text), pos))
            expect_operand = False
            if arg_counts:
                arg_counts[-1][1] = True
        elif kind == "id":
            if not expect_operand:
                raise ExprError(f"unexpected token {text!r}", pos)
            # look ahead: identifier followed by "(" is a call
            idx = tokens.index((kind, text, pos))
            nxt = tokens[idx + 1] if idx + 1 < len(tokens) else None
            if nxt is not None and nxt[0] == "op" and nxt[1] == "(":
                if text not in _FUNCTIONS:
                    raise ExprError(f"unknown function {text!r}", pos)
                op_stack.append(("fn", text, pos))
                # expect_operand stays True; the "(" comes next
            else:
                if text in variables:
                    value = float(variables[text])
                elif text in _CONSTANTS:
                    value = _CONSTANTS[text]
                else:
                    raise ExprError(f"unknown variable {text!r}", pos)
                output.append(("val", value, pos))
                expect_operand = False
                if arg_counts:
                    arg_counts[-1][1] = True
        elif text == "(":
            if not expect_operand:
                raise ExprError("unexpected '('", pos)
            is_call = bool(op_stack) and op_stack[-1][0] == "fn"
            op_stack.append(("(", pos, is_call))
            if is_call:
                arg_counts.append([0, False])
            expect_operand = True
        elif text == ")":
            # allow "f()" only: ")" directly after a call's "("
            if expect_operand:
                top = op_stack[-1] if op_stack else None
                if not (top and top[0] == "(" and top[2] and not arg_counts[-1][1] and arg_counts[-1][0] == 0):
                    raise ExprError("unexpected ')'", pos)
            while op_stack and op_stack[-1][0] != "(":
                pop_op()
            if not op_stack:
                raise ExprError("unbalanced ')'", pos)
            _, open_pos, is_call = op_stack.pop()
            if is_call:
                commas, saw = arg_counts.pop()
                argc = 0 if (commas == 0 and not saw) else commas + 1
                _, name, fpos = op_stack.pop()
                output.append(("call", name, argc, fpos))
            expect_operand = False
            if arg_counts:
                arg_counts[-1][1] = True
        elif text == ",":
            if expect_operand:
                raise ExprError("unexpected ','", pos)
            while op_stack and op_stack[-1][0] != "(":
                pop_op()
            if not op_stack or not op_stack[-1][2]:
                raise ExprError("',' outside of a function call", pos)
            arg_counts[-1][0] += 1
            expect_operand = True
        else:
            # operator
            if expect_operand:
                if text != "-":
                    raise ExprError(f"unexpected token {text!r}", pos)
                # prefix operator: push without popping anything
                op_stack.append(("op", "neg", pos))
                continue
            prec, assoc, _, _ = _OPERATORS[text]
            while op_stack and op_stack[-1][0] == "op":
                top_prec, top_assoc, _, _ = _OPERATORS[op_stack[-1][1]]
                if top_prec > prec or (top_prec == prec and assoc == LEFT):
                    pop_op()
                else:
                    break
            op_stack.append(("op", text, pos))
            expect_operand = True

    if expect_operand:
        raise ExprError("unexpected end of input", end_pos)
    while op_stack:
        top = op_stack[-1]
        if top[0] != "op":
            raise ExprError("unexpected end of input, expected ')'", end_pos)
        pop_op()
    return output


def _eval_rpn(rpn: list) -> float:
    stack: list[float] = []
    for item in rpn:
        if item[0] == "val":
            stack.append(item[1])
        elif item[0] == "op":
            _, sym, pos = item
            _, _, arity, fn = _OPERATORS[sym]
            if len(stack) < arity:
                raise ExprError("missing operand", pos)
            operands = stack[-arity:]
            del stack[-arity:]
            stack.append(fn(pos, *operands))
        else:
            _, name, argc, pos = item
            args = stack[-argc:] if argc else []
            if argc:
                del stack[-argc:]
            stack.append(_FUNCTIONS[name](pos, args))
    if len(stack) != 1:
        raise ExprError("malformed expression", 0)
    return float(stack[0])


def evaluate(text: str, variables: dict | None = None) -> float:
    tokens = _tokenize(text)
    rpn = _to_rpn(tokens, len(text), variables or {})
    return _eval_rpn(rpn)


def evaluate_many(texts: list[str], variables: dict | None = None) -> list:
    out = []
    for t in texts:
        try:
            out.append(evaluate(t, variables))
        except ExprError as e:
            out.append(e)
    return out
