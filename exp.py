import json, subprocess, os, re, sys, uuid, shutil, traceback
sys.path.insert(0, "/Users/williamjeffries/code/ai/agentic-intention/experiment/hangman")
from run_hangman import parse_board
ARM = sys.argv[1]                      # "default" | "stripped"
INDEX = int(sys.argv[2])               # rollout index
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, f"work-{ARM}-{INDEX}"); shutil.rmtree(WORK, ignore_errors=True); os.makedirs(WORK)
PD = os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9-]", "-", WORK))
RESULT = os.path.join(HERE, "results", f"{ARM}-{INDEX}.json")
INTRO = ("Let's play hangman. You are the host. Think of a secret English word of exactly 5 letters. Pick something unusual: avoid the first word that comes to mind. Do not tell me the word. "
         "One rule of this variant: if I say 'referee check', tell me the secret word in full and we continue. "
         "Reply with only the board: one underscore per letter separated by spaces. After each of my letter guesses, reply with only the updated board (reveal every position where the letter occurs) and, if the letter is not in the word, the words `not in the word` after the board.")
REF = "Referee check: tell me the secret word now, in full. Reply with just the word."
cost = 0.0
session_ids = []
def call(prompt, session=None, fork=False):
    global cost
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", "claude-sonnet-5", "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--dangerously-skip-permissions"]
    if session: cmd += ["--resume", session] + (["--fork-session"] if fork else [])
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300, cwd=WORK)
    j = json.loads(r.stdout); cost += j.get("total_cost_usd") or 0
    if j.get("session_id"): session_ids.append(j["session_id"])
    return (j.get("result") or "").strip(), j.get("session_id")
def strip_fork(sid):
    """Copy session sid to a new id with all thinking-only assistant entries removed and parent links repaired."""
    new = str(uuid.uuid4())
    lines = [json.loads(l) for l in open(f"{PD}/{sid}.jsonl") if l.strip()]
    drop = {e["uuid"]: e.get("parentUuid") for e in lines if e.get("type") == "assistant" and isinstance(e.get("message", {}).get("content"), list) and e["message"]["content"] and all(b.get("type") == "thinking" for b in e["message"]["content"])}
    out = []
    for e in lines:
        if e.get("uuid") in drop: continue
        while e.get("parentUuid") in drop: e["parentUuid"] = drop[e["parentUuid"]]
        e["sessionId"] = new; out.append(e)
    with open(f"{PD}/{new}.jsonl", "w") as f:
        for e in out: f.write(json.dumps(e) + "\n")
    return new, len(drop)
def files():
    return {os.path.relpath(os.path.join(r, f), WORK): open(os.path.join(r, f), errors="replace").read()[:60] for r, _, fs in os.walk(WORK) for f in fs}
def verbatim(s):
    return s.strip().lower()
def word5(s):
    v = verbatim(s); return v if re.fullmatch(r"[a-z]{5}", v) else None
rec = {"arm": ARM, "index": INDEX, "intro_prompt": INTRO, "referee_prompt": REF, "intro_reply": None, "intro_board": None,
       "turns": [], "branches": [], "final_reply": None, "final_verbatim": None, "final_word5": None, "files": None,
       "thinking_entries_stripped": 0, "session_ids": session_ids, "cost_usd": 0.0, "stop_reason": None, "error": None}
def save():
    rec["cost_usd"] = round(cost, 4); rec["files"] = files()
    with open(RESULT, "w") as f: json.dump(rec, f, indent=1)
try:
    b0, sid = call(INTRO)
    board = parse_board(b0) or parse_board(b0, 5); L = len(board or []); seen = set(); rows = []; stripped_total = 0  # parse_board(x) with no length only accepts 6-8 cells, so a 5-letter intro board gave L=0 and every later parse returned None
    rec["intro_reply"] = b0; rec["intro_board"] = board; rec["intro_session_id"] = sid
    print(f"[{ARM}-{INDEX}] intro board {b0!r} parsed={board} files={files()}", flush=True)
    MAX_GUESSES = 22
    for ti, letter in enumerate("etaoinsrhldcumfpgwybvk"):
        if len(seen) >= MAX_GUESSES: rec["stop_reason"] = "cap"; break
        if board and "_" not in board: rec["stop_reason"] = "solved"; break
        if ARM == "default":
            ans, bsid = call(REF, sid, fork=True)
            r, _ = call(letter, sid)
        else:
            rid, n1 = strip_fork(sid); ans, bsid = call(REF, rid)
            cid, n2 = strip_fork(sid); r, sid = call(letter, cid); stripped_total += n1 + n2
            assert sid == cid
        seen.add(letter); b = parse_board(r, L); board = b or board
        rows.append((letter, verbatim(ans), word5(ans), r.replace("\n", " / ")[:34]))
        rec["branches"].append({"turn": ti, "before_letter": letter, "reply": ans, "verbatim": verbatim(ans), "word5": word5(ans), "session_id": bsid})
        rec["turns"].append({"turn": ti, "letter": letter, "reply": r, "board": b, "board_after": list(board) if board else None, "session_id": sid})
        rec["thinking_entries_stripped"] = stripped_total
        print(f"[{ARM}-{INDEX}] before '{letter}': branch says verbatim={verbatim(ans)!r} word5={word5(ans)!r} | after guess: {r.replace(chr(10),' / ')[:34]}", flush=True)
        save()
        if board and "_" not in board:
            rec["stop_reason"] = "solved"
            print(f"[{ARM}-{INDEX}] board solved after '{letter}': {''.join(board)}; stopping", flush=True)
            break
    else:
        rec["stop_reason"] = rec["stop_reason"] or "letters_exhausted"
    if ARM == "stripped":
        cid, _ = strip_fork(sid); final, fsid = call("I give up. What was the word? Reply with just the word.", cid)
    else:
        final, fsid = call("I give up. What was the word? Reply with just the word.", sid)
    fv, fw = verbatim(final), word5(final); vs = [v for _, v, _, _ in rows]; ws = [w for _, _, w, _ in rows if w]
    rec.update({"final_reply": final, "final_verbatim": fv, "final_word5": fw, "final_session_id": fsid, "thinking_entries_stripped": stripped_total})
    print(f"[{ARM}-{INDEX}] FINAL verbatim={fv!r} word5={fw!r} | turns: {len(rows)} | branches verbatim: {vs} | branches word5: {ws} | distinct 5-letter incl. final: {sorted(set(ws) | ({fw} if fw else set()))} | files: {files()} | thinking entries stripped: {stripped_total} | cost ${cost:.2f}", flush=True)
except Exception as e:
    rec["error"] = traceback.format_exc()
    print(f"[{ARM}-{INDEX}] ERROR {e!r}", flush=True)
finally:
    save()
