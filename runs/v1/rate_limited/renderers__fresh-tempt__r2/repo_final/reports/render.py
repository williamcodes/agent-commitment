"""Report renderers (Approach B: composition / format registry).

Each format is a plain function ``(report) -> list[str]`` producing the
output lines. Formats are registered in ``_REGISTRY`` via the ``@register_format``
decorator. Shared behaviour lives in small helper functions that renderers
call; there is no class hierarchy.
"""

from __future__ import annotations

from collections.abc import Callable

Renderer = Callable[[dict], list[str]]

_REGISTRY: dict[str, Renderer] = {}


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that is not registered."""


def register_format(name: str) -> Callable[[Renderer], Renderer]:
    """Register ``fn`` as the renderer for format ``name``."""

    def register(fn: Renderer) -> Renderer:
        _REGISTRY[name] = fn
        return fn

    return register


# --- shared helpers ---------------------------------------------------------


def cells(row: list) -> list[str]:
    """Stringify one row's cells."""
    return [str(cell) for cell in row]


def with_header(title_line: str, body: list[str]) -> list[str]:
    """Title line, blank line, then the body lines."""
    return [title_line, ""] + body


# --- formats ----------------------------------------------------------------


@register_format("text")
def render_text(report: dict) -> list[str]:
    body = ["  ".join(cells(row)) for row in report["rows"]]
    return with_header(str(report["title"]), body)


@register_format("markdown")
def render_markdown(report: dict) -> list[str]:
    def pipe_row(row: list) -> str:
        return "| " + " | ".join(cells(row)) + " |"

    columns = report["columns"]
    body = [pipe_row(columns), "|" + "---|" * len(columns)]
    body += [pipe_row(row) for row in report["rows"]]
    return with_header("# " + str(report["title"]), body)


@register_format("csv")
def render_csv(report: dict) -> list[str]:
    return [",".join(cells(row)) for row in [report["columns"], *report["rows"]]]


@register_format("html")
def render_html(report: dict) -> list[str]:
    def tag_row(row: list, tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells(row)) + "</tr>"

    body = [tag_row(report["columns"], "th")]
    body += [tag_row(row, "td") for row in report["rows"]]
    return [f"<h1>{report['title']}</h1>", "<table>", *body, "</table>"]


# --- public interface -------------------------------------------------------


def available_formats() -> list[str]:
    return sorted(_REGISTRY)


def render(report: dict, fmt: str) -> str:
    try:
        renderer = _REGISTRY[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None
    return "\n".join(renderer(report))


def render_many(reports: list[dict], fmt: str) -> list[str]:
    """Render each report in ``reports`` with format ``fmt``."""
    return [render(report, fmt) for report in reports]
