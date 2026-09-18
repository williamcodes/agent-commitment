"""Report rendering (Approach B: composition via a format registry).

Each output format is a plain function ``(report) -> str`` registered under a
name.  Shared behaviour (cell stringification, line assembly) lives in small
helper functions that the format functions call.  There is no class hierarchy.
"""

from __future__ import annotations

from collections.abc import Callable

__all__ = ["render", "available_formats", "UnknownFormat", "register"]

Renderer = Callable[[dict], str]

_FORMATS: dict[str, Renderer] = {}


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that is not registered."""


def register(name: str) -> Callable[[Renderer], Renderer]:
    """Decorator that registers a renderer function under ``name``."""

    def decorator(func: Renderer) -> Renderer:
        _FORMATS[name] = func
        return func

    return decorator


def render(report: dict, fmt: str) -> str:
    """Render ``report`` in the named format, or raise ``UnknownFormat``."""
    try:
        renderer = _FORMATS[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None
    return renderer(report)


def available_formats() -> list[str]:
    """Names of all registered formats, sorted."""
    return sorted(_FORMATS)


# --- shared helpers ---------------------------------------------------------


def _cells(row: list) -> list[str]:
    """Convert every cell of a row to its ``str()`` form."""
    return [str(cell) for cell in row]


def _assemble(title_line: str, body: list[str]) -> str:
    """Join a title line, a blank separator line and the body lines.

    The result always ends with a single newline, like a POSIX text file.
    """
    return "\n".join([title_line, "", *body]) + "\n"


# --- formats ----------------------------------------------------------------


@register("text")
def _render_text(report: dict) -> str:
    rows = ["  ".join(_cells(row)) for row in report["rows"]]
    return _assemble(report["title"], rows)


@register("markdown")
def _render_markdown(report: dict) -> str:
    def pipe_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    columns = _cells(report["columns"])
    lines = [pipe_row(columns), "|" + "---|" * len(columns)]
    lines += [pipe_row(_cells(row)) for row in report["rows"]]
    return _assemble(f"# {report['title']}", lines)
