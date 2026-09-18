#!/usr/bin/env python3
"""Run the commitment experiment: independent headless Claude Code processes, one per run.

Each run = one task x one arm x one repetition, executed as four sequential turns. Everything the
harness can observe is written to runs/raw/<run_id>/ (see METHODOLOGY.md for the layout).

Usage:
  python experiment/run_experiment.py --tasks all --arms all --reps 1 --concurrency 5
"""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, shutil, subprocess, sys, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tasks_lib import ROOT, ARMS, TURNS, list_tasks, load_task, load_detector, build_prompt

PY = "/private/tmp/acx-venv/bin/python"
VENV_BIN = "/private/tmp/acx-venv/bin"
WORK_BASE = "/private/tmp/acx-work"          # neutral path: the agent sees its cwd in its system prompt
RAW_BASE = os.environ.get("ACX_RAW_BASE", os.path.join(ROOT, "runs", "raw"))
HOOK = os.path.join(ROOT, "experiment", "hooks", "snapshot.sh")
MODEL = os.environ.get("ACX_MODEL", "claude-fable-5-1")
TURN_TIMEOUT = int(os.environ.get("ACX_TURN_TIMEOUT", "2400"))
MAX_TURNS = "200"
LOCK = threading.Lock()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def mangle(path: str) -> str:
    # Claude Code's project directory name for a cwd: every non-alphanumeric char becomes '-'
    import re
    return re.sub(r"[^A-Za-z0-9-]", "-", path)


def project_dir(cwd: str) -> str:
    return os.path.expanduser(os.path.join("~/.claude/projects", mangle(cwd)))


def write_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True, default=str)


def log(run_id, msg):
    line = f"{now()} [{run_id}] {msg}"
    with LOCK:
        print(line, flush=True)
        with open(os.path.join(RAW_BASE, "_log", "progress.log"), "a") as f:
            f.write(line + "\n")


def run_tests(task, workdir, run_dir, turn):
    """Run pristine copies of tests applicable at this turn, one pytest invocation per test file so
    results can be attributed per file. Returns summary dict."""
    import xml.etree.ElementTree as ET
    pristine = os.path.join(run_dir, "_pristine_tests")
    os.makedirs(pristine, exist_ok=True)
    os.makedirs(os.path.join(run_dir, "tests"), exist_ok=True)
    env = dict(os.environ, PYTHONPATH=workdir, PYTHONDONTWRITEBYTECODE="1")
    summary = {"turn": turn, "files": [], "per_file": {}, "total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "returncode": 0}
    stdout_all = []
    for t in range(1, turn + 1):
        src = task["tests"][t]
        name = os.path.basename(src)
        dst = os.path.join(pristine, name)
        shutil.copy(src, dst)
        summary["files"].append(name)
        xml = os.path.join(run_dir, "tests", f"t{turn}.{name}.junit.xml")
        try:
            r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", workdir, f"--junitxml={xml}", dst],
                               cwd=workdir, capture_output=True, text=True, timeout=600, env=env)
            stdout_all.append(f"=== {name} (rc={r.returncode}) ===\n{r.stdout}\n--- stderr ---\n{r.stderr}")
            summary["returncode"] = max(summary["returncode"], r.returncode)
            root = ET.parse(xml).getroot()
            suite = root if root.tag == "testsuite" else root.find("testsuite")
            total = int(suite.get("tests", 0)); fail = int(suite.get("failures", 0)); err = int(suite.get("errors", 0)); skip = int(suite.get("skipped", 0))
            # collection errors show up as errors with tests=1 or 0; treat any error as failing the file
            pf = {"total": total, "passed": total - fail - err - skip, "failed": fail, "errors": err, "skipped": skip}
        except Exception as e:
            stdout_all.append(f"=== {name} EXCEPTION {e!r}")
            pf = {"total": 0, "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "exception": repr(e)}
        summary["per_file"][name] = pf
        for k in ("total", "passed", "failed", "errors", "skipped"):
            summary[k] += pf[k]
    open(os.path.join(run_dir, "tests", f"t{turn}.stdout.txt"), "w").write("\n".join(stdout_all))
    # did the agent modify visible tests?
    modified = []
    for t in range(1, turn + 1):
        src = task["tests"][t]
        dst = os.path.join(workdir, "tests", os.path.basename(src))
        if not os.path.exists(dst):
            modified.append(os.path.basename(src) + " (missing)")
        elif open(src, "rb").read() != open(dst, "rb").read():
            modified.append(os.path.basename(src))
    summary["tests_modified"] = modified
    return summary


def snapshot_shadow(run_dir, workdir, label):
    """Commit the working tree into the shadow repo with a harness label (turn boundaries)."""
    shadow = os.path.join(run_dir, "shadow.git")
    if not os.path.isdir(shadow):
        sh(["git", "init", "-q", "--bare", shadow])
        sh(["git", "--git-dir", shadow, "config", "user.email", "acx@example.invalid"])
        sh(["git", "--git-dir", shadow, "config", "user.name", "acx-snapshot"])
    env = dict(os.environ, GIT_DIR=shadow, GIT_WORK_TREE=workdir)
    sh(["git", "add", "-A"], env=env)
    if sh(["git", "diff", "--cached", "--quiet"], env=env).returncode != 0:
        sh(["git", "commit", "-q", "-m", f"harness:{label} {now()}"], env=env)


def copy_memory(cwd, run_dir, turn, wipe):
    pd = project_dir(cwd)
    mem = os.path.join(pd, "memory")
    out = {"memory_dir": mem, "exists": os.path.isdir(mem), "files": []}
    if os.path.isdir(mem):
        for root, _, files in os.walk(mem):
            for f in files:
                p = os.path.join(root, f)
                rel = os.path.relpath(p, mem)
                out["files"].append(rel)
                dst = os.path.join(run_dir, "memory", f"after_t{turn}", rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy(p, dst)
        if wipe:
            shutil.rmtree(mem, ignore_errors=True)
            out["wiped"] = True
    return out


def claude_turn(run_id, run_dir, workdir, prompt, turn, resume_session):
    """Invoke one turn of the agent under test. Returns (result_event, session_id, exit info)."""
    prompt_path = os.path.join(run_dir, "prompts", f"t{turn}.md")
    os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
    open(prompt_path, "w", encoding="utf-8").write(prompt)
    settings = os.path.join(run_dir, "settings.json")
    if not os.path.exists(settings):
        write_json(settings, {"hooks": {"PostToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": HOOK}]}]}})
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--setting-sources", "",
           "--settings", settings, "--dangerously-skip-permissions", "--model", MODEL,
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--max-turns", MAX_TURNS]
    if resume_session:
        cmd += ["--resume", resume_session]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env.update(ACX_RUN_DIR=run_dir, ACX_WORK_DIR=workdir, ASDF_PYTHON_VERSION="3.12.12",
               PATH=VENV_BIN + ":" + env.get("PATH", ""), VIRTUAL_ENV="/private/tmp/acx-venv")
    stream_path = os.path.join(run_dir, "turns", f"t{turn}.stream.jsonl")
    err_path = os.path.join(run_dir, "turns", f"t{turn}.stderr.txt")
    os.makedirs(os.path.dirname(stream_path), exist_ok=True)
    started = now(); t0 = time.time()
    with open(stream_path, "w") as out, open(err_path, "w") as err:
        try:
            p = subprocess.run(cmd, cwd=workdir, stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env, timeout=TURN_TIMEOUT)
            rc, timed_out = p.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = -1, True
    info = {"turn": turn, "started": started, "ended": now(), "seconds": round(time.time() - t0, 1), "returncode": rc,
            "timed_out": timed_out, "command": cmd[:1] + ["<prompt>"] + cmd[3:], "resume_session": resume_session}
    result, session_id, init = None, None, None
    for line in open(stream_path, encoding="utf-8", errors="replace"):
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = ev; session_id = ev.get("session_id")
        if ev.get("type") == "result":
            result = ev; session_id = ev.get("session_id", session_id)
    info["session_id"] = session_id
    if result:
        write_json(os.path.join(run_dir, "turns", f"t{turn}.result.json"), result)
    if init:
        write_json(os.path.join(run_dir, "turns", f"t{turn}.init.json"), init)
    # copy the agent-visible transcript that Claude Code keeps for the session
    if session_id:
        for cand in glob.glob(os.path.join(project_dir(workdir), f"{session_id}.jsonl")):
            shutil.copy(cand, os.path.join(run_dir, "turns", f"t{turn}.transcript.jsonl"))
    return result, session_id, info


def do_run(task_id, arm, rep, force=False):
    run_id = f"{task_id}__{arm}__r{rep}"
    run_dir = os.path.join(RAW_BASE, run_id)
    if os.path.exists(os.path.join(run_dir, "meta.json")) and not force:
        m = json.load(open(os.path.join(run_dir, "meta.json")))
        if m.get("status") == "complete":
            log(run_id, "already complete; skipping"); return
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir)
    workdir = os.path.join(WORK_BASE, run_id)
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    task = load_task(task_id)
    shutil.copytree(task["starter"], workdir)
    sh(["git", "init", "-q"], cwd=workdir); sh(["git", "add", "-A"], cwd=workdir)
    sh(["git", "-c", "user.email=dev@example.invalid", "-c", "user.name=dev", "commit", "-q", "-m", "Initial commit: spec and tests"], cwd=workdir)
    pd = project_dir(workdir)
    if os.path.isdir(pd):
        shutil.rmtree(pd)
    meta = {"run_id": run_id, "task": task_id, "arm": arm, "rep": rep, "model": MODEL, "workdir": workdir,
            "started": now(), "status": "running", "claude_version": sh(["claude", "--version"]).stdout.strip(),
            "experiment_commit": sh(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip(),
            "python": sh([PY, "--version"]).stdout.strip(), "platform": sys.platform,
            "turn_timeout_s": TURN_TIMEOUT, "max_agent_turns_per_turn": int(MAX_TURNS),
            "context_mode": "continuous session (--resume)" if arm.startswith("ctx") else "fresh session per turn",
            "challenge": "irrelevant temptation" if arm.endswith("tempt") else "decision-relevant evidence",
            "turns": [], "detections": {}, "tests": {}, "memory": {}, "target_for_t3": None}
    write_json(os.path.join(run_dir, "meta.json"), meta)
    detect = load_detector(task_id)
    snapshot_shadow(run_dir, workdir, "starter")
    session = None
    try:
        for turn in TURNS:
            if turn >= 2:
                shutil.copy(task["tests"][turn], os.path.join(workdir, "tests", f"test_t{turn}.py"))
                snapshot_shadow(run_dir, workdir, f"tests_added_t{turn}")
            target = None
            if turn == 3:
                d2 = meta["detections"].get("2", {}).get("choice"); d1 = meta["detections"].get("1", {}).get("choice")
                target = d2 if d2 in ("A", "B") else (d1 if d1 in ("A", "B") else "A")
                meta["target_for_t3"] = target
                meta["target_fallback_used"] = d2 not in ("A", "B")
            prompt = build_prompt(task, turn, arm, target)
            log(run_id, f"turn {turn} start (target={target})")
            resume = session if arm.startswith("ctx") else None
            result, session, info = claude_turn(run_id, run_dir, workdir, prompt, turn, resume)
            if result:
                info["cost_usd"] = result.get("total_cost_usd"); info["num_agent_turns"] = result.get("num_turns")
                info["is_error"] = result.get("is_error"); info["subtype"] = result.get("subtype")
            meta["turns"].append(info)
            snapshot_shadow(run_dir, workdir, f"end_t{turn}")
            meta["tests"][str(turn)] = run_tests(task, workdir, run_dir, turn)
            det = detect(workdir, PY)
            meta["detections"][str(turn)] = det
            write_json(os.path.join(run_dir, "detect", f"t{turn}.json"), det)
            meta["memory"][str(turn)] = copy_memory(workdir, run_dir, turn, wipe=arm.startswith("fresh"))
            log(run_id, f"turn {turn} done in {info['seconds']}s rc={info['returncode']} choice={det.get('choice')} tests={meta['tests'][str(turn)].get('passed')}/{meta['tests'][str(turn)].get('total')}")
            write_json(os.path.join(run_dir, "meta.json"), meta)
            if info["timed_out"]:
                meta["status"] = "timed_out"; break
        else:
            meta["status"] = "complete"
    except Exception:
        meta["status"] = "error"; meta["error"] = traceback.format_exc()
        log(run_id, "ERROR " + meta["error"][-500:])
    # final artefacts
    final = os.path.join(run_dir, "repo_final")
    shutil.copytree(workdir, final, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    agent_git = sh(["git", "log", "--format=%H %aI %s", "--stat"], cwd=workdir).stdout
    open(os.path.join(run_dir, "agent_git_log.txt"), "w").write(agent_git)
    shadow = os.path.join(run_dir, "shadow.git")
    if os.path.isdir(shadow):
        sh(["git", "--git-dir", shadow, "bundle", "create", os.path.join(run_dir, "snapshots.bundle"), "--all"])
        export_snapshots(shadow, os.path.join(run_dir, "snapshots.jsonl"))
        shutil.rmtree(shadow)
    shutil.rmtree(os.path.join(run_dir, "_pristine_tests"), ignore_errors=True)
    meta["ended"] = now()
    meta["total_cost_usd"] = sum((t.get("cost_usd") or 0) for t in meta["turns"])
    write_json(os.path.join(run_dir, "meta.json"), meta)
    log(run_id, f"finished status={meta['status']} cost=${meta['total_cost_usd']:.2f}")


def export_snapshots(shadow, out_path):
    """Write every snapshot commit as a JSON line: seq, ts, label, files, unified diff vs parent."""
    r = sh(["git", "--git-dir", shadow, "log", "--reverse", "--format=%H%x1f%aI%x1f%s"])
    with open(out_path, "w") as out:
        for seq, line in enumerate(l for l in r.stdout.splitlines() if l):
            h, ts, subj = line.split("\x1f")
            parent = sh(["git", "--git-dir", shadow, "rev-parse", "--verify", "-q", h + "^"]).stdout.strip()
            if parent:
                diff = sh(["git", "--git-dir", shadow, "diff", "--no-color", parent, h]).stdout
                files = sh(["git", "--git-dir", shadow, "diff", "--name-status", parent, h]).stdout.splitlines()
            else:
                diff = sh(["git", "--git-dir", shadow, "show", "--no-color", "--format=", h]).stdout
                files = ["A\t" + f for f in sh(["git", "--git-dir", shadow, "ls-tree", "-r", "--name-only", h]).stdout.splitlines()]
            parts = subj.split(" ")
            rec = {"seq": seq, "commit": h, "ts": ts, "label": parts[0], "tool_use_id": parts[2] if len(parts) > 2 else None,
                   "files": [f.split("\t") for f in files], "diff": diff}
            out.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all"); ap.add_argument("--arms", default="all")
    ap.add_argument("--reps", type=int, default=1); ap.add_argument("--rep-start", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    tasks = list_tasks() if a.tasks == "all" else a.tasks.split(",")
    arms = ARMS if a.arms == "all" else a.arms.split(",")
    os.makedirs(os.path.join(RAW_BASE, "_log"), exist_ok=True)
    jobs = [(t, arm, r) for r in range(a.rep_start, a.rep_start + a.reps) for t in tasks for arm in arms]
    print(f"{len(jobs)} runs, concurrency {a.concurrency}, model {MODEL}")
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        list(ex.map(lambda j: do_run(*j, force=a.force), jobs))


if __name__ == "__main__":
    main()
