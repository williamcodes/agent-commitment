"""Report rendering.

Approach B (composition): each format is a plain function registered in
``_FORMATS`` via the ``@format_renderer`` decorator. Shared behaviour lives in
small helper functions that the renderers call. There is no class hierarchy.
"""

import json
from collections.abc import Callable

Renderer = Callable[[dict], str]

_FORMATS: dict[str, Renderer] = {}
# Formats whose output must not have a footer line appended (e.g. structured
# formats where a trailing line would corrupt the output).
_NO_FOOTER: set[str] = set()


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that is not registered."""


def format_renderer(
    name: str, *, supports_footer: bool = True
) -> Callable[[Renderer], Renderer]:
    """Register ``func`` as the renderer for format ``name``.

    ``supports_footer=False`` marks a format whose output must be left
    untouched by ``render(..., footer=True)``.
    """

    def decorator(func: Renderer) -> Renderer:
        _FORMATS[name] = func
        if not supports_footer:
            _NO_FOOTER.add(name)
        return func

    return decorator


# --- shared helpers ---------------------------------------------------------


def _cells(row: list) -> list[str]:
    return [str(cell) for cell in row]


def _rows(report: dict) -> list[list[str]]:
    return [_cells(row) for row in report.get("rows", [])]


def _join_lines(lines: list[str]) -> str:
    """Join lines with newlines (no trailing newline)."""
    return "\n".join(lines)


def _truncate(report: dict, max_rows: int | None) -> dict:
    """Return ``report`` with at most ``max_rows`` rows (``None`` keeps all).

    Returns a shallow copy; the caller's report is never mutated.
    """
    if max_rows is None:
        return report
    if max_rows < 0:
        raise ValueError(f"max_rows must be >= 0 or None, got {max_rows!r}")
    return {**report, "rows": list(report.get("rows", []))[:max_rows]}


def _footer(report: dict) -> str:
    """The footer line: the number of rows in ``report``."""
    return f"{len(report.get('rows', []))} rows"


# --- format renderers -------------------------------------------------------


@format_renderer("text")
def render_text(report: dict) -> str:
    # Title, a blank line, then the rows. The header block always ends with
    # the blank separator line, even when there are no rows; the row block
    # itself has no trailing newline.
    header = f"{report['title']}\n\n"
    body = _join_lines(["  ".join(row) for row in _rows(report)])
    return header + body


@format_renderer("markdown")
def render_markdown(report: dict) -> str:
    def pipe_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    columns = _cells(report["columns"])
    lines = [f"# {report['title']}", ""]
    lines.append(pipe_row(columns))
    lines.append("|" + "---|" * len(columns))
    lines.extend(pipe_row(row) for row in _rows(report))
    return _join_lines(lines)


@format_renderer("csv")
def render_csv(report: dict) -> str:
    lines = [",".join(_cells(report["columns"]))]
    lines.extend(",".join(row) for row in _rows(report))
    return _join_lines(lines)


@format_renderer("html")
def render_html(report: dict) -> str:
    def tag_row(cells: list[str], tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"

    lines = [f"<h1>{report['title']}</h1>", "<table>"]
    lines.append(tag_row(_cells(report["columns"]), "th"))
    lines.extend(tag_row(row, "td") for row in _rows(report))
    lines.append("</table>")
    return _join_lines(lines)


@format_renderer("json", supports_footer=False)
def render_json(report: dict) -> str:
    # The report dict itself, serialized; cells keep their native types.
    return json.dumps(report)


# --- public interface -------------------------------------------------------


def available_formats() -> list[str]:
    return sorted(_FORMATS)


def render(
    report: dict, fmt: str, *, max_rows: int | None = None, footer: bool = False
) -> str:
    """Render ``report`` in format ``fmt``.

    ``max_rows`` keeps only the first ``max_rows`` rows. ``footer`` appends a
    final ``"<n> rows"`` line, where ``n`` is the number of rows actually
    rendered (i.e. after truncation). Both are handled here, around dispatch,
    so they apply uniformly without each renderer having to know about them.
    Formats registered with ``supports_footer=False`` (``json``, which must
    stay valid JSON) are returned unchanged.
    """
    try:
        renderer = _FORMATS[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None
    report = _truncate(report, max_rows)
    out = renderer(report)
    if footer and fmt not in _NO_FOOTER:
        out = _join_lines([out, _footer(report)])
    return out


def render_many(
    reports: list[dict],
    fmt: str,
    *,
    max_rows: int | None = None,
    footer: bool = False,
) -> list[str]:
    """Render each report in ``reports`` with format ``fmt``."""
    return [
        render(report, fmt, max_rows=max_rows, footer=footer) for report in reports
    ]
