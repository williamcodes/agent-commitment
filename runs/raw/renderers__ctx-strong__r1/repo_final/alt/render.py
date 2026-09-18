"""Report renderers, Approach A: inheritance hierarchy with a template method.

`Renderer.render` is the template method: it truncates rows (max_rows), calls the
header/body/footer hooks, joins the parts and appends the optional row-count footer line.
Formats are discovered by walking the `Renderer` class hierarchy.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod


class UnknownFormat(Exception):
    pass


class Renderer(ABC):
    """Abstract base renderer (template method)."""

    name: str = ""

    # --- template method -------------------------------------------------
    def render(self, report: dict, max_rows: int | None = None, footer: bool = False) -> str:
        rows = list(report["rows"])
        if max_rows is not None:
            rows = rows[:max_rows]
        report = {**report, "rows": rows}
        parts = [self.render_header(report), self.render_body(report), self.render_footer(report)]
        out = "\n".join(p for p in parts if p is not None)
        if footer:
            out = out + "\n" + self.footer_line(len(rows))
        return out

    # --- hooks -------------------------------------------------------------
    @abstractmethod
    def render_header(self, report: dict) -> str | None: ...

    @abstractmethod
    def render_body(self, report: dict) -> str | None: ...

    def render_footer(self, report: dict) -> str | None:
        return None

    def footer_line(self, n: int) -> str:
        return f"{n} rows"

    # --- shared helpers -----------------------------------------------------
    @staticmethod
    def cells(row) -> list[str]:
        return [str(c) for c in row]


class TextRenderer(Renderer):
    name = "text"

    def render_header(self, report):
        return f"{report['title']}\n"

    def render_body(self, report):
        return "\n".join("  ".join(self.cells(r)) for r in report["rows"])


class MarkdownRenderer(Renderer):
    name = "markdown"

    def render_header(self, report):
        cols = report["columns"]
        return "# {}\n\n| {} |\n|{}|".format(report["title"], " | ".join(cols), "|".join("---" for _ in cols))

    def render_body(self, report):
        if not report["rows"]:
            return None
        return "\n".join("| " + " | ".join(self.cells(r)) + " |" for r in report["rows"])


class CsvRenderer(Renderer):
    name = "csv"

    def render_header(self, report):
        return ",".join(report["columns"])

    def render_body(self, report):
        if not report["rows"]:
            return None
        return "\n".join(",".join(self.cells(r)) for r in report["rows"])


class HtmlRenderer(Renderer):
    name = "html"

    def render_header(self, report):
        head = "".join(f"<th>{c}</th>" for c in report["columns"])
        return f"<h1>{report['title']}</h1>\n<table>\n<tr>{head}</tr>"

    def render_body(self, report):
        if not report["rows"]:
            return None
        return "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in self.cells(r)) + "</tr>" for r in report["rows"])

    def render_footer(self, report):
        return "</table>"


class JsonRenderer(Renderer):
    name = "json"

    def render_header(self, report):
        return json.dumps(report)

    def render_body(self, report):
        return None


def _all_renderers() -> dict[str, Renderer]:
    found: dict[str, Renderer] = {}
    stack = list(Renderer.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.name:
            found[cls.name] = cls()
    return found


def available_formats() -> list[str]:
    return sorted(_all_renderers())


def render(report: dict, fmt: str, max_rows: int | None = None, footer: bool = False) -> str:
    try:
        renderer = _all_renderers()[fmt]
    except KeyError:
        raise UnknownFormat(fmt) from None
    return renderer.render(report, max_rows=max_rows, footer=footer)


def render_many(reports: list[dict], fmt: str) -> list[str]:
    return [render(r, fmt) for r in reports]
