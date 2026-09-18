from reports.render import render

REPORT = {"title": "Sales", "columns": ["region", "units"], "rows": [["north", 12], ["south", 7]]}


def test_footer_line_text():
    out = render(REPORT, "text", footer=True).splitlines()
    assert out[-1] == "2 rows"


def test_footer_markdown_and_csv():
    assert render(REPORT, "markdown", footer=True).splitlines()[-1] == "2 rows"
    assert render(REPORT, "csv", footer=True).splitlines()[-1] == "2 rows"


def test_footer_counts_after_truncation():
    out = render(REPORT, "text", max_rows=1, footer=True).splitlines()
    assert out[-1] == "1 rows"


def test_no_footer_by_default():
    assert not render(REPORT, "text").endswith("rows")
