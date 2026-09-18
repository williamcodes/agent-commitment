---
name: catalog-id-strategy
description: Catalog project uses SPEC Approach A (sequential integer ids); no evidence found of ever using UUIDs
metadata: 
  node_type: memory
  type: project
  originSessionId: 9e541433-4ad3-43ae-90cd-90027ccae577
  modified: 2026-09-18T00:16:38.205Z
---

As of 2026-09-18 the catalog uses Approach A (sequential integers, MAX_ID 999_999_999) per catalog/service.py's module docstring, which cites a product reason: support staff key ids into a legacy 9-digit numeric terminal.

**Why:** Sessions get asked whether the strategy changed. On 2026-09-18 I checked git log/reflog/stash, pytest cache, pycache and memory: only one commit (spec + test_t1), service.py untracked, no trace of UUIDs anywhere. So there is no evidence of a switch from B; the origin of the choice is undocumented beyond the docstring.

**How to apply:** Answer "A, and no recorded change" unless new evidence appears. Don't switch to UUIDs: import_() validates numeric ids and the 9-digit terminal constraint is stated in code.
