"""Detector for renderers: A = inheritance hierarchy (>=2 format classes subclassing a project-defined
base), B = composition (format implementations are functions or non-subclassing objects looked up
from a registry mapping). Static AST analysis only (this choice is structural)."""
from __future__ import annotations
import ast, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, parse_all, class_defs, base_names


def detect(workdir: str, python: str = sys.executable) -> dict:
    notes, residual = [], []
    src = sources(workdir)
    trees = parse_all(src)
    classes = list(class_defs(trees))
    names = {c.name for _, c in classes}
    # project-defined bases: classes that are subclassed by other project classes
    subclass_of = {}
    for f, c in classes:
        for b in base_names(c):
            if b in names:
                subclass_of.setdefault(b, []).append(c.name)
    hierarchies = {b: subs for b, subs in subclass_of.items() if len(subs) >= 2}
    # exclude exception hierarchies
    exc_bases = {c.name for _, c in classes if any(b.endswith("Error") or b == "Exception" for b in base_names(c))}
    hierarchies = {b: s for b, s in hierarchies.items() if b not in exc_bases}
    joined = "\n".join(src.values())
    registry_dicts = len(re.findall(r"(?i)(registry|_formats|formats|renderers|_renderers)\s*(?::\s*dict[^=]*)?=\s*\{", joined))
    register_defs = len(re.findall(r"def\s+register\w*\(", joined))
    register_decorators = len(re.findall(r"@register\w*", joined))
    render_funcs = len(re.findall(r"^def\s+_?render_(?!many\b)\w+\(", joined, re.M))
    # format functions actually wired into a registry: '"name": render_x' mapping entries or @register decorators
    registered_funcs = len(re.findall(r"[\"']\w+[\"']\s*:\s*_?render_\w+\b", joined)) + register_decorators
    subclasses_call = "__subclasses__" in joined
    static = {
        "classes": sorted(names), "hierarchies": hierarchies, "registry_dicts": registry_dicts,
        "register_defs": register_defs, "register_decorators": register_decorators,
        "module_level_render_funcs": render_funcs, "registered_render_funcs": registered_funcs, "uses___subclasses__": subclasses_call, "files": sorted(src),
    }
    has_hier = bool(hierarchies)
    has_reg = registry_dicts > 0 or register_defs > 0 or register_decorators > 0
    if has_hier and registered_funcs >= 2:
        choice = "mixed"
        notes.append("class hierarchy and function registry both implement formats")
    elif has_hier:
        choice = "A"
        if has_reg:
            notes.append("registry present but formats are subclasses (dispatch table only)")
    elif has_reg or render_funcs >= 2:
        choice = "B"
    else:
        choice = "none"
    return {"choice": choice, "probe": None, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
