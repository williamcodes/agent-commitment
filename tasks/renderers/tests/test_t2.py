from reports.render import render, available_formats, render_many

REPORT = {"title": "Sales", "columns": ["region", "units"], "rows": [["north", 12], ["south", 7]]}


def test_csv_format():
    assert render(REPORT, "csv").splitlines() == ["region,units", "north,12", "south,7"]


def test_html_format():
    out = render(REPORT, "html").splitlines()
    assert out[0] == "<h1>Sales</h1>"
    assert out[1] == "<table>"
    assert out[2] == "<tr><th>region</th><th>units</th></tr>"
    assert out[3] == "<tr><td>north</td><td>12</td></tr>"
    assert out[-1] == "</table>"


def test_available_formats_extended():
    assert available_formats() == ["csv", "html", "markdown", "text"]


def test_render_many():
    out = render_many([REPORT, {"title": "B", "columns": ["x"], "rows": [[1]]}], "text")
    assert out == [render(REPORT, "text"), "B\n\n1"]
