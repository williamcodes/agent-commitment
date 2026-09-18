"""Report rendering (Approach B: composition + format registry).

Each format is a plain function ``(report) -> str`` registered in
``_FORMATS`` via the ``@format_renderer`` decorator. Shared behaviour lives in
small helper functions that renderers call. There is no class hierarchy.
"""

from __future__ import annotations

import csv
import html
import io
from typing import Callable, Iterable

Cell = str | int | float
Renderer = Callable[[dict], str]


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that is not registered."""


_FORMATS: dict[str, Renderer] = {}


def format_renderer(name: str) -> Callable[[Renderer], Renderer]:
    """Decorator registering a renderer function under ``name``."""

    def register(fn: Renderer) -> Renderer:
        _FORMATS[name] = fn
        return fn

    return register


# --- shared helpers -------------------------------------------------------

def join_lines(lines: Iterable[str]) -> str:
    """Join output lines with newlines (no trailing newline)."""
    return "\n".join(lines)


def cells(row: list[Cell]) -> list[str]:
    """Convert a row's cells to strings."""
    return [str(c) for c in row]


def join_row(row: list[Cell], sep: str) -> str:
    """Render one row with its cells joined by ``sep``."""
    return sep.join(cells(row))


def pipe_row(row: list[Cell]) -> str:
    """Render one row as a Markdown pipe-table row."""
    return "| " + join_row(row, " | ") + " |"


def csv_row(row: list[Cell]) -> str:
    """Render one row as a CSV line (quoting cells that need it)."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(cells(row))
    return buf.getvalue()


def html_row(row: list[Cell], tag: str) -> str:
    """Render one row as an HTML ``<tr>`` of ``tag`` cells, escaping text."""
    inner = "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells(row))
    return f"<tr>{inner}</tr>"


# --- renderers ------------------------------------------------------------

@format_renderer("text")
def render_text(report: dict) -> str:
    # Header is the title line plus a blank line; the blank line stays
    # newline-terminated even when there are no rows to follow it.
    header = f"{report['title']}\n\n"
    return header + join_lines(join_row(row, "  ") for row in report["rows"])


@format_renderer("markdown")
def render_markdown(report: dict) -> str:
    columns = report["columns"]
    lines = [f"# {report['title']}", ""]
    lines.append(pipe_row(columns))
    lines.append("|" + "---|" * len(columns))
    lines.extend(pipe_row(row) for row in report["rows"])
    return join_lines(lines)


@format_renderer("csv")
def render_csv(report: dict) -> str:
    lines = [csv_row(report["columns"])]
    lines.extend(csv_row(row) for row in report["rows"])
    return join_lines(lines)


@format_renderer("html")
def render_html(report: dict) -> str:
    lines = [f"<h1>{html.escape(str(report['title']))}</h1>", "<table>"]
    lines.append(html_row(report["columns"], "th"))
    lines.extend(html_row(row, "td") for row in report["rows"])
    lines.append("</table>")
    return join_lines(lines)


# --- public interface -----------------------------------------------------

def available_formats() -> list[str]:
    """Return the registered format names, sorted."""
    return sorted(_FORMATS)


def render(report: dict, fmt: str) -> str:
    """Render ``report`` in format ``fmt``; raise ``UnknownFormat`` if unknown."""
    try:
        renderer = _FORMATS[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None
    return renderer(report)


def render_many(reports: Iterable[dict], fmt: str) -> list[str]:
    """Render each report in ``fmt``; raise ``UnknownFormat`` before any work."""
    if fmt not in _FORMATS:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        )
    return [render(report, fmt) for report in reports]
