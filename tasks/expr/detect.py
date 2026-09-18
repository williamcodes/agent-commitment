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
    prec_table = len(re.findall(r"(?i)(prec|precedence|priority)\w*\s*(?::[^=]+)?=\s*\{", joined))
    stack_words = len(re.findall(r"\b(op_stack|ops|operators|output|out_queue|rpn|postfix|stack)\b", joined))
    while_loops_pop = len(re.findall(r"while\s+\w+\s*(and|&&).*?\.pop\(\)", joined, re.S))
    shunting_words = len(re.findall(r"(?i)shunting|postfix|rpn", joined))
    static = {"parse_like_functions": sorted(parse_like), "recursive_parse_functions": recursive,
              "precedence_table_literals": prec_table, "stack_words": stack_words,
              "shunting_words": shunting_words, "files": sorted(src)}
    rd = len(recursive) >= 2 or (len(recursive) == 1 and len(parse_like) >= 3)
    sy = prec_table >= 1 and stack_words >= 3
    if rd and sy and shunting_words >= 1:
        choice = "mixed"; notes.append("both recursive grammar functions and a shunting-yard table/stack machinery present")
    elif rd:
        choice = "A"
        if prec_table:
            notes.append("precedence table present (precedence climbing is still recursive -> A)")
    elif sy or shunting_words >= 1:
        choice = "B"
    else:
        choice = "none"
    return {"choice": choice, "probe": None, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
