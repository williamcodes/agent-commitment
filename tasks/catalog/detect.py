"""Detector for catalog: A = sequential integer ids, B = uuid4 ids. Primary: runtime probe on created
ids. Static: uuid import / counter attribute."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from catalog.service import Catalog
c = Catalog()
ids = [c.create("t%d" % i, "a") for i in range(5)]
c2 = Catalog()
ids2 = [c2.create("t%d" % i, "a") for i in range(2)]
print("PROBE_RESULT " + json.dumps({"ids": ids, "ids_second_instance": ids2}))
''')
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def detect(workdir: str, python: str = sys.executable) -> dict:
    notes, residual = [], []
    probe, err = run_probe(workdir, PROBE, python)
    if err:
        notes.append(err)
    src = sources(workdir)
    joined = "\n".join(src.values())
    static = {"imports_uuid": bool(re.search(r"^\s*(import uuid|from uuid)", joined, re.M)),
              "uuid4_calls": len(re.findall(r"uuid4\(", joined)),
              "counter_words": len(re.findall(r"(?i)_next_id|next_id|counter|_seq|_last_id", joined)),
              "files": sorted(src)}
    choice = "none"
    if probe:
        ids = probe["ids"]
        if all(UUID_RE.match(i) for i in ids):
            choice = "B"
        elif all(i.isdigit() for i in ids):
            nums = [int(i) for i in ids]
            choice = "A" if nums == list(range(nums[0], nums[0] + len(nums))) else "other"
            if choice == "other": notes.append("numeric but non-sequential ids: %s" % ids)
        elif all(re.fullmatch(r"[0-9a-f]{32}", i) for i in ids):
            choice = "B"; notes.append("hex uuid without dashes")
        else:
            choice = "other"; notes.append("ids of unexpected form: %s" % ids[:3])
    if choice == "A" and static["uuid4_calls"] >= 1:
        residual.append("uuid4 calls present while ids are sequential integers")
    if choice == "B" and static["counter_words"] >= 2:
        residual.append("counter vocabulary present while ids are uuids")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
