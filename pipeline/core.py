"""The state machine and the one set of functions the CLI, the MCP server and the page call (`API`).
States: queued → coding → checked → reviewed → candidate → gated → pushed → closed, plus failed, needs-maintainer,
rate-limited, waiting, paused. An item moves only through the transitions here, each running its own check and
writing one journal line; a model's report never moves an item (pipeline.one-state-machine)."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path

from pipeline import ROOT, STATE, budget, checks, coder, config, gh, journal

STATES = ("queued", "coding", "checked", "reviewed", "candidate", "gated", "pushed", "closed",
          "failed", "needs-maintainer", "rate-limited", "waiting", "paused")
CFG: dict = {}
ISSUE = gh.issue  # the one read of an issue; tests replace it
DRY_RUN = True    # GitHub writes: the CLI flips this with --apply; tests and the proof run never do


def cfg() -> dict:
    global CFG
    if not CFG:
        CFG = config.load()
    return CFG


# --- state = the journal replayed -------------------------------------------------------------------------------

def state() -> dict:
    s = {"items": {}, "tasks": {}, "queue": {}, "point": None, "paused": False, "workers": {}, "machine": None}
    for e in journal.read():
        ev, it = e["event"], s["items"].get(str(e.get("issue")))
        if ev == "item":
            s["items"][str(e["issue"])] = {"issue": e["issue"], "task": e["task"], "title": e.get("title", ""), "state": "queued",
                                           "attempts": 0, "checks": [], "verdicts": [], "cost_usd": 0.0, "history": [], "sha": ""}
            s["tasks"].setdefault(e["task"], {"issues": [], "window": e.get("window"), "worktree": e.get("worktree")})
            s["tasks"][e["task"]]["issues"].append(e["issue"])
        elif ev == "transition" and it:
            it["state"] = e["to"]
            it["history"].append(f"{e['ts']} {e['to']}: {e.get('why', '')}")
        elif ev == "check" and it:
            it["checks"] = e["results"]
            it["sha"] = e["sha"]
            if not e["ok"]:
                it["attempts"] += 1
        elif ev == "verdict" and it:
            it["verdicts"].append({k: e[k] for k in ("sha", "verdict", "by", "findings")})
        elif ev == "cost" and it:
            it["cost_usd"] = e["usd"]
            it["tokens"], it["model"] = e["tokens"], e["model"]
        elif ev == "queue":
            s["queue"][e["id"]] = {k: e.get(k) for k in ("id", "kind", "text", "options", "task", "window", "ts")}
        elif ev == "answer":
            s["queue"].pop(e["id"], None)
        elif ev == "point":
            s["point"] = e["milestone"]
        elif ev in ("pause", "resume"):
            s["paused"] = ev == "pause"
        elif ev == "worker":
            s["workers"][e["window"]] = {k: e.get(k) for k in ("window", "task", "model", "session_dir", "cwd", "role")}
        elif ev in ("report", "tell", "ask", "done_requested", "wait") and e.get("task") in s["tasks"]:
            s["tasks"][e["task"]].setdefault("messages", []).append(f"{e['ts']} {ev}: {e.get('text', '')[:200]}")
    for w in s["workers"].values():
        st = coder.status(Path(w["session_dir"])) if w.get("session_dir") else {}
        w.update(idle=st.get("idle"), cost_usd=round(st.get("cost_usd", 0.0), 3), last_text=(st.get("last_text") or "")[-300:])
    s["stuck"] = [i for i, it in s["items"].items() if _stuck(it)]
    return s


def _stuck(it: dict) -> bool:
    if it["state"] not in ("coding", "checked") or not it["history"]:
        return False
    last = time.mktime(time.strptime(it["history"][-1][:19], "%Y-%m-%dT%H:%M:%S"))
    return time.time() - last > cfg()["workers"]["stuck_minutes"] * 60


def status() -> dict:
    s = state()
    s["machine"] = budget.machine()
    return s


def _move(issue: int, to: str, why: str = "") -> None:
    assert to in STATES, to
    journal.append("transition", issue=issue, to=to, why=why)


def _queue(kind: str, text: str, options=None, task=None, window=None) -> str:
    qid = uuid.uuid4().hex[:8]
    journal.append("queue", id=qid, kind=kind, text=text, options=options or [], task=task, window=window)
    return qid


def _require_running() -> None:
    if state()["paused"]:
        raise RuntimeError("paused: `python -m pipeline resume` first (pipeline.pause-all)")


# --- the brief the coder gets -----------------------------------------------------------------------------------

BEHAVIOUR_ID = re.compile(r"`([a-z][a-z0-9-]*\.[a-z0-9.-]+)`")


def spec_lines(ids: set[str]) -> list[str]:
    out, specs = [], Path(cfg()["repo"]["path"]) / cfg()["repo"]["specs"]
    for p in specs.rglob("*.md") if ids else []:
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if any(f"`{i}`" in line for i in ids):
                out.append(f"{p.relative_to(cfg()['repo']['path'])}:{n}: {line.strip()}")
    return out


def brief(issue: dict, task: str, failure: str = "") -> str:
    """The coder's prompt: the issue (only text by allow-listed authors), its spec lines, the rules. Outside text
    never enters a prompt (pipeline.outside-bugs)."""
    g = cfg()["github"]
    if issue.get("author") not in g["allowed_authors"]:
        raise PermissionError(f"#{issue['number']} is by {issue.get('author')}: not allow-listed, triage it first")
    body = issue.get("body") or ""
    lines = spec_lines(set(BEHAVIOUR_ID.findall(body)))
    text = [f"# Issue #{issue['number']}: {issue['title']}", "", body, ""]
    if lines:
        text += ["## Spec lines", *lines, ""]
    if failure:
        text += ["## The checks FAILED on your last commit. Fix this, then commit again:", "```", failure[-4000:], "```", ""]
    text += ["## How to work",
             "1. Start with jcodemunch `plan_turn` for this task, and jdocmunch for the spec lines and docs. Read before you write.",
             "2. Ponytail: the shortest correct diff; no new abstractions; a `ponytail:` comment on each known ceiling.",
             "3. Write the test first from the spec's words and see it fail; then make it pass. Run only your own tests.",
             f"4. Do not touch {', '.join(cfg()['repo']['check_paths'])}: those are the checks you are judged by.",
             f"5. Commit your own work, once for this issue: `git commit --author='Claude <{g['agent_email']}>' -m '<what> ({'Part of' if issue.get('part_of') else 'Fixes'} #{issue['number']})' -m '{g['commit_trailer']}'`. Uncommitted work counts as nothing.",
             f"6. When committed, call the `done` tool with task `{task}`. Use `ask` for a question (the maintainer answers), `report` for progress.",
             "7. Work only in this directory. Do not run the app or the engine; tests use the scratch paths the runner sets."]
    return "\n".join(text)


# --- transitions --------------------------------------------------------------------------------------------------

def _worktree(task: str) -> Path:
    c = cfg()
    wt = Path(c["repo"]["path"]) / c["repo"]["worktrees"] / task
    if not wt.exists():
        journal.append("intent", task=task, what="worktree", path=str(wt))
        subprocess.run(["git", "fetch", "-q", c["repo"]["base"].split("/")[0]], cwd=c["repo"]["path"], check=False)
        checks.git(c["repo"]["path"], "worktree", "add", "-q", "-b", f"pipeline/{task}", str(wt), c["repo"]["base"])
        subprocess.run(["git", "config", "extensions.worktreeConfig", "true"], cwd=wt, check=False, capture_output=True)
        for k, v in (("user.name", "Claude"), ("user.email", c["github"]["agent_email"])):
            subprocess.run(["git", "config", "--worktree", k, v], cwd=wt, check=False, capture_output=True)
        journal.append("done", task=task, what="worktree", path=str(wt))
    return wt


def _wait_room(kind: str, task: str) -> None:
    for _ in range(240):
        ok, why = budget.room_for(kind, cfg()["workers"]["needs_mb"])
        if ok:
            return
        journal.append("wait", task=task, text=why)
        time.sleep(30)
    raise RuntimeError(f"no room for {kind} after two hours")


def _start_worker(task: str, wt: Path, worker: dict, window: str) -> Path:
    c = cfg()
    session_dir = STATE / "sessions" / task / f"{worker['provider']}-{worker['model'].replace('/', '_')}"
    session_dir.mkdir(parents=True, exist_ok=True)
    env = coder.allowed_env(c)
    env.update(PIPELINE_ROOT=str(ROOT), PIPELINE_STATE=str(STATE), PIPELINE_TASK=task, PIPELINE_ROLE="coder",
               PIPELINE_PYTHON=sys.executable)
    journal.append("intent", task=task, what="worker", window=window)
    coder.start_window(c, window, wt, coder.pi_command(c, worker, session_dir), env)
    journal.append("worker", window=window, task=task, role="coder", model=config.pi_model_id(worker),
                   session_dir=str(session_dir), cwd=str(wt))
    journal.append("done", task=task, what="worker", window=window)
    return session_dir


def start(issues: list[int], milestone: str | None = None, task: str | None = None, worker_index: int = 0,
          from_file: str | None = None) -> dict:
    """queued → coding → (checks) for a batch of issues in one coder context; blocks until the batch is done.
    `from_file`: a local JSON issue (number, title, body, author, part_of) for a step not yet filed on GitHub."""
    _require_running()
    c = cfg()
    read_issue = ISSUE if not from_file else (lambda n: json.loads(Path(from_file).read_text()))
    task = task or f"{(milestone or 'issues').replace(' ', '-').lower()}-{issues[0]}"
    s = state()
    live = [w for w in s["workers"].values() if not w.get("idle") and w.get("task") != task]
    if len(live) >= c["workers"]["caps"]["coders"]:
        raise RuntimeError(f"coder cap {c['workers']['caps']['coders']}: {', '.join(w['window'] for w in live)} running")
    briefs = {}
    for n in issues:  # every issue is read and allow-listed before anything starts
        if str(n) in s["items"] and s["items"][str(n)]["state"] not in ("queued", "coding", "failed"):
            continue  # finished or under review: never redone (pipeline.resume-from-journal)
        briefs[n] = read_issue(n)
        if briefs[n].get("author") not in c["github"]["allowed_authors"]:
            _queue("triage", f"#{n} by {briefs[n].get('author')}: outside text, rewrite it into a triaged issue", task=task)
            raise PermissionError(f"#{n} is by {briefs[n].get('author')}: not allow-listed (pipeline.outside-bugs)")
    if not briefs:
        return {"task": task, "done": "nothing left to do"}
    wt = _worktree(task)
    window = f"coder-{task}"
    for n, iss in briefs.items():
        if str(n) not in s["items"]:
            journal.append("item", issue=n, task=task, title=iss["title"], window=window, worktree=str(wt))
    workers = c["roles"]["coder"]
    worker = workers[worker_index]
    _wait_room(worker["kind"], task)
    session_dir = _start_worker(task, wt, worker, window)
    summary = {"task": task, "window": window, "worktree": str(wt), "items": {}}
    for n, iss in briefs.items():
        summary["items"][n] = _run_issue(task, n, iss, wt, window, session_dir, worker, worker_index)
        if summary["items"][n] in ("rate-limited",):
            break  # the fallback list: the next worker takes the rest of the batch in a fresh context
    return summary


def _run_issue(task, n, iss, wt, window, session_dir, worker, worker_index) -> str:
    c = cfg()
    since = checks.git(wt, "rev-parse", "HEAD")
    journal.append("since", issue=n, sha=since)
    failure = ""
    for attempt in range(c["workers"]["retries"] + 1):
        _move(n, "coding", f"{worker['provider']}/{worker['model']}, attempt {attempt + 1}")
        path = coder.brief_file(task, f"issue-{n}-attempt-{attempt + 1}", brief(iss, task, failure))
        tell(window, f"Read and do {path} — issue #{n}. Call the `done` tool with task {task} when your commit is in.", task=task)
        st = coder.wait_idle(session_dir, c["workers"]["cost_cap_usd"], note=lambda s: None)
        st = _wait_answers(task, session_dir, st)
        journal.append("cost", issue=n, usd=round(st["cost_usd"], 4), tokens=st["tokens"], model=st["model"],
                       tools=dict(st["tool_calls"]))
        if st.get("rate_limited") or "cost cap" in st.get("stopped", ""):
            _move(n, "rate-limited", st.get("stopped") or "quota or credit failure")
            if worker_index + 1 < len(c["roles"]["coder"]):
                _queue("fallback", f"#{n}: {worker['model']} stopped ({st.get('stopped') or 'rate limited'}); next worker takes over", task=task)
            else:
                _queue("budget", f"#{n}: every worker in the fallback list stopped; more budget?", task=task)
            return "rate-limited"
        if st.get("stopped"):
            _move(n, "failed", st["stopped"])
            return "failed"
        results = check(n, since=since)
        if all(r["ok"] for r in results):
            return "checked"
        failure = "\n\n".join(f"[{r['name']}] {r['text']}" for r in results if not r["ok"])
        if results and results[0]["name"] == "pinned-checks":
            break
    _move(n, "needs-maintainer", failure[-500:])
    _queue("failed-checks", f"#{n} failed its checks {c['workers']['retries'] + 1} times:\n{failure[-1500:]}", task=task, window=window)
    return "needs-maintainer"


def _wait_answers(task: str, session_dir: Path, st: dict) -> dict:
    """An idle worker that asked a question waits for the maintainer's answer, then for its next idle turn."""
    while any(q["task"] == task and q["kind"] == "ask" for q in state()["queue"].values()):
        time.sleep(15)
        st = coder.wait_idle(session_dir, cfg()["workers"]["cost_cap_usd"], note=lambda s: None)
    return st


def check(issue: int, since: str | None = None) -> list[dict]:
    """coding → checked only when every rung is green; red: retry (the caller) or needs-maintainer."""
    s = state()
    it = s["items"].get(str(issue))
    if not it:
        raise KeyError(f"#{issue} is not an item")
    t = s["tasks"][it["task"]]
    wt = Path(t["worktree"])
    since = since or next((e["sha"] for e in reversed(journal.read()) if e["event"] == "since" and e["issue"] == issue), None)
    _wait_room("pytest", it["task"])
    with journal.Lock("test-run"):
        results = checks.run_all(wt, cfg(), since=since)
    sha = checks.git(wt, "rev-parse", "HEAD")
    ok = bool(results) and all(r["ok"] for r in results)
    journal.append("check", issue=issue, ok=ok, sha=sha, results=results)
    gh.cache_clear()
    if ok:
        _move(issue, "checked", f"{len(results)} rungs green at {sha[:9]}")
    elif results and results[0]["name"] == "pinned-checks":
        _move(issue, "needs-maintainer", results[0]["text"])
    return results


def verdict(issue: int, sha: str, verdict: str, by: str = "reviewer", findings: str = "") -> dict:
    """checked → reviewed on READY from the reviewer role for the current head sha; anything else is recorded only."""
    it = state()["items"].get(str(issue))
    if not it:
        raise KeyError(f"#{issue} is not an item")
    journal.append("verdict", issue=issue, sha=sha, verdict=verdict, by=by, findings=findings[:4000])
    if verdict == "READY" and by == "reviewer" and it["state"] == "checked" and sha == it["sha"]:
        _move(issue, "reviewed", f"READY by {by} at {sha[:9]}")
        return {"issue": issue, "state": "reviewed"}
    return {"issue": issue, "state": it["state"], "recorded": verdict,
            "note": "" if sha == it["sha"] else f"verdict is for {sha[:9]}, head is {it['sha'][:9]}: not binding"}


def _not_built(name):
    def f(*a, **k):
        raise NotImplementedError(f"{name}: Stage 3 (nightly gate, push) is not built; nothing moves past reviewed")
    return f


candidate, gate, push = _not_built("candidate"), _not_built("gate"), _not_built("push")


# --- messages, queue, pointing ----------------------------------------------------------------------------------

def tell(window: str, text: str, task: str | None = None) -> dict:
    _require_running()
    journal.append("intent", task=task or window, what="tell", text=text[:300])
    coder.tell(cfg(), window, text)
    journal.append("tell", task=task, window=window, text=text[:300])
    journal.append("done", task=task or window, what="tell", text=text[:300])
    return {"window": window, "sent": text[:120]}


def report(task: str, text: str) -> dict:
    journal.append("report", task=task, text=text[:2000])
    return {"ok": True}


def ask(task: str, question: str, options: list[str] | None = None) -> dict:
    s = state()
    window = next((w for w, v in s["workers"].items() if v["task"] == task), None)
    qid = _queue("ask", question, options, task=task, window=window)
    return {"queued": qid, "note": "the maintainer's answer will be told to your window; carry on with what you can"}


def done(task: str) -> dict:
    """Only REQUESTS the check transition: the runner runs the checks when the worker's turn ends."""
    journal.append("done_requested", task=task, text="")
    return {"ok": True, "note": "the runner runs the checks; nothing moves on your word"}


def queue() -> list[dict]:
    return sorted(state()["queue"].values(), key=lambda q: q["ts"] or "")


def answer(qid: str, text: str) -> dict:
    q = state()["queue"].get(qid)
    if not q:
        raise KeyError(f"no open queue item {qid}")
    journal.append("answer", id=qid, text=text)
    if q.get("window"):
        tell(q["window"], f"Answer to your question ({q['text'][:80]}): {text}", task=q.get("task"))
    return {"answered": qid, "told": q.get("window")}


def point(milestone: str) -> dict:
    journal.append("point", milestone=milestone)
    return {"point": milestone}


def pause() -> dict:
    journal.append("pause")
    return {"paused": True}


def resume() -> dict:
    journal.append("resume")
    return {"paused": False}


def file_bug(title: str, text: str, milestone: str | None = None) -> dict:
    """A bug issue through the one write function; dry run unless the CLI said --apply (pipeline.bug-intake)."""
    args = ["issue", "create", "--title", title, "--body", text, "--label", cfg()["labels"]["bug"]]
    if milestone:
        args += ["--milestone", milestone]
    out = gh.write(*args, dry_run=DRY_RUN)
    if not milestone:
        _queue("milestone", f"bug '{title}' has no milestone; pick one")
    return {"result": out, "command": shlex.join(args)}


# The one table the three faces use; each tool is this function, no face has a shortcut around a check.
API = {"status": status, "start": start, "check": check, "verdict": verdict, "tell": tell, "report": report, "ask": ask,
       "done": done, "queue": queue, "answer": answer, "point": point, "pause": pause, "resume": resume, "file_bug": file_bug}
# Per-role MCP tools (pipeline.three-faces): approve/answer are never over MCP.
ROLE_TOOLS = {"coder": ("report", "ask", "done"), "reviewer": ("verdict", "report"),
              "manager": ("status", "start", "check", "tell", "file_bug", "point", "queue", "report")}
