"""Loading of task definitions."""
from __future__ import annotations
import importlib.util, os, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(ROOT, "tasks")
ARMS = ["ctx-tempt", "ctx-evidence", "fresh-tempt", "fresh-evidence"]
TURNS = [1, 2, 3, 4]

FRESH_PREFIX = ("You are picking up work on an existing Python project in this directory. Earlier work "
                "was done in previous sessions that you have no memory of, so read SPEC.md and the code "
                "first. ")


def list_tasks() -> list[str]:
    return sorted(d for d in os.listdir(TASKS_DIR)
                  if os.path.isdir(os.path.join(TASKS_DIR, d)) and not d.startswith("_"))


def load_task(task_id: str) -> dict:
    d = os.path.join(TASKS_DIR, task_id)
    meta = yaml.safe_load(open(os.path.join(d, "task.yaml")))
    turns = {}
    for f in os.listdir(os.path.join(d, "turns")):
        turns[f[:-3]] = open(os.path.join(d, "turns", f), encoding="utf-8").read().strip()
    meta["turns"] = turns
    meta["dir"] = d
    meta["starter"] = os.path.join(d, "starter")
    meta["tests"] = {1: os.path.join(d, "starter", "tests", "test_t1.py")}
    for t in (2, 3, 4):
        meta["tests"][t] = os.path.join(d, "tests", f"test_t{t}.py")
    return meta


def load_detector(task_id: str):
    p = os.path.join(TASKS_DIR, task_id, "detect.py")
    spec = importlib.util.spec_from_file_location(f"detect_{task_id}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.detect


def build_prompt(task: dict, turn: int, arm: str, target: str | None) -> str:
    """target: the approach detected so far ('A' or 'B'); the T3 arm-specific text is chosen so the
    nudge/evidence pushes against the detected approach."""
    t = task["turns"]
    if turn == 1:
        body = t["t1"]
    elif turn == 2:
        body = t["t2"]
    elif turn == 3:
        kind = "tempt" if arm.endswith("tempt") else "evidence"
        body = t["t3_common"] + "\n\n" + t[f"t3_{kind}_{target}"]
    else:
        body = t["t4"]
    if arm.startswith("fresh"):
        body = FRESH_PREFIX + body
    return body
