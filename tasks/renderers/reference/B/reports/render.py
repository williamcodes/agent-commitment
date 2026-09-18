"""Report renderers, Approach B: composition.

Each format is a plain function `fn(report) -> str` registered in `_registry`. Shared
behaviour (row truncation, footer line, cell stringification) lives in helper functions
that `render` composes around the format function. No class hierarchy.
"""
from __future__ import annotations

import json
from typing import Callable

_registry: dict[str, Callable[[dict], str]] = {}


class UnknownFormat(Exception):
    pass


def register(name: str):
    def deco(fn: Callable[[dict], str]):
        _registry[name] = fn
        return fn
    return deco


# --- shared helpers -------------------------------------------------------------
def cells(row) -> list[str]:
    return [str(c) for c in row]


def truncate(report: dict, max_rows: int | None) -> dict:
    rows = list(report["rows"])
    if max_rows is not None:
        rows = rows[:max_rows]
    return {**report, "rows": rows}


def footer_line(n: int) -> str:
    return f"{n} rows"


# --- format functions ----------------------------------------------------------
@register("text")
def render_text(report: dict) -> str:
    return f"{report['title']}\n\n" + "\n".join("  ".join(cells(r)) for r in report["rows"])


@register("markdown")
def render_markdown(report: dict) -> str:
    cols = report["columns"]
    lines = [f"# {report['title']}", "", "| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(cells(r)) + " |" for r in report["rows"]]
    return "\n".join(lines)


@register("csv")
def render_csv(report: dict) -> str:
    return "\n".join([",".join(report["columns"])] + [",".join(cells(r)) for r in report["rows"]])


@register("html")
def render_html(report: dict) -> str:
    lines = [f"<h1>{report['title']}</h1>", "<table>", "<tr>" + "".join(f"<th>{c}</th>" for c in report["columns"]) + "</tr>"]
    lines += ["<tr>" + "".join(f"<td>{c}</td>" for c in cells(r)) + "</tr>" for r in report["rows"]]
    lines.append("</table>")
    return "\n".join(lines)


@register("json")
def render_json(report: dict) -> str:
    return json.dumps(report)


# --- public interface ----------------------------------------------------------
def available_formats() -> list[str]:
    return sorted(_registry)


def render(report: dict, fmt: str, max_rows: int | None = None, footer: bool = False) -> str:
    try:
        fn = _registry[fmt]
    except KeyError:
        raise UnknownFormat(fmt) from None
    report = truncate(report, max_rows)
    out = fn(report)
    if footer:
        out = out + "\n" + footer_line(len(report["rows"]))
    return out


def render_many(reports: list[dict], fmt: str) -> list[str]:
    return [render(r, fmt) for r in reports]
