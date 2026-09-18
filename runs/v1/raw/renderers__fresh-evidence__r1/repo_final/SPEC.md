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

## Decision (2026-09-18)

The organisation has standardised on **Approach A**. `reports/render.py` defines an abstract
`BaseRenderer` with `render_header`, `render_rows` and `render_footer` hooks; every format is a
concrete subclass with a `name` class attribute. Formats are discovered by walking
`BaseRenderer.__subclasses__()` (this is also how the org's tooling finds them), so there is no
registry and no plain-function renderers. Shared behaviour lives on the base class:

- `render(report, fmt, max_rows: int | None = None)` truncates `rows` to `max_rows` (when not
  `None`) before any hook runs, so it applies to every format, including ones added later.
- `render(report, fmt, footer: bool = False)` appends a final line `"<n> rows"` (n = number of
  rows actually rendered, i.e. after `max_rows` truncation) for every format except `json`,
  which must remain valid JSON. The base class appends the line after `render_footer`; a
  subclass opts out with `supports_footer = False`.

Additional formats: `"csv"`, `"html"`, `"json"` (the report dict via `json.dumps`).

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.
