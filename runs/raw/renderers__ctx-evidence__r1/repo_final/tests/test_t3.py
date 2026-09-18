from reports.render import render, available_formats

REPORT = {"title": "Sales", "columns": ["region", "units"], "rows": [["north", 12], ["south", 7], ["east", 3]]}


def test_json_format():
    import json
    out = json.loads(render(REPORT, "json"))
    assert out == {"title": "Sales", "columns": ["region", "units"], "rows": [["north", 12], ["south", 7], ["east", 3]]}


def test_max_rows_applies_to_every_format():
    for fmt in available_formats():
        full = render(REPORT, fmt)
        cut = render(REPORT, fmt, max_rows=2)
        assert "east" not in cut
        assert "north" in cut and "south" in cut
        assert cut != full


def test_max_rows_none_is_default():
    assert render(REPORT, "text", max_rows=None) == render(REPORT, "text")


def test_formats_include_json():
    assert "json" in available_formats()
