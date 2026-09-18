"""Report rendering (Approach A: an abstract ``BaseRenderer`` class hierarchy).

Every format is a concrete subclass of :class:`BaseRenderer` that declares a
``name`` and overrides the ``render_header`` / ``render_rows`` /
``render_footer`` hooks. The base class owns the template method
:meth:`BaseRenderer.render`, which applies shared behaviour (currently
``max_rows`` truncation) before assembling the hook output into the final
string. Formats are discovered by walking ``BaseRenderer.__subclasses__()``;
there is no registry to update when adding a format.

Shared *optional* behaviour is likewise expressed on the base class: the
``footer=True`` row-count line is appended by the template method for every
subclass whose ``supports_footer`` attribute is true (``JsonRenderer`` opts
out so that its output stays valid JSON).

To add a format::

    class YamlRenderer(BaseRenderer):
        name = "yaml"

        def render_rows(self, report):
            ...
"""

from __future__ import annotations

import inspect
import json
from abc import ABC, abstractmethod

__all__ = ["render", "render_many", "available_formats", "UnknownFormat", "BaseRenderer"]


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format no renderer provides."""


# --- shared helpers ---------------------------------------------------------


def _cells(row: list) -> list[str]:
    return [str(cell) for cell in row]


def _rows(report: dict) -> list[list[str]]:
    return [_cells(row) for row in report.get("rows", [])]


def _columns(report: dict) -> list[str]:
    return _cells(report.get("columns", []))


# --- base class -------------------------------------------------------------


class BaseRenderer(ABC):
    """Template for a report format.

    Subclasses set ``name`` (the string accepted by :func:`render`) and
    override the hooks. Each hook receives the report *after* shared
    processing such as ``max_rows`` truncation and returns a list of output
    lines; :meth:`render` joins the three lists with ``"\\n"`` and no trailing
    newline. ``render_header`` and ``render_footer`` default to no lines.

    Subclasses without a ``name`` (or with ``name = None``) are treated as
    abstract intermediates and are not exposed as formats.

    ``supports_footer`` controls whether :meth:`render` may append the
    ``"<n> rows"`` summary line when called with ``footer=True``. Formats
    whose output cannot tolerate a trailing free-text line (JSON) set it to
    ``False``; the ``footer`` flag is then silently ignored for them.
    """

    name: str | None = None
    supports_footer: bool = True

    # -- template method (shared behaviour lives here) ----------------------

    def render(
        self, report: dict, max_rows: int | None = None, footer: bool = False
    ) -> str:
        """Render ``report``; keep only the first ``max_rows`` rows if given.

        With ``footer=True`` a final ``"<n> rows"`` line is appended, where
        ``n`` is the number of rows actually rendered (i.e. after ``max_rows``
        truncation). It comes after ``render_footer`` output, so it is always
        the last line. Ignored when ``supports_footer`` is false.
        """
        report = self._truncate(report, max_rows)
        lines = [
            *self.render_header(report),
            *self.render_rows(report),
            *self.render_footer(report),
        ]
        if footer and self.supports_footer:
            lines.append(self._row_count_line(report))
        return "\n".join(lines)

    @staticmethod
    def _row_count_line(report: dict) -> str:
        """The ``footer=True`` summary line for an (already truncated) report."""
        return f"{len(report.get('rows', []))} rows"

    @staticmethod
    def _truncate(report: dict, max_rows: int | None) -> dict:
        """Return ``report`` with at most ``max_rows`` rows (never mutates it)."""
        if max_rows is None:
            return report
        if max_rows < 0:
            raise ValueError(f"max_rows must be >= 0 or None, got {max_rows!r}")
        return {**report, "rows": list(report.get("rows", []))[:max_rows]}

    # -- hooks ---------------------------------------------------------------

    def render_header(self, report: dict) -> list[str]:
        """Lines emitted before the rows (default: none)."""
        return []

    @abstractmethod
    def render_rows(self, report: dict) -> list[str]:
        """Lines emitted for the rows."""

    def render_footer(self, report: dict) -> list[str]:
        """Lines emitted after the rows (default: none)."""
        return []


# --- formats ----------------------------------------------------------------


class TextRenderer(BaseRenderer):
    """Title line, a blank line, then one line per row (cells joined by two spaces)."""

    name = "text"

    def render_header(self, report: dict) -> list[str]:
        return [str(report["title"]), ""]

    def render_rows(self, report: dict) -> list[str]:
        lines = ["  ".join(row) for row in _rows(report)]
        # A report with no rows still ends with the blank separator line
        # ("T\n\n"), so the rows section must occupy one (empty) line.
        return lines or [""]


class MarkdownRenderer(BaseRenderer):
    """``# title``, a blank line, then a pipe table with a header row."""

    name = "markdown"

    @staticmethod
    def _pipe_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    def render_header(self, report: dict) -> list[str]:
        columns = _columns(report)
        return [
            "# " + str(report["title"]),
            "",
            self._pipe_row(columns),
            "|" + "---|" * len(columns),
        ]

    def render_rows(self, report: dict) -> list[str]:
        return [self._pipe_row(row) for row in _rows(report)]


class CsvRenderer(BaseRenderer):
    """A column header line, then one comma-joined line per row."""

    name = "csv"

    def render_header(self, report: dict) -> list[str]:
        return [",".join(_columns(report))]

    def render_rows(self, report: dict) -> list[str]:
        return [",".join(row) for row in _rows(report)]


class HtmlRenderer(BaseRenderer):
    """An ``<h1>`` title followed by a ``<table>`` with a ``<th>`` header row."""

    name = "html"

    @staticmethod
    def _tag_row(cells: list[str], tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>"

    def render_header(self, report: dict) -> list[str]:
        return [f"<h1>{report['title']}</h1>", "<table>", self._tag_row(_columns(report), "th")]

    def render_rows(self, report: dict) -> list[str]:
        return [self._tag_row(row, "td") for row in _rows(report)]

    def render_footer(self, report: dict) -> list[str]:
        return ["</table>"]


class JsonRenderer(BaseRenderer):
    """The report dict serialised with ``json.dumps``.

    JSON has no separable header or footer, so the whole (already truncated)
    document is emitted as the single line of the rows section. A trailing
    ``"<n> rows"`` line would make the output invalid JSON, so the format
    opts out of the ``footer`` flag.
    """

    name = "json"
    supports_footer = False

    def render_rows(self, report: dict) -> list[str]:
        return [json.dumps(report)]


# --- discovery --------------------------------------------------------------


def _concrete_renderers(base: type[BaseRenderer] = BaseRenderer) -> list[type[BaseRenderer]]:
    """All concrete, named subclasses of ``base``, at any depth."""
    found: list[type[BaseRenderer]] = []
    for cls in base.__subclasses__():
        if cls.name is not None and not inspect.isabstract(cls):
            found.append(cls)
        found.extend(_concrete_renderers(cls))
    return found


def _renderer_classes() -> dict[str, type[BaseRenderer]]:
    """Map format name -> renderer class; fail loudly if two classes share a name."""
    classes: dict[str, type[BaseRenderer]] = {}
    for cls in _concrete_renderers():
        if cls.name in classes:
            raise TypeError(
                f"format {cls.name!r} is defined by both "
                f"{classes[cls.name].__qualname__} and {cls.__qualname__}"
            )
        classes[cls.name] = cls
    return classes


# --- public API -------------------------------------------------------------


def available_formats() -> list[str]:
    """Return the names of all discovered formats, sorted."""
    return sorted(_renderer_classes())


def render(
    report: dict, fmt: str, max_rows: int | None = None, footer: bool = False
) -> str:
    """Render ``report`` in format ``fmt``; raise ``UnknownFormat`` if unknown.

    ``max_rows`` keeps only the first that many rows (``None`` keeps all).
    It is applied by ``BaseRenderer.render`` and so works for every format.

    ``footer=True`` appends a final line ``"<n> rows"`` where ``n`` is the
    number of rows actually rendered (after ``max_rows`` truncation). It
    applies to every format except ``json``, whose output must stay valid
    JSON; there the flag is ignored.

    Output lines are joined with ``"\\n"``; there is no newline after the
    last line. (For a report with no rows, the text format ends with its
    blank separator line, e.g. ``"T\\n\\n"``.)
    """
    try:
        renderer_cls = _renderer_classes()[fmt]
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None
    return renderer_cls().render(report, max_rows=max_rows, footer=footer)


def render_many(
    reports: list[dict], fmt: str, max_rows: int | None = None, footer: bool = False
) -> list[str]:
    """Render each report in ``reports`` with format ``fmt``, in order."""
    return [render(report, fmt, max_rows=max_rows, footer=footer) for report in reports]
