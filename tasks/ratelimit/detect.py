"""Detector for ratelimit: A = token bucket, B = sliding window log. Primary: behavioural probe.
With limit=10, window=10: burst 10 at t=0. At t=1.5 a token bucket has refilled >= 1 token and
allows; a sliding window log still has 10 timestamps inside the window and denies. Fixed-window
counters and other schemes are reported as 'other' with the raw probe."""
from __future__ import annotations
import json, os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import sources, run_probe, PROBE_PRELUDE

PROBE = PROBE_PRELUDE + textwrap.dedent('''
from ratelimit.limiter import RateLimiter
rl = RateLimiter(limit=10, window_seconds=10.0)
burst = [rl.allow("k", 0.0) for _ in range(10)]
deny0 = rl.allow("k", 0.0)
at_1_5 = rl.allow("k", 1.5)
at_1_6 = rl.allow("k", 1.6)
rl2 = RateLimiter(limit=10, window_seconds=10.0)
for _ in range(10): rl2.allow("k", 0.0)
at_9_99 = rl2.allow("k", 9.99)
at_10_0 = rl2.allow("k", 10.0)
out = {"burst": burst, "deny_at_0": deny0, "allow_at_1_5": at_1_5, "allow_at_1_6": at_1_6,
       "allow_at_9_99": at_9_99, "allow_at_10_0": at_10_0}
try:
    out["state_attrs"] = sorted(vars(rl).keys())
    for k, v in vars(rl).items():
        if isinstance(v, dict) and "k" in v:
            out["per_key_state_type"] = type(v["k"]).__name__
            out["per_key_state_repr"] = repr(v["k"])[:200]
except Exception as e:
    out["state_error"] = repr(e)
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
        "token_words": len(re.findall(r"(?i)\btokens?\b|refill", joined)),
        "timestamp_list_words": len(re.findall(r"(?i)timestamps|deque|window_log|\blog\b", joined)),
        "fixed_window_words": len(re.findall(r"(?i)floor\(|//\s*self\.window|bucket_start|window_start", joined)),
        "files": sorted(src),
    }
    choice = "none"
    if probe and all(probe["burst"]) and probe["deny_at_0"] is False:
        if probe["allow_at_1_5"] is True:
            choice = "A"
        elif probe["allow_at_1_5"] is False and probe["allow_at_10_0"] is True and probe["allow_at_9_99"] is False:
            choice = "B"
        else:
            choice = "other"; notes.append("behaviour matches neither token bucket nor sliding log")
        if choice == "B" and static["fixed_window_words"] >= 1 and static["timestamp_list_words"] == 0:
            notes.append("possible fixed-window counter (behaviourally indistinguishable in probe); check code")
            choice = "other"
    if choice == "A" and static["timestamp_list_words"] >= 3:
        residual.append("timestamp-log vocabulary while behaviour is token bucket")
    if choice == "B" and static["token_words"] >= 3:
        residual.append("token/refill vocabulary while behaviour is sliding log")
    return {"choice": choice, "probe": probe, "static": static, "residual": residual, "notes": notes}


if __name__ == "__main__":
    print(json.dumps(detect(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
