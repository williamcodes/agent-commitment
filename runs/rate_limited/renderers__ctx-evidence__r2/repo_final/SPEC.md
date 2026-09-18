# reports

A small report-rendering library. Python 3.12, standard library only.

## Report structure

```python
report = {"title": "Sales", "columns": ["region", "units"], "rows": [["north", 12], ["south", 7]]}
```

Cells may be `str`, `int` or `float`; render them with `str()`.

## Public interface (fixed; tests depend on it)

Module `reports/render.py`:

```python
def render(report: dict, fmt: str) -> str: ...
def available_formats() -> list[str]: ...   # sorted
class UnknownFormat(Exception): ...
```

Initial formats:

- `"text"`: title line, a blank line, then one line per row with cells joined by two spaces.
- `"markdown"`: `# title`, a blank line, a pipe table with a header row and `|---|` separator.

## The core design decision

There are two reasonable ways to structure the renderers. Both are acceptable. Pick one.

**Approach A — Inheritance.** An abstract `Renderer` base class implements the shared skeleton
(template method: header, rows, footer) and each format is a subclass overriding the hooks.
Formats are discovered from the class hierarchy.

**Approach B — Composition.** Each format is a plain function (or a small strategy object that
does not subclass anything) registered in a format registry; shared behaviour lives in helper
functions that renderers call or that wrap them. No class hierarchy.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
