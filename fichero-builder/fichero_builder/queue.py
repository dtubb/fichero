"""`builder queue [add|run]`: the owner-side loop that works a queue of briefs with no manager in the loop
(dev-workflows.tool.queue, Step 2.6; the frozen runner's #6166 ported).

One row per item in `<state>/queue.json` (id, brief, worktree, base, depends_on, issues, state, head, why). The loop
starts the next queued item whose `depends_on` is satisfied (a sha on origin/<branch>, or a queue item that has landed),
at most `[queue].workers` at a time, each as one `builder work` process (run -> rebase -> patches -> check -> review ->
land gate; the ladder is one at a time across items by the `ladder` lock in `builder work`); exit 0 -> `builder landed`
(push only with --push) -> landed; exit 2 (a QUESTION line) -> `question`, the line in `<state>/question-<id>.txt` for a
person; any other end -> `blocked` with the output tail. Every transition is a journal row (event `queue`); `builder watch`
shows the table. The process control is a small object so the tests run against fakes."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fichero_builder import journal

STATES = ("queued", "running", "landing", "landed", "blocked", "question")


def path() -> Path:
    return journal.STATE / "queue.json"


def load() -> list[dict]:
    p = path()
    return json.loads(p.read_text())["items"] if p.is_file() else []


def save(items: list[dict]) -> None:
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps({"items": items}, indent=1))


def workers(root) -> int:
    f = Path(root) / "harness.toml"
    return int(tomllib.loads(f.read_text()).get("queue", {}).get("workers", 1)) if f.is_file() else 1


def add(id: str, brief: str, worktree: str, issues: list[int], base: str = "", depends_on: list[str] | None = None) -> dict:
    """One queued row; an id already queued or running is refused (a landed, blocked or questioned one is replaced)."""
    with journal.Lock("queue"):
        items = load()
        old = next((i for i in items if i["id"] == id), None)
        if old and old["state"] in ("queued", "running", "landing"):
            raise ValueError(f"{id} is already {old['state']}")
        row = {"id": id, "brief": str(brief), "worktree": str(worktree), "base": base, "depends_on": list(depends_on or []),
               "issues": list(issues), "state": "queued", "head": "", "why": ""}
        items = [i for i in items if i["id"] != id] + [row]
        save(items)
    journal.append("queue", id=id, state="queued", detail=f"depends on {', '.join(row['depends_on']) or 'nothing'}")
    return row


@dataclass
class Procs:
    """What the loop does to the world; the tests replace each one."""
    start: Callable[[dict, str], object]            # (item, base sha) -> a handle
    poll: Callable[[object], tuple | None]          # handle -> (rc, output) once ended, None while running
    landed: Callable[[dict, bool], tuple]           # (item, push) -> (rc, output); the verdict store is the item's own
    origin_head: Callable[[], str]                  # the current origin/<branch> sha (after a fetch)
    on_origin: Callable[[str], bool]                # sha -> is an ancestor of origin/<branch>
    head_of: Callable[[dict], str]                  # item -> the sha `builder work` fetched for it (its fetch row)
    sleep: Callable[[float], None] = time.sleep


def landed_argv(root, item: dict, push: bool) -> list[str]:
    """`builder landed` for a queue item: the verdict store `builder work` wrote for it (`verdicts-<id>.json`)."""
    return [sys.executable, "-m", "fichero_builder", "landed", item["head"], "--root", str(root), "--state", str(journal.STATE),
            "--verdicts", str(journal.STATE / f"verdicts-{item['id']}.json")] + (["--push"] if push else [])


def real_procs(root, repo: str, branch: str) -> Procs:
    py, pkg = sys.executable, Path(__file__).resolve().parents[1]

    def git(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)

    def start(item, base):
        log = (journal.STATE / f"queue-{item['id']}.log").open("w")
        argv = [py, "-m", "fichero_builder", "work", "--brief", item["brief"], "--worktree", item["worktree"], "--name", item["id"],
                "--issues", *map(str, item["issues"]), "--root", str(root), "--state", str(journal.STATE)] + (["--base", base] if base else [])
        return subprocess.Popen(argv, cwd=str(pkg), stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONPATH": str(pkg)})

    def poll(p):
        rc = p.poll()
        if rc is None:
            return None
        p.stdout.close()
        return rc, (journal.STATE / f"queue-{p.args[p.args.index('--name') + 1]}.log").read_text()[-2000:]

    def landed(item, do_push):
        r = subprocess.run(landed_argv(root, item, do_push), cwd=str(pkg), capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(pkg)})
        return r.returncode, (r.stdout + r.stderr)[-2000:]

    def origin_head():
        git("fetch", "-q", "origin")
        return git("rev-parse", f"refs/remotes/origin/{branch}").stdout.strip()

    def head_of(item):
        return next((r["detail"] for r in reversed(journal.read()) if r.get("event") == "work" and r.get("name") == item["id"]
                     and r.get("step") == "fetch" and r.get("ok")), "")

    return Procs(start=start, poll=poll, landed=landed, origin_head=origin_head,
                 on_origin=lambda sha: git("merge-base", "--is-ancestor", sha, f"refs/remotes/origin/{branch}").returncode == 0, head_of=head_of)


def satisfied(dep: str, items: list[dict], on_origin) -> bool:
    """A dependency is a queue item id (landed) or a sha (on origin/<branch>)."""
    row = next((i for i in items if i["id"] == dep), None)
    return row["state"] == "landed" if row else on_origin(dep)


def tick(procs: Procs, handles: dict, *, workers_n: int, push: bool, out=print) -> bool:
    """One pass: ended processes move on, free slots start the next satisfied item. False when nothing is left to do."""
    with journal.Lock("queue"):
        items = load()
    by_id = {i["id"]: i for i in items}

    def move(item, state, detail=""):
        item["state"], item["why"] = state, detail[-300:]
        journal.append("queue", id=item["id"], state=state, detail=detail[-300:])
        out(f"{item['id']}: {state}" + (f" ({detail.strip().splitlines()[-1][:120]})" if detail.strip() else ""))

    for id_, h in list(handles.items()):
        item = by_id[id_]
        ended = procs.poll(h)
        if ended is None:
            continue
        del handles[id_]
        rc, output = ended
        if rc == 0:
            item["head"] = procs.head_of(item)
            move(item, "landing", item["head"])
            lrc, lout = procs.landed(item, push)
            move(item, "landed" if lrc == 0 else "blocked", lout if lrc else f"landed {item['head'][:9]}" + (" (pushed)" if push else " (not pushed)"))
        elif rc == 2:
            q = next((ln for ln in output.splitlines() if ln.startswith("QUESTION:")), "QUESTION: (the work process printed none)")
            (journal.STATE / f"question-{id_}.txt").write_text(q + "\n")
            move(item, "question", q)
        else:
            move(item, "blocked", f"work exited {rc}: {output}")
    base = ""
    for item in items:
        if len(handles) >= workers_n:
            break
        if item["state"] == "queued" and all(satisfied(d, items, procs.on_origin) for d in item["depends_on"]):
            base = base or procs.origin_head()
            handles[item["id"]] = procs.start(item, base)
            move(item, "running", f"base {base[:9]}")
    with journal.Lock("queue"):
        save(items)
    return any(i["state"] in ("queued", "running") for i in items)


def run(procs: Procs, *, workers_n: int, push: bool, tick_s: float = 30.0, once: bool = False, out=print) -> int:
    handles: dict = {}
    while tick(procs, handles, workers_n=workers_n, push=push, out=out):
        if once:
            break
        procs.sleep(tick_s)
    return 0


def table() -> list[list]:
    return [[i["id"], i["state"], ", ".join(f"#{n}" for n in i["issues"]), ", ".join(i["depends_on"]) or "-", i["head"][:9] or "-", i["why"]]
            for i in load()]


def main(a) -> int:
    if a.action == "add":
        try:
            add(a.id, a.brief, a.worktree, a.issues, base=a.base or "", depends_on=a.depends_on)
        except ValueError as e:
            print(f"REFUSED: {e}")
            return 1
        print(f"queued {a.id}")
        return 0
    if a.action == "run":
        rules = tomllib.loads((Path(a.root) / "harness.toml").read_text())
        repo = rules.get("check", {}).get("engine_repo", "")
        if not repo:
            print("REFUSED: no [check].engine_repo in the rules file")
            return 1
        return run(real_procs(a.root, repo, rules["land"]["branch"]), workers_n=workers(a.root), push=a.push, tick_s=a.tick, once=a.once)
    for row in table():
        print("\t".join(shlex.quote(x) if " " in x else x for x in row))
    return 0
