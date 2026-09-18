---
name: wire-format-history
description: "The wire codec uses JSON lines (Approach B); the spec rewrite and \"no longer\" wording indicate a switch away from compact binary (A) mid-project, but no committed history proves it"
metadata: 
  node_type: memory
  type: project
  originSessionId: 0ffb0a26-d29f-4f20-beb0-09822179e561
  modified: 2026-09-18T03:53:10.510Z
---

As of 2026-09-18 the `wire` codec uses Approach B (JSON lines). The committed SPEC.md (initial commit 7201b76) offered A (compact binary) and B as an open choice. The uncommitted SPEC.md rewrite says product requirements settled it on B (technicians hand-edit logs with grep/sed; storage no longer a concern) and was made in the same minute as a codec.py rewrite, after the third feature (dump_text/filter_sensor) and before merge. codec.py has never been committed, so an earlier binary version cannot be verified from git.

**Why:** A later session was asked which format is in use and whether it changed; only the working tree answers this, and the evidence for a change is inferential.

**How to apply:** Treat B as settled. If asked about history, say a switch from A to B is strongly indicated by the spec rewrite but not provable from git. Consider committing wire/codec.py so future history is visible.
