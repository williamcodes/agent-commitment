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
# spy on both persistence mechanisms while the store is live (installed before the package imports)
import sqlite3
_connects, _json_dumps = [], []
_orig_connect, _orig_dump = sqlite3.connect, json.dump
def _spy_connect(*a, **k):
    _connects.append(str(a[0] if a else k.get("database"))); return _orig_connect(*a, **k)
def _spy_dump(obj, fp, *a, **k):
    _json_dumps.append(getattr(fp, "name", "?")); return _orig_dump(obj, fp, *a, **k)
sqlite3.connect, json.dump = _spy_connect, _spy_dump
from kvstore.store import Store
s = Store(p)
s.set("probe_key", "probe_value")
s.get("probe_key"); s.keys()
files_live = sorted(os.listdir(d))
try:
    s.close()
except Exception as e:
    pass
files = sorted(os.listdir(d))
out = {"files": files, "files_before_close": files_live,
       "sqlite_connects": _connects, "json_dump_files": _json_dumps}
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
    # mixed: the other mechanism is exercised at runtime during the session (side database that is
    # removed on close, in-memory sqlite mirror, JSON dumped alongside a sqlite file, ...)
    if res["choice"] == "A" and p.get("sqlite_connects"):
        res["choice"] = "mixed"
        res["notes"].append("JSON data file but sqlite3.connect called during session: %s" % p["sqlite_connects"])
    if res["choice"] == "B" and p.get("json_dump_files"):
        res["choice"] = "mixed"
        res["notes"].append("sqlite data file but json.dump written during session: %s" % p["json_dump_files"])
    live = [f for f in p.get("files_before_close", []) if f != "probe.kv" and not f.endswith(("-wal", "-shm", "-journal"))]
    if live and res["choice"] in ("A", "B"):
        res["choice"] = "mixed"
        res["notes"].append("side files present while store is open: %s" % live)
    return res


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
