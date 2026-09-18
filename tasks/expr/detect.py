"""Detector for expr: A = recursive descent (mutually recursive parse functions per grammar level, or
precedence climbing), B = shunting-yard (operator table + explicit stacks, no recursive parse
functions). Static AST analysis: find functions in the calc package that call other parse-like
functions or themselves (recursion) versus a precedence table + stack loop."""
from __future__ import annotations
import ast, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, parse_all


def _calls(fn: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def detect(workdir: str, python: str = sys.executable) -> dict:
    notes, residual = [], []
    src = {k: v for k, v in sources(workdir).items() if k.startswith("calc")}
    trees = parse_all(src)
    funcs = {}
    for fname, tree in trees.items():
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                funcs[n.name] = n
    parse_like = {n for n in funcs if re.search(r"(parse|expr|term|factor|power|unary|primary|atom|climb|binary|comparison|additive|multiplicative)", n, re.I)}
    graph = {n: (_calls(funcs[n]) & parse_like) for n in parse_like}
    # recursion: a cycle among parse-like functions (incl. self-recursion)
    def reachable(start):
        seen, stack = set(), [start]
        while stack:
            x = stack.pop()
            for y in graph.get(x, ()):
                if y not in seen:
                    seen.add(y); stack.append(y)
        return seen
    recursive = sorted(n for n in parse_like if n in reachable(n))
    joined = "\n".join(src.values())
    # A precedence table is a dict literal with >= 3 entries whose values carry an integer precedence (int, or a
    # tuple/list containing an int). A one-entry alias map such as {"**": "^"} is not a table (round-2 review, finding 1).
    prec_table = 0
    for fname, tree in trees.items():
        for n in ast.walk(tree):
            if isinstance(n, ast.Dict) and len(n.keys) >= 3:
                def has_int(v):
                    if isinstance(v, ast.Constant) and isinstance(v.value, int) and not isinstance(v.value, bool): return True
                    if isinstance(v, (ast.Tuple, ast.List)): return any(has_int(e) for e in v.elts)
                    if isinstance(v, ast.Call): return any(has_int(a) for a in n_args(v))
                    return False
                def n_args(c): return list(c.args) + [k.value for k in c.keywords]
                if sum(1 for v in n.values if v is not None and has_int(v)) >= 3:
                    prec_table += 1
    # a binary-operator loop that reads precedence from a table: a while/for loop whose body subscripts a name into the
    # table or compares a precedence variable (precedence climbing / shunting-yard)
    table_loop = bool(re.search(r"(while|for)[^\n]*:\n(?:[^\n]*\n){0,12}?[^\n]*(prec|precedence|priority|min_prec|_bp|binding)", joined, re.I))
    stack_words = len(re.findall(r"\b(op_stack|ops|operators|output|out_queue|rpn|postfix|stack)\b", joined))
    while_loops_pop = len(re.findall(r"while\s+[^\n]*:\n(?:[^\n]*\n){0,6}?[^\n]*\.pop\(\)", joined))
    shunting_words = len(re.findall(r"(?i)shunting|postfix|rpn", joined))
    static = {"parse_like_functions": sorted(parse_like), "recursive_parse_functions": recursive,
              "precedence_table_literals": prec_table, "table_driven_loop": table_loop, "stack_words": stack_words,
              "shunting_words": shunting_words, "while_pop_loops": while_loops_pop, "files": sorted(src)}
    rd = len(recursive) >= 2 or (len(recursive) == 1 and len(parse_like) >= 3)
    sy = prec_table >= 1 and (stack_words >= 3 or while_loops_pop >= 1)
    # structural shunting-yard signal: an operator table plus a loop that pops an explicit stack.
    # Vocabulary alone (docstrings mentioning stacks/postfix) must not turn precedence climbing into "mixed".
    sy_structural = prec_table >= 1 and while_loops_pop >= 1
    if rd and sy_structural:
        choice = "mixed"; notes.append("both recursive grammar functions and a shunting-yard table/stack machinery present")
    elif rd and prec_table >= 1 and table_loop:
        # v2 (post-review): precedence climbing = recursive functions for the fixed grammar plus ONE table-driven
        # binary-operator loop. SPEC.md defines A as one function per precedence level, so this is a third design.
        # Round-2 correction: requires a real precedence table (>= 3 entries with integer precedences) AND a loop that
        # reads precedence from it; a one-entry alias map does not qualify.
        choice = "hybrid"; notes.append("precedence climbing: recursive grammar functions with a table-driven binary-operator loop")
    elif rd:
        choice = "A"
    elif sy or shunting_words >= 1:
        choice = "B"
    else:
        choice = "none"
    return {"choice": choice, "probe": None, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
