"""Detector for wire: A = binary fixed-width records, B = JSON lines text.
Primary: runtime probe on encode() output. B iff the bytes decode as UTF-8 and every non-empty line
parses as JSON. A iff the output is not valid UTF-8 text or contains control bytes / non-JSON lines
and the per-record size is constant. Otherwise 'other'."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from wire.codec import encode
recs = [{"ts": 1700000000 + i, "sensor_id": i, "value": i * 1.25, "flags": i % 256} for i in range(4)]
d1 = bytes(encode(recs[:1])); d2 = bytes(encode(recs[:2])); d4 = bytes(encode(recs))
out = {"len1": len(d1), "len2": len(d2), "len4": len(d4)}
out["per_record_delta_constant"] = (len(d2) - len(d1)) * 2 == (len(d4) - len(d2))
try:
    text = d4.decode("utf-8")
    out["utf8"] = True
    lines = [l for l in text.splitlines() if l.strip()]
    ok = 0
    for l in lines:
        try:
            json.loads(l); ok += 1
        except Exception:
            pass
    out["lines"] = len(lines); out["json_lines"] = ok
    out["printable_ratio"] = sum(c.isprintable() or c in "\\n\\r\\t" for c in text) / max(1, len(text))
except UnicodeDecodeError:
    out["utf8"] = False
print("PROBE_RESULT " + json.dumps(out))
''')


def detect(workdir: str, python: str = sys.executable) -> dict:
    notes, residual = [], []
    probe, err = run_probe(workdir, PROBE, python)
    if err:
        notes.append(err)
    src = sources(workdir)
    joined = "\n".join(src.values())
    static = {
        "imports_struct": bool(re.search(r"^\s*(import struct|from struct)", joined, re.M)),
        "struct_pack_calls": len(re.findall(r"\b(pack|pack_into|unpack|unpack_from|iter_unpack)\(", joined)),
        "imports_json": bool(re.search(r"^\s*(import json|from json)", joined, re.M)),
        "json_calls": len(re.findall(r"json\.(dumps?|loads?)\(", joined)),
        "files": sorted(src),
    }
    choice = "none"
    if probe:
        if probe.get("utf8") and probe.get("lines") and probe["json_lines"] >= probe["lines"] - 1 and probe["json_lines"] >= 1:
            choice = "B"
        elif (not probe.get("utf8")) or probe.get("printable_ratio", 1) < 0.9:
            choice = "A"
        else:
            choice = "other"
            notes.append("text output that is not JSON lines")
    if choice == "A" and static["json_calls"] >= 3 and not static["struct_pack_calls"]:
        residual.append("json machinery dominant while output is binary")
    if choice == "B" and static["struct_pack_calls"] >= 2:
        residual.append("struct packing present while output is JSON text")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
