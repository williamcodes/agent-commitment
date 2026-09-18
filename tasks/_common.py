"""Shared helpers for task detectors. Detectors must be deterministic and self-explaining:
they return the raw probe/static signals alongside the classification so a human can disagree."""
from __future__ import annotations
import ast, json, os, re, subprocess, sys


def sources(workdir: str) -> dict[str, str]:
    out = {}
    for root, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if d not in {".git", "tests", "__pycache__", ".venv", "venv", ".pytest_cache"}]
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                try:
                    out[os.path.relpath(p, workdir)] = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    pass
    return out


def run_probe(workdir: str, code: str, python: str = sys.executable, timeout: int = 120) -> tuple[dict | None, str]:
    """Run probe code in a subprocess with cwd=workdir. The probe prints 'PROBE_RESULT {json}'."""
    try:
        r = subprocess.run([python, "-c", code], cwd=workdir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "probe timeout"
    except Exception as e:
        return None, "probe exception: %r" % e
    m = re.search(r"PROBE_RESULT (.*)", r.stdout)
    if not m:
        return None, "probe failed: " + (r.stderr[-800:] or r.stdout[-800:])
    try:
        return json.loads(m.group(1)), ""
    except Exception as e:
        return None, "probe output unparsable: %r" % e


def parse_all(src: dict[str, str]) -> dict[str, ast.AST]:
    out = {}
    for name, text in src.items():
        try:
            out[name] = ast.parse(text)
        except SyntaxError:
            pass
    return out


def class_defs(trees: dict[str, ast.AST]):
    for fname, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                yield fname, node


def func_defs(trees: dict[str, ast.AST]):
    for fname, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield fname, node


def base_names(cls: ast.ClassDef) -> list[str]:
    names = []
    for b in cls.bases:
        if isinstance(b, ast.Name):
            names.append(b.id)
        elif isinstance(b, ast.Attribute):
            names.append(b.attr)
        elif isinstance(b, ast.Subscript) and isinstance(b.value, ast.Name):
            names.append(b.value.id)
    return names


def result(choice: str, probe, static, residual, notes) -> dict:
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


PROBE_PRELUDE = "import json, os, sys\nsys.path.insert(0, os.getcwd())\n"
