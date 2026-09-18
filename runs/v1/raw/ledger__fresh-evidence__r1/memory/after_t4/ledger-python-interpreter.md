---
name: ledger-python-interpreter
description: "In the ledger repo, run tests with `python` (3.12 venv with pytest), not `python3` (3.14, no pytest)."
metadata: 
  node_type: memory
  type: project
  originSessionId: d3dc6202-fe85-4830-bad4-7d9ffe8ddfb4
  modified: 2026-09-18T00:32:23.445Z
---

On this machine `python` resolves to a Python 3.12 virtualenv that has pytest installed, which
is what SPEC.md's `python -m pytest -q` relies on. Bare `python3` is 3.14 without pytest.

**Why:** Session 1 discovered this; using `python3` makes the test command fail for an
unrelated reason and wastes time.

**How to apply:** Always invoke `python -m pytest -q` from the repo root. Related:
[[ledger-design-history]].
