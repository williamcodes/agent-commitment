"""Report rendering (Approach B: composition / format registry).

Each format is a plain function ``(report) -> list[str]`` that returns the
output lines. Functions are registered in ``_FORMATS`` via the ``register``
decorator; there is no class hierarchy. Shared behaviour lives in small
helper functions (``title_of``, ``columns_of``, ``rows_of``) that the
format functions call, or in ``render`` itself, which wraps every format
(e.g. ``max_rows`` truncation and the ``footer`` line happen there, so
format functions never see them and formats added later get them for free).

A format can opt out of wrapper behaviour that would corrupt its output
(``json`` must stay valid JSON, so it is registered with ``footer=False``);
that flag lives in the registry entry, not in a class.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from html import escape

Report = dict
FormatFn = Callable[[Report], list[str]]


@dataclass(frozen=True)
class Format:
    """Registry entry: the format function plus its capability flags."""

    fn: FormatFn
    footer: bool = True  # may ``render`` append the "<n> rows" footer line?


_FORMATS: dict[str, Format] = {}


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that is not registered."""


def register(name: str, *, footer: bool = True) -> Callable[[FormatFn], FormatFn]:
    """Decorator that registers ``fn`` as the renderer for format ``name``.

    ``footer=False`` marks a format whose output must not have the
    ``"<n> rows"`` footer appended (structured formats such as ``json``).
    """

    def decorator(fn: FormatFn) -> FormatFn:
        _FORMATS[name] = Format(fn, footer=footer)
        return fn

    return decorator


def available_formats() -> list[str]:
    """Return the names of all registered formats, sorted."""
    return sorted(_FORMATS)


def render(
    report: Report, fmt: str, *, max_rows: int | None = None, footer: bool = False
) -> str:
    """Render ``report`` in format ``fmt``; raise ``UnknownFormat`` if unknown.

    If ``max_rows`` is given, only the first ``max_rows`` rows are rendered.
    Truncation is applied here, before the format function runs, so it works
    identically for every registered format.

    If ``footer`` is true, a final line ``"<n> rows"`` is appended, where
    ``n`` is the number of rows actually rendered (i.e. after ``max_rows``
    truncation). Formats registered with ``footer=False`` (``json``) ignore
    the flag so their output stays well-formed.

    Lines are joined with ``"\\n"`` and the result has no trailing newline,
    except that a trailing *blank* line (e.g. after the title of a report with
    no rows) is newline-terminated so it survives ``str.splitlines()``.
    """
    try:
        format_ = _FORMATS[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None
    report = truncate_rows(report, max_rows)
    lines = format_.fn(report)
    if footer and format_.footer:
        lines.append(footer_line(report))
    text = "\n".join(lines)
    if lines and lines[-1] == "":
        text += "\n"
    return text


def render_many(
    reports: Iterable[Report],
    fmt: str,
    *,
    max_rows: int | None = None,
    footer: bool = False,
) -> list[str]:
    """Render each report in ``reports`` with format ``fmt``.

    ``max_rows`` and ``footer`` are applied to each report individually, as
    in ``render``.
    The format is looked up once, so an unknown ``fmt`` raises
    ``UnknownFormat`` before any report is rendered (even for an empty list).
    """
    if fmt not in _FORMATS:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        )
    return [
        render(report, fmt, max_rows=max_rows, footer=footer) for report in reports
    ]


# --- shared helpers ---------------------------------------------------------


def truncate_rows(report: Report, max_rows: int | None) -> Report:
    """Return ``report`` with at most ``max_rows`` rows.

    ``None`` means no limit and returns ``report`` unchanged. Otherwise a
    shallow copy is returned; the caller's report is never mutated.
    """
    if max_rows is None:
        return report
    if max_rows < 0:
        raise ValueError(f"max_rows must be >= 0 or None, got {max_rows!r}")
    return {**report, "rows": list(report["rows"])[:max_rows]}


def footer_line(report: Report) -> str:
    """The ``"<n> rows"`` footer for ``report`` (``n`` = its row count)."""
    return f"{len(report['rows'])} rows"


def title_of(report: Report) -> str:
    return str(report["title"])


def columns_of(report: Report) -> list[str]:
    return [str(c) for c in report["columns"]]


def rows_of(report: Report) -> list[list[str]]:
    """Rows with every cell converted with ``str()``."""
    return [[str(cell) for cell in row] for row in report["rows"]]


# --- formats ----------------------------------------------------------------


@register("text")
def render_text(report: Report) -> list[str]:
    lines = [title_of(report), ""]
    lines.extend("  ".join(row) for row in rows_of(report))
    return lines


@register("markdown")
def render_markdown(report: Report) -> list[str]:
    def pipe_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    columns = columns_of(report)
    lines = [f"# {title_of(report)}", "", pipe_row(columns)]
    lines.append("|" + "---|" * len(columns))
    lines.extend(pipe_row(row) for row in rows_of(report))
    return lines


@register("csv")
def render_csv(report: Report) -> list[str]:
    lines = [",".join(columns_of(report))]
    lines.extend(",".join(row) for row in rows_of(report))
    return lines


@register("html")
def render_html(report: Report) -> list[str]:
    def tag_row(tag: str, cells: list[str]) -> str:
        return "<tr>" + "".join(f"<{tag}>{escape(c)}</{tag}>" for c in cells) + "</tr>"

    lines = [f"<h1>{escape(title_of(report))}</h1>", "<table>"]
    lines.append(tag_row("th", columns_of(report)))
    lines.extend(tag_row("td", row) for row in rows_of(report))
    lines.append("</table>")
    return lines


@register("json", footer=False)
def render_json(report: Report) -> list[str]:
    """The report dict serialised with ``json.dumps`` (cells keep their types).

    Registered with ``footer=False``: appending a ``"<n> rows"`` line would
    make the output invalid JSON, so ``render`` never does.
    """
    return [json.dumps(report)]
