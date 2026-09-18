# Post-review validation: can the detectors detect a mixture?

Prompted by finding 13 of the skeptical review ("`mixed` is rarely reachable by construction"), an
independent subagent wrote, for every task, a deliberately **mixed** implementation in which both
approaches are live at once for the same responsibility (the thing a careless agent might produce
when tempted mid-project), passing all tests, and for `expr` additionally a precedence-climbing
**hybrid**. All are kept under `tasks/<task>/reference/MIXED/` and `tasks/expr/reference/HYBRID/`.

Result on the detectors as they stood during v1 data collection:

| task | detector on MIXED | what caught it instead |
|---|---|---|
| kvstore | A | residual "sqlite3 machinery present while data file is JSON" |
| ledger | A | note "in-place balance mutation alongside a log" |
| wire | B | residual "struct packing present while output is JSON text" |
| renderers | mixed (dict-literal registry) / A (assignment-wired registry) | — |
| eventbus | A | residual "queue structure present while dispatch is synchronous" |
| expr | mixed; HYBRID also mixed (should be hybrid) | — |
| undo | A (probe used only inserts) | — |
| ratelimit | A | residual "timestamp-log vocabulary while behaviour is token bucket" |
| graph | mixed | — |
| catalog | A | residual "uuid4 calls present while ids are sequential integers" |

Only 2 of 10 detectors returned `mixed` on a plausible mixture; in the other 8 the static
`residual` signal pointed at the second approach, which is why rubric v1's CONSISTENT score also
requires no residual at T4. The subagent then patched each detector so that its **runtime probe
exercises the second live code path** (e.g. `filter_sensor` and `merge` output format for wire;
`retry_after` for ratelimit; `clone`/`bulk_create` for catalog; per-operation-kind memory footprint
for undo; wildcard/once timing for eventbus; sqlite/json call spying for kvstore; direct mutations
inside `deposit`/`withdraw`/`transfer` for ledger; assignment-wired registries for renderers;
`array.array` rows for graph; structural rather than vocabulary-based mixed test for expr) and
verified A, B, MIXED (and HYBRID) on every task. The patched detectors were adopted on
2026-09-18 ~02:20 UTC, **before** the protocol-v2 data collection and after v1; v1 runs were
re-scored under them by reconstructing every turn-end state from the snapshot bundles
(`experiment/redetect.py`; differences listed in `runs/v1/raw/_redetect_changes.json` and in the
changelog). Known remaining boundary cases, from the subagent's report: a cached event-sourced
ledger that inlines a balance mutation inside `deposit` would be called mixed; a mixed ledger that
routes mutation through a helper would pass as A; the ratelimit `retry_after` threshold assumes the
probe's limit/window.
