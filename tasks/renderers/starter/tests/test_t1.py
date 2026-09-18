import pytest
from reports.render import render, available_formats, UnknownFormat

REPORT = {"title": "Sales", "columns": ["region", "units"], "rows": [["north", 12], ["south", 7]]}


def test_text_format():
    out = render(REPORT, "text")
    assert out.splitlines() == ["Sales", "", "north  12", "south  7"]


def test_markdown_format():
    out = render(REPORT, "markdown")
    assert out.splitlines() == ["# Sales", "", "| region | units |", "|---|---|", "| north | 12 |", "| south | 7 |"]


def test_available_formats():
    assert available_formats() == ["markdown", "text"]


def test_unknown_format():
    with pytest.raises(UnknownFormat):
        render(REPORT, "pdf")


def test_empty_rows():
    r = {"title": "T", "columns": ["a"], "rows": []}
    assert render(r, "text").splitlines() == ["T", ""]
    assert render(r, "markdown").splitlines() == ["# T", "", "| a |", "|---|"]
