---
name: ledger-design-history
description: The ledger started as Approach B (snapshot dict) and was migrated to Approach A (event-sourced log) on 2026-09-18 because of an audit requirement; none of this is in git history.
metadata: 
  node_type: memory
  type: project
  originSessionId: d3dc6202-fe85-4830-bad4-7d9ffe8ddfb4
  modified: 2026-09-18T00:32:18.739Z
---

The ledger codebase currently uses **Approach A (event sourcing)**: an append-only list of
`Operation` records is the source of truth; `_State` (balances, frozen, overdraft) is a cache
folded from it. It did NOT start that way.

Timeline (all on 2026-09-18, four sessions; only "Initial commit: spec and tests" is committed):
1. Session 1 implemented Approach B (plain `dict[str, int]` mutated in place) because the
   original interface exposed no history/audit features.
2. Session 2 added apply_interest / close_account / total_assets, keeping B.
3. Session 3 added freeze/unfreeze/batch_transfer and, on the product owner's audit
   requirement (ledger is the only system of record; must replay every operation and any
   historical balance; corrections appended, never edited), rewrote the module as Approach A
   and appended an "Audit requirement" section to SPEC.md declaring B ruled out.
4. Session 4 added set_overdraft_limit / overdraft_limit / balances() as a logged
   `set_overdraft` operation kind.

**Why:** The migration is only recorded in SPEC.md's audit section and in prior session
transcripts; git has a single commit, so a fresh session cannot see it from history.

**How to apply:** Any new feature that changes what is permitted or changes balances must be a
new `Operation` kind applied through `_State.apply` and `Ledger._record`, so `balance_at`
replay keeps validating. Never mutate `_state` directly. See [[ledger-python-interpreter]].
