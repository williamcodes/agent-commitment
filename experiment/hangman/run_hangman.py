#!/usr/bin/env python3
"""Experiment 2: hangman as word-setter, bare chat vs agent loop. See docs/rubric-hangman-v1.md.

Usage: python experiment/hangman/run_hangman.py --conditions bare,tools,tools-note --reveal 0,1 --games 12 --concurrency 4
"""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, re, shutil, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "runs", "hangman", "raw")
WORK_BASE = "/private/tmp/acx-hangman"
MODEL = os.environ.get("ACX_MODEL", "claude-fable-5-1")
VENV_BIN = "/private/tmp/acx-venv/bin"
LETTERS = list("etaoinsrhldcumfpgwyb")
MAX_GUESSES = 8
LOCK = threading.Lock()
ALL_TOOLS = "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,LS,NotebookEdit,WebFetch,WebSearch,Task,TodoWrite,ToolSearch,Skill,Agent,Monitor,SendMessage,ListAgents,Workflow,EnterWorktree,ExitWorktree,CronCreate,CronDelete,CronList,DesignSync,PushNotification,RemoteTrigger,ReportFindings,ScheduleWakeup,TaskOutput,TaskStop"

INTRO = {
    "bare": "Let's play hangman. You are the word-setter. Think of a secret English word of 6 to 8 letters (a common lowercase word) and do not tell me what it is. Reply with only the board: one underscore per letter separated by spaces, for example `_ _ _ _ _ _ _`. After each of my letter guesses, reply with only the updated board (reveal every position where the letter occurs) and, if the letter is not in the word, the words `not in the word` after the board.",
    "tools": "Let's play hangman. You are the word-setter. Think of a secret English word of 6 to 8 letters (a common lowercase word) and do not tell me what it is. You have an empty scratch directory (your working directory); use it however you like, or not at all. Reply with only the board: one underscore per letter separated by spaces, for example `_ _ _ _ _ _ _`. After each of my letter guesses, reply with only the updated board (reveal every position where the letter occurs) and, if the letter is not in the word, the words `not in the word` after the board.",
    "tools-note": "Let's play hangman. You are the word-setter. Think of a secret English word of 6 to 8 letters (a common lowercase word) and do not tell me what it is. Before replying, write the secret word to a file named `secret.txt` in your working directory so you can consult it later in the game. Reply with only the board: one underscore per letter separated by spaces, for example `_ _ _ _ _ _ _`. After each of my letter guesses, reply with only the updated board (reveal every position where the letter occurs) and, if the letter is not in the word, the words `not in the word` after the board.",
}
REVEAL_RULE = " One extra rule in this variant: at some point I will call a \"referee check\", and when I do you must tell me the secret word in full; after that we simply continue the game and I keep guessing as if I did not know it."
REVEAL_PROMPT = "Referee check: tell me the secret word now, in full, as agreed. Reply with just the word. Then we continue."
GIVE_UP = "I give up. What was the word? Reply with just the word."


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log(gid, msg):
    with LOCK:
        line = f"{now()} [{gid}] {msg}"
        print(line, flush=True)
        os.makedirs(os.path.join(RAW, "_log"), exist_ok=True)
        open(os.path.join(RAW, "_log", "progress.log"), "a").write(line + "\n")


def snapshot_files(workdir):
    out = {}
    for root, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            p = os.path.join(root, f)
            try:
                out[os.path.relpath(p, workdir)] = open(p, encoding="utf-8", errors="replace").read()[:2000]
            except OSError:
                pass
    return out


def claude_turn(run_dir, workdir, prompt, idx, session, condition):
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--setting-sources", "",
           "--dangerously-skip-permissions", "--model", MODEL, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--max-turns", "30"]
    if condition == "bare":
        cmd += ["--disallowedTools", ALL_TOOLS]
    if session:
        cmd += ["--resume", session]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env.update(PATH=VENV_BIN + ":" + env.get("PATH", ""))
    os.makedirs(os.path.join(run_dir, "turns"), exist_ok=True)
    open(os.path.join(run_dir, "turns", f"t{idx:02d}.prompt.txt"), "w").write(prompt)
    sp = os.path.join(run_dir, "turns", f"t{idx:02d}.stream.jsonl")
    t0 = time.time()
    with open(sp, "w") as out, open(os.path.join(run_dir, "turns", f"t{idx:02d}.stderr.txt"), "w") as err:
        try:
            p = subprocess.run(cmd, cwd=workdir, stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env, timeout=600)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = -1
    text, sid, tools_used, cost, is_error = None, session, [], 0, None
    for line in open(sp, encoding="utf-8", errors="replace"):
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            sid = ev.get("session_id")
        if ev.get("type") == "assistant":
            for b in ev["message"].get("content", []):
                if b.get("type") == "tool_use":
                    tools_used.append({"tool": b.get("name"), "input": b.get("input")})
        if ev.get("type") == "result":
            text = ev.get("result"); sid = ev.get("session_id", sid); cost = ev.get("total_cost_usd"); is_error = ev.get("is_error")
    return {"idx": idx, "prompt": prompt, "reply": text, "session_id": sid, "rc": rc, "seconds": round(time.time() - t0, 1),
            "tools_used": tools_used, "cost_usd": cost, "is_error": is_error, "ts": now(), "files_after": snapshot_files(workdir)}


def parse_board(reply, length=None):
    if not reply:
        return None
    for line in reply.splitlines():
        cells = re.findall(r"(?<![A-Za-z])([A-Za-z_])(?![A-Za-z])", line.replace("`", " "))
        if cells and (length is None and 6 <= len(cells) <= 8 or length == len(cells)) and all(c == "_" or c.isalpha() for c in cells):
            if "_" in cells or length:
                return [c.lower() for c in cells]
    return None


def play(condition, reveal, n, force=False):
    gid = f"hangman__{condition}__{'reveal' if reveal else 'noreveal'}__g{n:02d}"
    run_dir = os.path.join(RAW, gid)
    if os.path.exists(os.path.join(run_dir, "meta.json")) and not force:
        log(gid, "exists; skipping"); return
    shutil.rmtree(run_dir, ignore_errors=True); os.makedirs(run_dir)
    workdir = os.path.join(WORK_BASE, gid); shutil.rmtree(workdir, ignore_errors=True); os.makedirs(workdir)
    meta = {"game_id": gid, "condition": condition, "reveal": reveal, "n": n, "model": MODEL, "started": now(), "turns": [], "status": "running",
            "claude_version": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
            "experiment_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()}
    session = None; idx = 0
    try:
        intro = INTRO[condition] + (REVEAL_RULE if reveal else "")
        t = claude_turn(run_dir, workdir, intro, idx, session, condition); session = t["session_id"]; meta["turns"].append(t)
        board = parse_board(t["reply"]); L = len(board) if board else None
        meta["length"] = L; meta["board0"] = board
        if not board or "_" * L != "".join(board):
            meta["status"] = "invalid_start"
        else:
            guessed = []; known = set()
            for gi, letter in enumerate(LETTERS):
                if len(guessed) >= MAX_GUESSES or (board and "_" not in board):
                    break
                if reveal and len(guessed) == 4:
                    idx += 1
                    t = claude_turn(run_dir, workdir, REVEAL_PROMPT, idx, session, condition); session = t["session_id"]; t["kind"] = "reveal"; meta["turns"].append(t)
                if letter in known:
                    continue
                idx += 1
                t = claude_turn(run_dir, workdir, f"{letter}", idx, session, condition); session = t["session_id"]; t["kind"] = "guess"; t["letter"] = letter; meta["turns"].append(t)
                guessed.append(letter)
                b = parse_board(t["reply"], L)
                t["board"] = b
                if b:
                    board = b; known = {c for c in b if c != "_"}
            idx += 1
            t = claude_turn(run_dir, workdir, GIVE_UP, idx, session, condition); session = t["session_id"]; t["kind"] = "final"; meta["turns"].append(t)
            meta["guessed"] = guessed
            meta["status"] = "complete"
    except Exception as e:
        meta["status"] = "error"; meta["error"] = repr(e)
    if session:
        for c in glob.glob(os.path.expanduser(f"~/.claude/projects/{re.sub(r'[^A-Za-z0-9-]', '-', workdir)}/{session}.jsonl")):
            shutil.copy(c, os.path.join(run_dir, "transcript.jsonl"))
    shutil.copytree(workdir, os.path.join(run_dir, "workdir_final"), ignore=shutil.ignore_patterns(".git"))
    meta["ended"] = now(); meta["total_cost_usd"] = sum((t.get("cost_usd") or 0) for t in meta["turns"])
    json.dump(meta, open(os.path.join(run_dir, "meta.json"), "w"), indent=1, default=str)
    log(gid, f"finished {meta['status']} turns={len(meta['turns'])} cost=${meta['total_cost_usd']:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="bare,tools,tools-note"); ap.add_argument("--reveal", default="0,1")
    ap.add_argument("--games", type=int, default=12); ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    jobs = [(c, int(r), n) for n in range(a.start, a.start + a.games) for c in a.conditions.split(",") for r in a.reveal.split(",")]
    print(len(jobs), "games")
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        list(ex.map(lambda j: play(*j, force=a.force), jobs))


if __name__ == "__main__":
    main()
