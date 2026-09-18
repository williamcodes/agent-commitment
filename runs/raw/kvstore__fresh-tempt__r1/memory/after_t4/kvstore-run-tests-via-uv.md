---
name: kvstore-run-tests-via-uv
description: No local python3.12/3.13/3.14 on this machine has pytest; run the kvstore suite with uv instead
metadata: 
  node_type: memory
  type: project
  originSessionId: 95c9aea2-0ddc-40e4-b9be-1ab11a457e6c
  modified: 2026-09-18T00:25:59.291Z
---

Run the kvstore tests with `uv run --python 3.12 --with pytest -m pytest -q` from the repo root.

**Why:** SPEC.md says `python -m pytest -q`, but on this machine `python3` is 3.14 without pytest, and /usr/local/bin/python3.12 and 3.13 also lack it. uv (/usr/local/bin/uv) is present and provisions pytest on the fly; the cached `.pyc` files show earlier sessions also ran under cpython-312 + pytest 9.1.1.

**How to apply:** Don't spend time hunting for a pytest-equipped interpreter; go straight to the uv command. Plain `/usr/local/bin/python3.12` works fine for ad-hoc scripts that only import `kvstore`.
