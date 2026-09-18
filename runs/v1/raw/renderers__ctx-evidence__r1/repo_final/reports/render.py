"""Report rendering built on an abstract ``BaseRenderer`` (Approach A).

``BaseRenderer.render`` is a template method: it applies shared behaviour
(``max_rows`` truncation) and then assembles the output from three hooks,
``render_header``, ``render_rows`` and ``render_footer``. Each hook returns
a list of lines, or ``None`` to omit that section. Sections are separated
by a newline, so an empty list still occupies one (empty) line. With
``footer=True`` a final ``"<n> rows"`` line is appended after the format's
own footer, unless the class opts out via ``row_count_footer = False``.

Formats are discovered by walking ``BaseRenderer.__subclasses__()``; a
concrete subclass advertises its name through the ``format`` attribute.
"""

from __future__ import annotations

import csv
import html
import inspect
import io
import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from typing import ClassVar

Lines = list[str] | None


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format no renderer provides."""


class BaseRenderer(ABC):
    """Template-method base class for every report format.

    Subclasses set ``format`` and override the hooks. They receive the
    report with its original cell types (so a format such as JSON can keep
    numbers as numbers) and can use ``cells`` to stringify a row.
    """

    format: ClassVar[str | None] = None
    # Whether the optional "<n> rows" line may be appended. Formats whose
    # output must stay a single well-formed document (e.g. JSON) set False.
    row_count_footer: ClassVar[bool] = True

    def render(
        self, report: dict, *, max_rows: int | None = None, footer: bool = False
    ) -> str:
        report = self.prepare(report, max_rows)
        sections = [
            self.render_header(report),
            self.render_rows(report),
            self.render_footer(report),
        ]
        if footer and self.row_count_footer:
            sections.append(self.render_row_count(report))
        return "\n".join("\n".join(lines) for lines in sections if lines is not None)

    # --- shared behaviour ------------------------------------------------

    def prepare(self, report: dict, max_rows: int | None) -> dict:
        """Return a shallow copy of ``report`` with rows truncated."""
        if max_rows is not None and max_rows < 0:
            raise ValueError(f"max_rows must be >= 0 or None, got {max_rows}")
        rows = list(report.get("rows", []))
        if max_rows is not None:
            rows = rows[:max_rows]
        return {**report, "rows": rows}

    @staticmethod
    def cells(values: Iterable[object]) -> list[str]:
        return [str(v) for v in values]

    def render_row_count(self, report: dict) -> Lines:
        """The ``footer=True`` line; counts the rows actually rendered."""
        return [f"{len(report['rows'])} rows"]

    # --- hooks -----------------------------------------------------------

    def render_header(self, report: dict) -> Lines:
        return None

    @abstractmethod
    def render_rows(self, report: dict) -> Lines: ...

    def render_footer(self, report: dict) -> Lines:
        return None


# --- discovery and public functions -----------------------------------------


def _concrete_renderers() -> Iterator[type[BaseRenderer]]:
    stack = list(BaseRenderer.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.format is not None and not inspect.isabstract(cls):
            yield cls


def _renderer_for(fmt: str) -> BaseRenderer:
    for cls in _concrete_renderers():
        if cls.format == fmt:
            return cls()
    raise UnknownFormat(
        f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
    )


def available_formats() -> list[str]:
    return sorted({cls.format for cls in _concrete_renderers()})


def render(
    report: dict, fmt: str, *, max_rows: int | None = None, footer: bool = False
) -> str:
    return _renderer_for(fmt).render(report, max_rows=max_rows, footer=footer)


def render_many(
    reports: Iterable[dict],
    fmt: str,
    *,
    max_rows: int | None = None,
    footer: bool = False,
) -> list[str]:
    """Render each report in ``reports`` with format ``fmt``, in order."""
    renderer = _renderer_for(fmt)
    return [
        renderer.render(report, max_rows=max_rows, footer=footer) for report in reports
    ]


# --- formats -----------------------------------------------------------------


class TextRenderer(BaseRenderer):
    format = "text"

    def render_header(self, report: dict) -> Lines:
        return [str(report["title"]), ""]

    def render_rows(self, report: dict) -> Lines:
        return ["  ".join(self.cells(row)) for row in report["rows"]]


class MarkdownRenderer(BaseRenderer):
    format = "markdown"

    @staticmethod
    def _pipe_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    def render_header(self, report: dict) -> Lines:
        columns = self.cells(report["columns"])
        return [
            f"# {report['title']}",
            "",
            self._pipe_row(columns),
            "|" + "---|" * len(columns),
        ]

    def render_rows(self, report: dict) -> Lines:
        return [self._pipe_row(self.cells(row)) for row in report["rows"]]


class CsvRenderer(BaseRenderer):
    format = "csv"

    @staticmethod
    def _csv_lines(rows: Iterable[Iterable[object]]) -> list[str]:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        return buf.getvalue().splitlines()

    def render_header(self, report: dict) -> Lines:
        return self._csv_lines([report["columns"]])

    def render_rows(self, report: dict) -> Lines:
        return self._csv_lines(report["rows"])


class HtmlRenderer(BaseRenderer):
    format = "html"

    @staticmethod
    def _row(cells: list[str], tag: str) -> str:
        inner = "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells)
        return f"<tr>{inner}</tr>"

    def render_header(self, report: dict) -> Lines:
        return [
            f"<h1>{html.escape(str(report['title']))}</h1>",
            "<table>",
            self._row(self.cells(report["columns"]), "th"),
        ]

    def render_rows(self, report: dict) -> Lines:
        return [self._row(self.cells(row), "td") for row in report["rows"]]

    def render_footer(self, report: dict) -> Lines:
        return ["</table>"]


class JsonRenderer(BaseRenderer):
    format = "json"
    row_count_footer = False  # a trailing "<n> rows" line would break the JSON

    # JSON has no separable header or footer: the whole (already truncated)
    # report is one document, emitted from the rows hook with original types.
    def render_rows(self, report: dict) -> Lines:
        return [json.dumps(report)]
