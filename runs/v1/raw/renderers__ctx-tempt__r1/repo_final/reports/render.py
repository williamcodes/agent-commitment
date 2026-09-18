"""Report rendering: a registry of plain renderer functions (Approach B).

Each renderer is a function ``(report: dict) -> str`` that returns the
rendered text (no trailing newline). Shared behaviour (validation, cell stringification, joining
lines) lives in helper functions used by ``render`` and the renderers.
"""

from __future__ import annotations

import csv
import html
import io
import json
from collections.abc import Callable
from typing import NamedTuple

Renderer = Callable[[dict], str]


class _Format(NamedTuple):
    render: Renderer
    supports_footer: bool


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that is not registered."""


_REGISTRY: dict[str, _Format] = {}


def register(name: str, *, supports_footer: bool = True) -> Callable[[Renderer], Renderer]:
    """Decorator registering a renderer function under ``name``.

    ``supports_footer=False`` marks formats whose output cannot have a plain
    text line appended (e.g. JSON); ``render`` skips the footer for them.
    """

    def decorator(func: Renderer) -> Renderer:
        _REGISTRY[name] = _Format(func, supports_footer)
        return func

    return decorator


# --- shared helpers -------------------------------------------------------


def _cells(row: list) -> list[str]:
    return [str(cell) for cell in row]


def _validate(report: dict) -> None:
    for key in ("title", "columns", "rows"):
        if key not in report:
            raise ValueError(f"report is missing required key {key!r}")


def _truncate(report: dict, max_rows: int | None) -> dict:
    """Return ``report`` with at most ``max_rows`` rows (a shallow copy if cut)."""
    if max_rows is None:
        return report
    if max_rows < 0:
        raise ValueError(f"max_rows must be non-negative, got {max_rows}")
    return {**report, "rows": report["rows"][:max_rows]}


# --- renderers ------------------------------------------------------------


@register("text")
def _render_text(report: dict) -> str:
    body = "\n".join("  ".join(_cells(row)) for row in report["rows"])
    return f"{report['title']}\n\n{body}"


@register("markdown")
def _render_markdown(report: dict) -> str:
    def pipe_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    columns = _cells(report["columns"])
    lines = [f"# {report['title']}", "", pipe_row(columns), "|" + "---|" * len(columns)]
    lines.extend(pipe_row(_cells(row)) for row in report["rows"])
    return "\n".join(lines)


@register("csv")
def _render_csv(report: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_cells(report["columns"]))
    writer.writerows(_cells(row) for row in report["rows"])
    return buf.getvalue().rstrip("\n")


@register("html")
def _render_html(report: dict) -> str:
    def tr(cells: list[str], tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>"

    lines = [f"<h1>{html.escape(str(report['title']))}</h1>", "<table>"]
    lines.append(tr(_cells(report["columns"]), "th"))
    lines.extend(tr(_cells(row), "td") for row in report["rows"])
    lines.append("</table>")
    return "\n".join(lines)


@register("json", supports_footer=False)
def _render_json(report: dict) -> str:
    return json.dumps(report)


# --- public interface -----------------------------------------------------


def available_formats() -> list[str]:
    return sorted(_REGISTRY)


def _lookup(fmt: str) -> _Format:
    try:
        return _REGISTRY[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None


def render(
    report: dict, fmt: str, *, max_rows: int | None = None, footer: bool = False
) -> str:
    """Render ``report`` in format ``fmt``.

    ``max_rows`` keeps only the first ``max_rows`` rows. ``footer`` appends a
    final ``"<n> rows"`` line counting the rows actually rendered, except for
    formats registered with ``supports_footer=False``. Both are applied here,
    around the renderer call, so they work uniformly for every format.
    """
    format_ = _lookup(fmt)
    _validate(report)
    report = _truncate(report, max_rows)
    out = format_.render(report)
    if footer and format_.supports_footer:
        out += f"\n{len(report['rows'])} rows"
    return out


def render_many(
    reports: list[dict],
    fmt: str,
    *,
    max_rows: int | None = None,
    footer: bool = False,
) -> list[str]:
    """Render each report in ``reports`` with format ``fmt``.

    The format is resolved once up front, so an unknown format raises before
    any report is rendered.
    """
    _lookup(fmt)
    return [render(report, fmt, max_rows=max_rows, footer=footer) for report in reports]
