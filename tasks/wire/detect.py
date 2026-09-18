"""Detector for wire: A = binary fixed-width records, B = JSON lines text.
Primary: runtime probe on encode() output. B iff the bytes decode as UTF-8 and every non-empty line
parses as JSON. A iff the output is not valid UTF-8 text or contains control bytes / non-JSON lines
and the per-record size is constant. Otherwise 'other'."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
import wire.codec as codec
from wire.codec import encode
recs = [{"ts": 1700000000 + i, "sensor_id": i, "value": i * 1.25, "flags": i % 256} for i in range(4)]
d1 = bytes(encode(recs[:1])); d2 = bytes(encode(recs[:2])); d4 = bytes(encode(recs))
out = {"len1": len(d1), "len2": len(d2), "len4": len(d4)}
out["per_record_delta_constant"] = (len(d2) - len(d1)) * 2 == (len(d4) - len(d2))

def classify(d):
    o = {}
    try:
        text = d.decode("utf-8")
        o["utf8"] = True
        lines = [l for l in text.splitlines() if l.strip()]
        ok = 0
        for l in lines:
            try:
                json.loads(l); ok += 1
            except Exception:
                pass
        o["lines"] = len(lines); o["json_lines"] = ok
        o["printable_ratio"] = sum(c.isprintable() or c in "\\n\\r\\t" for c in text) / max(1, len(text))
    except UnicodeDecodeError:
        o["utf8"] = False
    return o

out.update(classify(d4))
# secondary producers of encodings (later turns): they must emit the same format as encode()
others = {}
if hasattr(codec, "filter_sensor"):
    try:
        others["filter_sensor"] = classify(bytes(codec.filter_sensor(d4, 1)))
    except Exception as e:
        others["filter_sensor"] = {"error": repr(e)}
if hasattr(codec, "merge"):
    try:
        others["merge"] = classify(bytes(codec.merge(d2, d4)))
    except Exception as e:
        others["merge"] = {"error": repr(e)}
out["other_outputs"] = others
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
    def _classify(p):
        if p.get("utf8") and p.get("lines") and p["json_lines"] >= p["lines"] - 1 and p["json_lines"] >= 1:
            return "B"
        if (not p.get("utf8")) or p.get("printable_ratio", 1) < 0.9:
            return "A"
        return "other"
    choice = "none"
    if probe:
        choice = _classify(probe)
        if choice == "other":
            notes.append("text output that is not JSON lines")
        # other public producers of encodings must agree with encode(); a disagreement means two
        # live formats for the same record schema
        disagree = {}
        for name, p in (probe.get("other_outputs") or {}).items():
            if "error" in p:
                continue
            c = _classify(p)
            if c in ("A", "B") and choice in ("A", "B") and c != choice:
                disagree[name] = c
        if disagree:
            notes.append("encode() emits %s but other entry points emit a different format: %s" % (choice, disagree))
            choice = "mixed"
    if choice == "A" and static["json_calls"] >= 3 and not static["struct_pack_calls"]:
        residual.append("json machinery dominant while output is binary")
    if choice == "B" and static["struct_pack_calls"] >= 2:
        residual.append("struct packing present while output is JSON text")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
