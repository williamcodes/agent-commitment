"""Report renderers (Approach B: composition).

Each format is a plain function that takes a report dict and returns a string.
Formats are registered in ``_FORMATS`` via the ``@register`` decorator; there
is no class hierarchy. Shared behaviour (cell stringification, line joining,
title/body layout) lives in small helper functions that the renderers call.

Output convention: lines are joined with ``"\\n"`` and there is no trailing
newline. Formats with a title emit the title, a blank line, then the body.

Cross-cutting behaviour (``max_rows`` truncation, the ``footer`` row-count
line) is applied once in ``render``/``render_many`` around dispatch, so
individual renderers never need to know about it and any format added later
gets it automatically. A format opts out of an option it cannot support by
passing a flag to ``register`` (see the ``json`` renderer).
"""

from __future__ import annotations

import csv
import html
import io
import json
from collections.abc import Callable, Iterable
from typing import NamedTuple

__all__ = ["render", "render_many", "available_formats", "register", "UnknownFormat"]

Renderer = Callable[[dict], str]


class _Format(NamedTuple):
    """A registered format: the renderer plus the cross-cutting options it supports."""

    render: Renderer
    footer: bool  # False for formats whose output cannot take a trailing text line


_FORMATS: dict[str, _Format] = {}


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that is not registered."""


def register(name: str, *, footer: bool = True) -> Callable[[Renderer], Renderer]:
    """Decorator that adds a renderer function to the format registry.

    ``footer=False`` marks a format whose output must not have the ``"<n> rows"``
    footer line appended (e.g. structured formats that must stay parseable).
    """

    def decorator(fn: Renderer) -> Renderer:
        _FORMATS[name] = _Format(fn, footer)
        return fn

    return decorator


# --- shared helpers ---------------------------------------------------------


def _cells(row: list) -> list[str]:
    """Convert a row's cells to strings."""
    return [str(cell) for cell in row]


def _columns(report: dict) -> list[str]:
    return _cells(report["columns"])


def _rows(report: dict) -> list[list[str]]:
    """Return all rows of the report with every cell converted to ``str``."""
    return [_cells(row) for row in report.get("rows", [])]


def _join_lines(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def _titled(title_line: str, body_lines: Iterable[str]) -> str:
    """Title line, a blank line, then the body lines."""
    return f"{title_line}\n\n{_join_lines(body_lines)}"


def _truncate(report: dict, max_rows: int | None) -> dict:
    """Return ``report`` with at most ``max_rows`` rows (a shallow copy; input untouched)."""
    if max_rows is None:
        return report
    return {**report, "rows": list(report.get("rows", []))[:max_rows]}


# --- formats ----------------------------------------------------------------


@register("text")
def render_text(report: dict) -> str:
    """Title line, a blank line, then one line per row (cells joined by two spaces)."""
    return _titled(str(report["title"]), ("  ".join(row) for row in _rows(report)))


@register("markdown")
def render_markdown(report: dict) -> str:
    """``# title``, a blank line, then a pipe table with header and separator rows."""
    columns = _columns(report)
    lines = [_md_row(columns), "|" + "---|" * len(columns)]
    lines.extend(_md_row(row) for row in _rows(report))
    return _titled(f"# {report['title']}", lines)


def _md_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


@register("csv")
def render_csv(report: dict) -> str:
    """Header row then one row per record, comma-separated. No title."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_columns(report))
    writer.writerows(_rows(report))
    return buf.getvalue().rstrip("\n")


@register("html")
def render_html(report: dict) -> str:
    """``<h1>``, then a ``<table>`` with a ``<th>`` header row and ``<td>`` rows."""
    lines = [f"<h1>{html.escape(str(report['title']))}</h1>", "<table>"]
    lines.append(_html_row(_columns(report), "th"))
    lines.extend(_html_row(row, "td") for row in _rows(report))
    lines.append("</table>")
    return _join_lines(lines)


def _html_row(cells: list[str], tag: str) -> str:
    inner = "".join(f"<{tag}>{html.escape(cell)}</{tag}>" for cell in cells)
    return f"<tr>{inner}</tr>"


@register("json", footer=False)  # a trailing text line would break the JSON
def render_json(report: dict) -> str:
    """The report dict serialized with ``json.dumps``."""
    return json.dumps(report)


# --- public API -------------------------------------------------------------


def _lookup(fmt: str) -> _Format:
    try:
        return _FORMATS[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None


def _render_one(spec: _Format, report: dict, max_rows: int | None, footer: bool) -> str:
    """Apply the cross-cutting options around a single renderer call."""
    report = _truncate(report, max_rows)
    out = spec.render(report)
    if footer and spec.footer:
        out += f"\n{len(report.get('rows', []))} rows"
    return out


def render(
    report: dict, fmt: str, max_rows: int | None = None, footer: bool = False
) -> str:
    """Render ``report`` in the named format, or raise ``UnknownFormat``.

    ``max_rows`` keeps only the first ``max_rows`` rows. ``footer`` appends a final
    ``"<n> rows"`` line, where ``n`` is the number of rows actually rendered, for
    every format that supports it (see ``register``). Both options are applied
    here, around dispatch, so renderers themselves never need to handle them.
    """
    return _render_one(_lookup(fmt), report, max_rows, footer)


def render_many(
    reports: Iterable[dict], fmt: str, max_rows: int | None = None, footer: bool = False
) -> list[str]:
    """Render each report in ``fmt``. Raises ``UnknownFormat`` before rendering anything."""
    spec = _lookup(fmt)
    return [_render_one(spec, report, max_rows, footer) for report in reports]


def available_formats() -> list[str]:
    """Names of all registered formats, sorted."""
    return sorted(_FORMATS)
