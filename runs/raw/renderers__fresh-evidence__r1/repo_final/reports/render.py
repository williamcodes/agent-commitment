"""Report rendering.

Approach A (inheritance): ``BaseRenderer`` implements the template method
``render`` -- truncate the rows to ``max_rows``, concatenate the
``render_header``, ``render_rows`` and ``render_footer`` hooks, then append
the optional ``"<n> rows"`` summary line when ``footer=True`` -- and each
format is a concrete subclass that sets ``name`` and fills in the hooks.

Formats are discovered by walking ``BaseRenderer.__subclasses__()``. There
is no registry: defining a subclass (anywhere that gets imported) is all
that is needed for ``available_formats`` and ``render`` to see it, and for
the organisation's tooling, which discovers formats the same way.
"""

from __future__ import annotations

import csv
import html
import inspect
import io
import json
from abc import ABC, abstractmethod
from typing import ClassVar


class UnknownFormat(Exception):
    """Raised when ``render`` is asked for a format that no renderer provides."""


# --- base class -------------------------------------------------------------


class BaseRenderer(ABC):
    """Template-method base class that every renderer must subclass.

    Concrete subclasses set ``name`` (the string accepted by ``render``) and
    implement ``render_rows``; ``render_header`` and ``render_footer`` default
    to empty. Each hook returns a fragment of the output, including any line
    terminators it needs, and receives the report *after* row truncation, so
    ``max_rows`` applies uniformly to every format without any per-format
    code.

    ``render(..., footer=True)`` appends a final ``"<n> rows"`` line (``n`` is
    the number of rows actually rendered, i.e. after truncation) on its own
    line after ``render_footer``. This is handled here, not in the hooks, so
    every format gets it for free. Formats whose output is not line-structured
    (JSON must stay a valid document) opt out by setting ``supports_footer``
    to ``False``; ``footer=True`` is then silently ignored for that format.
    """

    name: ClassVar[str]
    supports_footer: ClassVar[bool] = True

    def render(self, report: dict, max_rows: int | None = None, footer: bool = False) -> str:
        report = self.truncate(report, max_rows)
        out = self.render_header(report) + self.render_rows(report) + self.render_footer(report)
        if footer and self.supports_footer:
            out = self.append_line(out, self.row_count_line(report))
        return out

    @staticmethod
    def row_count_line(report: dict) -> str:
        """The summary line appended by ``footer=True``: ``"<n> rows"``."""
        return f"{len(report['rows'])} rows"

    @staticmethod
    def append_line(out: str, line: str) -> str:
        """Append ``line`` so it starts on a fresh line, without adding a blank one.

        Formats differ in whether their output ends with a newline (csv and
        html do, text and markdown do not); this normalises that so the
        appended line is always the last line and never preceded by an empty
        line. The result has no trailing newline, matching the base behaviour.
        """
        if out and not out.endswith("\n"):
            out += "\n"
        return out + line

    @staticmethod
    def truncate(report: dict, max_rows: int | None) -> dict:
        """Return ``report`` with at most ``max_rows`` rows (a shallow copy).

        ``None`` means no limit and returns the report unchanged.
        """
        if max_rows is None:
            return report
        if max_rows < 0:
            raise ValueError(f"max_rows must be None or >= 0, got {max_rows!r}")
        return {**report, "rows": list(report["rows"][:max_rows])}

    @staticmethod
    def cells(row: list) -> list[str]:
        return [str(cell) for cell in row]

    def render_header(self, report: dict) -> str:
        return ""

    @abstractmethod
    def render_rows(self, report: dict) -> str: ...

    def render_footer(self, report: dict) -> str:
        return ""


# --- discovery --------------------------------------------------------------


def _renderers() -> dict[str, type[BaseRenderer]]:
    """Map format name -> concrete renderer class, found via the hierarchy.

    Walks ``__subclasses__`` recursively so intermediate abstract bases are
    allowed; classes that are abstract or have no ``name`` are skipped.
    """
    found: dict[str, type[BaseRenderer]] = {}
    pending = list(BaseRenderer.__subclasses__())
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        name = getattr(cls, "name", None)
        if inspect.isabstract(cls) or not name:
            continue
        if name in found and found[name] is not cls:
            raise TypeError(
                f"format {name!r} is provided by both {found[name].__qualname__} "
                f"and {cls.__qualname__}"
            )
        found[name] = cls
    return found


def available_formats() -> list[str]:
    return sorted(_renderers())


def _lookup(fmt: str) -> BaseRenderer:
    try:
        return _renderers()[fmt]()
    except KeyError:
        raise UnknownFormat(
            f"unknown format {fmt!r}; available: {', '.join(available_formats())}"
        ) from None


def render(report: dict, fmt: str, max_rows: int | None = None, footer: bool = False) -> str:
    return _lookup(fmt).render(report, max_rows=max_rows, footer=footer)


def render_many(
    reports: list[dict], fmt: str, max_rows: int | None = None, footer: bool = False
) -> list[str]:
    """Render every report in ``reports`` with the same format.

    The format is resolved once up front, so an unknown format raises
    ``UnknownFormat`` before any report is rendered.
    """
    renderer = _lookup(fmt)
    return [renderer.render(report, max_rows=max_rows, footer=footer) for report in reports]


# --- renderers --------------------------------------------------------------


class TextRenderer(BaseRenderer):
    """Title line, a blank line, then one line per row, cells joined by two spaces."""

    name = "text"

    def render_header(self, report: dict) -> str:
        return f"{report['title']}\n\n"

    def render_rows(self, report: dict) -> str:
        return "\n".join("  ".join(self.cells(row)) for row in report["rows"])


class MarkdownRenderer(BaseRenderer):
    """``# title``, a blank line, then a pipe table with a header row and separator."""

    name = "markdown"

    @staticmethod
    def _pipe_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    def render_header(self, report: dict) -> str:
        columns = self.cells(report["columns"])
        return f"# {report['title']}\n\n{self._pipe_row(columns)}\n|" + "---|" * len(columns)

    def render_rows(self, report: dict) -> str:
        # Each row is prefixed rather than suffixed with a newline so the
        # output has no trailing newline and the empty-rows case is exact.
        return "".join("\n" + self._pipe_row(self.cells(row)) for row in report["rows"])


class CsvRenderer(BaseRenderer):
    """Header row then data rows, comma-separated, no title.

    Uses the ``csv`` module so cells containing commas, quotes or newlines
    are quoted correctly. Every line, including the last, ends in ``\\n``.
    """

    name = "csv"

    @staticmethod
    def _csv(rows) -> str:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        return buf.getvalue()

    def render_header(self, report: dict) -> str:
        return self._csv([self.cells(report["columns"])])

    def render_rows(self, report: dict) -> str:
        return self._csv(self.cells(row) for row in report["rows"])


class HtmlRenderer(BaseRenderer):
    """``<h1>`` title followed by a ``<table>`` with a ``<th>`` header row."""

    name = "html"

    @staticmethod
    def _tag_row(tag: str, cells: list[str]) -> str:
        return "<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>"

    def render_header(self, report: dict) -> str:
        title = html.escape(str(report["title"]))
        return f"<h1>{title}</h1>\n<table>\n{self._tag_row('th', self.cells(report['columns']))}\n"

    def render_rows(self, report: dict) -> str:
        return "".join(self._tag_row("td", self.cells(row)) + "\n" for row in report["rows"])

    def render_footer(self, report: dict) -> str:
        return "</table>"


class JsonRenderer(BaseRenderer):
    """The report dict serialised with ``json.dumps``.

    JSON is not line-structured, so the whole document is emitted from
    ``render_rows`` (which sees the already-truncated report); the header
    and footer hooks are intentionally empty, and the ``footer=True`` row
    count line is disabled because appending it would make the output
    invalid JSON.
    """

    name = "json"
    supports_footer = False

    def render_rows(self, report: dict) -> str:
        return json.dumps(report)
