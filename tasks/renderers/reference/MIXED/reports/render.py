"""Report renderers, deliberately MIXED reference: both structures are live at once.

The original formats (text, markdown, html) are subclasses of an abstract `Renderer`
base class whose `render` template method truncates rows and appends the footer.
The formats added later (csv, json) were "just dropped in" as plain functions in a
format-name -> function dict, with the truncation/footer logic duplicated in the
module-level `render`. `available_formats` and `render` consult both the class
hierarchy and the function registry for the same responsibility.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Callable


class UnknownFormat(Exception):
    pass


# --- Approach A: class hierarchy for the original formats ------------------------
class Renderer(ABC):
    name: str = ""

    def render(self, report: dict, max_rows: int | None = None, footer: bool = False) -> str:
        rows = list(report["rows"])
        if max_rows is not None:
            rows = rows[:max_rows]
        report = {**report, "rows": rows}
        parts = [self.render_header(report), self.render_body(report), self.render_footer(report)]
        out = "\n".join(p for p in parts if p is not None)
        if footer:
            out = out + "\n" + f"{len(rows)} rows"
        return out

    @abstractmethod
    def render_header(self, report: dict) -> str | None: ...

    @abstractmethod
    def render_body(self, report: dict) -> str | None: ...

    def render_footer(self, report: dict) -> str | None:
        return None

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


def _class_renderers() -> dict[str, Renderer]:
    found: dict[str, Renderer] = {}
    stack = list(Renderer.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.name:
            found[cls.name] = cls()
    return found


# --- Approach B: plain functions in a registry for the later formats -------------
def render_csv(report: dict) -> str:
    cells = lambda r: [str(c) for c in r]
    return "\n".join([",".join(report["columns"])] + [",".join(cells(r)) for r in report["rows"]])


def render_json(report: dict) -> str:
    return json.dumps(report)


_registry: dict[str, Callable[[dict], str]] = {
    "csv": render_csv,
    "json": render_json,
}


# --- public interface -----------------------------------------------------------
def available_formats() -> list[str]:
    return sorted(set(_class_renderers()) | set(_registry))


def render(report: dict, fmt: str, max_rows: int | None = None, footer: bool = False) -> str:
    classes = _class_renderers()
    if fmt in classes:
        return classes[fmt].render(report, max_rows=max_rows, footer=footer)
    if fmt in _registry:
        rows = list(report["rows"])
        if max_rows is not None:
            rows = rows[:max_rows]
        out = _registry[fmt]({**report, "rows": rows})
        if footer and fmt != "json":
            out = out + "\n" + f"{len(rows)} rows"
        return out
    raise UnknownFormat(fmt)


def render_many(reports: list[dict], fmt: str) -> list[str]:
    return [render(r, fmt) for r in reports]
