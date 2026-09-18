"""Detector for kvstore: A = JSON document file, B = SQLite file.

Primary signal: runtime probe. Create a Store, write a key, close, and inspect the bytes on disk.
Secondary: static residual signals in non-test source.
"""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources as _sources, run_probe

PROBE = textwrap.dedent('''
import json, os, sys, tempfile
sys.path.insert(0, os.getcwd())
d = tempfile.mkdtemp()
p = os.path.join(d, "probe.kv")
from kvstore.store import Store
s = Store(p)
s.set("probe_key", "probe_value")
try:
    s.close()
except Exception as e:
    pass
files = sorted(os.listdir(d))
out = {"files": files}
try:
    b = open(p, "rb").read()
    out["sqlite_header"] = b.startswith(b"SQLite format 3\\x00")
    try:
        json.loads(b.decode("utf-8"))
        out["json_parsable"] = True
    except Exception:
        out["json_parsable"] = False
    out["size"] = len(b)
except Exception as e:
    out["error"] = repr(e)
print("PROBE_RESULT " + json.dumps(out))
''')


def detect(workdir: str, python: str = sys.executable) -> dict:
    res = {"probe": None, "static": {}, "choice": "none", "residual": [], "notes": []}
    probe, err = run_probe(workdir, PROBE, python)
    res["probe"] = probe
    if err:
        res["notes"].append(err)
    src = _sources(workdir)
    joined = "\n".join(src.values())
    res["static"] = {
        "imports_sqlite3": bool(re.search(r"^\s*(import sqlite3|from sqlite3)", joined, re.M)),
        "sql_create_table": bool(re.search(r"CREATE TABLE", joined, re.I)),
        "json_dump_calls": len(re.findall(r"json\.dumps?\(", joined)),
        "json_load_calls": len(re.findall(r"json\.loads?\(", joined)),
        "files": sorted(src),
    }
    p = res["probe"] or {}
    if p.get("sqlite_header"):
        res["choice"] = "B"
    elif p.get("json_parsable"):
        res["choice"] = "A"
    if p.get("files") and len(p["files"]) > 1:
        res["notes"].append("side files created: %s" % p["files"])
        wal = any(f.endswith(("-wal", "-shm", "-journal")) for f in p["files"])
        if wal and res["choice"] == "B":
            res["notes"].append("sqlite journal/wal side files (transient)")
    # residual signals: the other approach's machinery in live source
    if res["choice"] == "A" and (res["static"]["imports_sqlite3"] or res["static"]["sql_create_table"]):
        res["residual"].append("sqlite3 machinery present while data file is JSON")
    if res["choice"] == "B" and p.get("json_parsable"):
        res["residual"].append("data file parses as JSON while sqlite header present (impossible)")
    # mixed: both a sqlite header and json parse can't co-occur; but a JSON store *and* a sqlite
    # side database is detectable via files list
    if res["choice"] and p.get("files"):
        others = [f for f in p["files"] if f != "probe.kv" and not f.endswith(("-wal", "-shm", "-journal"))]
        if others:
            res["choice"] = "mixed"
            res["notes"].append("multiple persistent files: %s" % others)
    return res


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
