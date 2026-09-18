"""Report rendering (Approach B: composition + format registry).

Each format is a plain function ``(report) -> str`` registered in ``_FORMATS``
via the ``@format_renderer`` decorator. Shared behaviour lives in small helper
functions that the renderers call. There is no class hierarchy.
"""

from __future__ import annotations

import csv
import html
import io
import json
from typing import Callable, Iterable

__all__ = [
    "render",
    "render_many",
    "available_formats",
    "UnknownFormat",
    "format_renderer",
]

Renderer = Callable[[dict], str]


class UnknownFormat(Exception):
    """Raised when a renderer is requested for a format that is not registered."""


_FORMATS: dict[str, Renderer] = {}


def format_renderer(name: str) -> Callable[[Renderer], Renderer]:
    """Register the decorated function as the renderer for format ``name``."""

    def decorator(func: Renderer) -> Renderer:
        _FORMATS[name] = func
        return func

    return decorator


# --- shared helpers ---------------------------------------------------------


def _cells(row: list) -> list[str]:
    return [str(cell) for cell in row]


def _columns(report: dict) -> list[str]:
    return _cells(report.get("columns", []))


def _rows(report: dict) -> list[list[str]]:
    return [_cells(row) for row in report.get("rows", [])]


def _title(report: dict) -> str:
    return str(report.get("title", ""))


def _join_lines(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def _truncate(report: dict, max_rows: int | None) -> dict:
    """Return ``report`` with at most ``max_rows`` rows (unchanged if None)."""
    if max_rows is None:
        return report
    if max_rows < 0:
        raise ValueError(f"max_rows must be >= 0, got {max_rows}")
    return {**report, "rows": list(report.get("rows", []))[:max_rows]}


# --- renderers --------------------------------------------------------------


@format_renderer("text")
def _render_text(report: dict) -> str:
    # Title line, blank line, then rows. The blank separator line is emitted
    # even when there are no rows.
    body = _join_lines("  ".join(row) for row in _rows(report))
    return f"{_title(report)}\n\n{body}"


def _pipe_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


@format_renderer("markdown")
def _render_markdown(report: dict) -> str:
    columns = _columns(report)
    lines = ["# " + _title(report), ""]
    lines.append(_pipe_row(columns))
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    lines.extend(_pipe_row(row) for row in _rows(report))
    return _join_lines(lines)


@format_renderer("csv")
def _render_csv(report: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_columns(report))
    writer.writerows(_rows(report))
    return buf.getvalue().rstrip("\n")


def _html_row(cells: list[str], tag: str) -> str:
    return "<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>"


@format_renderer("html")
def _render_html(report: dict) -> str:
    lines = [f"<h1>{html.escape(_title(report))}</h1>", "<table>"]
    lines.append(_html_row(_columns(report), "th"))
    lines.extend(_html_row(row, "td") for row in _rows(report))
    lines.append("</table>")
    return _join_lines(lines)


@format_renderer("json")
def _render_json(report: dict) -> str:
    return json.dumps(report)


# --- public interface -------------------------------------------------------


def available_formats() -> list[str]:
    """Return the registered format names, sorted."""
    return sorted(_FORMATS)


def _lookup(fmt: str) -> Renderer:
    try:
        return _FORMATS[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None


def render(report: dict, fmt: str, *, max_rows: int | None = None) -> str:
    """Render ``report`` in format ``fmt``; raise ``UnknownFormat`` if unknown.

    ``max_rows`` keeps only the first N rows. Truncation happens here, before
    dispatch, so it applies uniformly to every registered format.
    """
    return _lookup(fmt)(_truncate(report, max_rows))


def render_many(
    reports: Iterable[dict], fmt: str, *, max_rows: int | None = None
) -> list[str]:
    """Render each report in ``fmt``; the format is resolved once up front."""
    renderer = _lookup(fmt)
    return [renderer(_truncate(report, max_rows)) for report in reports]
