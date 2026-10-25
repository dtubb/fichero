"""The state machine and the one set of functions the CLI, the MCP server and the page call (`API`).
States: queued → coding → checked → reviewed → candidate → gated → pushed → closed, plus failed, needs-maintainer,
rate-limited, waiting. An item moves only through the transitions in ALLOWED, each running its own check and
writing one journal line; a model's report never moves an item (pipeline.one-state-machine)."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from pipeline import STATE, budget, checks, coder, config, gh, journal

STATES = ("queued", "coding", "checked", "reviewed", "candidate", "gated", "pushed", "closed",
          "failed", "needs-maintainer", "rate-limited", "waiting")
# The states table of the spec, as code: (from, to). `start` on an item the maintainer sent back re-enters coding.
ALLOWED = {
    ("queued", "coding"), ("coding", "coding"), ("coding", "checked"), ("coding", "needs-maintainer"),
    ("coding", "rate-limited"), ("coding", "failed"), ("coding", "waiting"), ("waiting", "coding"),
    ("checked", "reviewed"), ("checked", "coding"), ("checked", "checked"), ("reviewed", "checked"), ("reviewed", "coding"),
    ("needs-maintainer", "coding"), ("needs-maintainer", "checked"), ("failed", "coding"), ("rate-limited", "coding"),
    ("reviewed", "candidate"), ("candidate", "gated"), ("gated", "pushed"), ("pushed", "closed"),
}
CFG: dict = {}
ISSUE = gh.issue  # the one read of an issue; tests replace it
DRY_RUN = True    # GitHub writes: the CLI flips this with --apply; tests and the proof run never do
ANSWER_DEADLINE_S = 4 * 3600


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
            if it:  # the item moves to a new task (a retry on another base): keep its record, re-bind it
                it.update(task=e["task"])
            else:
                s["items"][str(e["issue"])] = {"issue": e["issue"], "task": e["task"], "title": e.get("title", ""),
                                               "state": "queued", "attempts": 0, "checks": [], "verdicts": [],
                                               "cost_usd": 0.0, "history": [], "sha": "", "retry_text": ""}
            s["tasks"].setdefault(e["task"], {"issues": [], "window": e.get("window"), "worktree": e.get("worktree")})
            if e["issue"] not in s["tasks"][e["task"]]["issues"]:
                s["tasks"][e["task"]]["issues"].append(e["issue"])
        elif ev == "transition" and it:
            it["state"] = e["to"]
            it["history"].append(f"{e['ts']} {e['to']}: {e.get('why', '')}")
        elif ev == "check" and it:
            it["checks"] = e["results"]
            it["sha"] = e["sha"]
            if not e["ok"]:
                it["attempts"] += 1
                it["retry_text"] = "\n\n".join(f"[{r['name']}] {r['text']}" for r in e["results"] if not r["ok"])
        elif ev == "retry" and it:  # a binding NOT_READY: counts as an attempt, its findings are the retry text
            it["attempts"] += 1
            it["retry_text"] = e["text"]
        elif ev == "verdict" and it:
            it["verdicts"].append({k: e[k] for k in ("sha", "verdict", "by", "findings")})
        elif ev == "cost" and it:
            it["cost_usd"] = round(it["cost_usd"] + e["usd"], 4)
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
        elif ev == "worker_gone":
            s["workers"].pop(e["window"], None)
        elif ev == "undelivered" and e.get("window") in s["workers"]:
            s["workers"][e["window"]]["undelivered"] = e["text"][:120]
        elif ev == "tell" and e.get("delivered") and e.get("window") in s["workers"]:
            s["workers"][e["window"]].pop("undelivered", None)
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
    cur = state()["items"][str(issue)]["state"]
    if (cur, to) not in ALLOWED:
        raise RuntimeError(f"#{issue}: no transition {cur} -> {to} in the states table")
    journal.append("transition", issue=issue, to=to, why=why)


def _queue(kind: str, text: str, options=None, task=None, window=None) -> str:
    qid = uuid.uuid4().hex[:8]
    journal.append("queue", id=qid, kind=kind, text=text, options=options or [], task=task, window=window)
    return qid


def _require_running() -> None:
    if state()["paused"]:
        raise RuntimeError("paused: `python -m pipeline resume` first (pipeline.pause-all)")


def _head(wt) -> str:
    return checks.git(wt, "rev-parse", "HEAD")


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
        text += ["## The checks or the review FAILED on your last commit. Fix this, then commit again:", "```", failure[-6000:], "```", ""]
    fixes = "Part of" if issue.get("part_of") else "Fixes"
    text += ["## How to work",
             "1. Start with jcodemunch `plan_turn` for this task, and jdocmunch for the spec lines and docs. Read before you write.",
             "2. Ponytail: the shortest correct diff; no new abstractions; a `ponytail:` comment on each known ceiling.",
             "3. Write the test first from the spec's words and see it fail; then make it pass. Run only your own tests.",
             f"4. Do not change or delete anything under {', '.join(cfg()['repo']['check_paths'])}: those are the checks you are judged by (adding a new guard is fine).",
             f"5. Commit your own work, once for this issue: `git commit --author='Claude <{g['agent_email']}>' -m '<what> ({fixes} #{issue['number']})' -m '{g['commit_trailer']}'`. Uncommitted work counts as nothing.",
             f"6. When committed, call the `done` tool with task `{task}`. Use `ask` for a question (the maintainer answers), `report` for progress.",
             "7. Work only in this directory. Do not run the app or the engine; tests use the scratch paths the runner sets."]
    return "\n".join(text)


# --- transitions --------------------------------------------------------------------------------------------------

def _worktree(task: str, base: str | None = None) -> Path:
    c = cfg()
    base = base or c["repo"]["base"]
    wt = Path(c["repo"]["path"]) / c["repo"]["worktrees"] / task
    if not wt.exists():
        journal.append("intent", task=task, what="worktree", ref=str(wt))
        if "/" in base:
            subprocess.run(["git", "fetch", "-q", base.split("/")[0]], cwd=c["repo"]["path"], check=False)
        checks.git(c["repo"]["path"], "worktree", "add", "-q", "-b", f"pipeline/{task}", str(wt), base)
        subprocess.run(["git", "config", "extensions.worktreeConfig", "true"], cwd=wt, check=False, capture_output=True)
        for k, v in (("user.name", "Claude"), ("user.email", c["github"]["agent_email"])):
            subprocess.run(["git", "config", "--worktree", k, v], cwd=wt, check=False, capture_output=True)
        journal.append("done", task=task, what="worktree", ref=str(wt))
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
    journal.append("intent", task=task, what="worker", ref=window)
    coder.start_window(c, window, wt, coder.pi_command(c, worker, session_dir), coder.allowed_env(c, task, "coder"))
    journal.append("worker", window=window, task=task, role="coder", model=config.pi_model_id(worker),
                   session_dir=str(session_dir), cwd=str(wt))
    journal.append("done", task=task, what="worker", ref=window)
    return session_dir


def _live_coders(s: dict, task: str) -> list[str]:
    live = coder.live_windows(cfg())
    out = []
    for w in s["workers"].values():
        if w["window"] not in live:
            journal.append("worker_gone", window=w["window"], task=w["task"])
        elif w.get("task") != task and not w.get("idle"):
            out.append(w["window"])
    return out


def start(issues: list[int], milestone: str | None = None, task: str | None = None, worker_index: int = 0,
          from_file: str | None = None, base: str | None = None) -> dict:
    """queued → coding → (checks) for a batch of issues in one coder context; blocks until the batch is done.
    `from_file`: a local JSON issue (number, title, body, author, part_of) for a step not yet filed on GitHub.
    `base`: the branch the worktree comes off (default the profile's), e.g. the runner branch for a bootstrap step."""
    with journal.Lock("dispatch", wait=False):
        return _start(issues, milestone, task, worker_index, from_file, base)


def _start(issues, milestone, task, worker_index, from_file, base) -> dict:
    _require_running()
    c = cfg()
    task = task or f"{(milestone or 'issues').replace(' ', '-').lower()}-{issues[0]}"
    s = state()
    live = _live_coders(s, task)
    if len(live) >= c["workers"]["caps"]["coders"]:
        raise RuntimeError(f"coder cap {c['workers']['caps']['coders']}: {', '.join(live)} running")
    read_issue = ISSUE if not from_file else (lambda n: json.loads(Path(from_file).read_text()))
    briefs = {}
    for n in issues:  # every issue is read and allow-listed before anything starts
        it = s["items"].get(str(n))
        if it and it["state"] not in ("queued", "coding", "failed", "needs-maintainer", "rate-limited"):
            continue  # finished or under review: never redone (pipeline.resume-from-journal)
        briefs[n] = read_issue(n)
        if briefs[n].get("author") not in c["github"]["allowed_authors"]:
            _queue("triage", f"#{n} by {briefs[n].get('author')}: outside text, rewrite it into a triaged issue", task=task)
            raise PermissionError(f"#{n} is by {briefs[n].get('author')}: not allow-listed (pipeline.outside-bugs)")
    if not briefs:
        return {"task": task, "done": "nothing left to do"}
    wt = _worktree(task, base)
    window = f"coder-{task}"
    for n, iss in briefs.items():
        if str(n) not in s["items"] or s["items"][str(n)]["task"] != task:
            journal.append("item", issue=n, task=task, title=iss["title"], window=window, worktree=str(wt))
    worker = c["roles"]["coder"][worker_index]
    _wait_room(worker["kind"], task)
    session_dir = _start_worker(task, wt, worker, window)
    summary = {"task": task, "window": window, "worktree": str(wt), "items": {}}
    for n, iss in briefs.items():
        summary["items"][n] = _run_issue(task, n, iss, wt, window, session_dir, worker, worker_index)
        if summary["items"][n] in ("rate-limited", "failed"):
            break  # the fallback list: the next worker takes the rest of the batch in a fresh context
    return summary


def _run_issue(task, n, iss, wt, window, session_dir, worker, worker_index) -> str:
    c = cfg()
    since = _head(wt)
    journal.append("since", issue=n, sha=since)
    it = state()["items"][str(n)]
    failure, attempt = it["retry_text"], it["attempts"]
    while attempt <= c["workers"]["retries"]:
        _move(n, "coding", f"{worker['provider']}/{worker['model']}, attempt {attempt + 1}")
        path = coder.brief_file(task, f"issue-{n}-attempt-{attempt + 1}", brief(iss, task, failure))
        before = coder.status(session_dir)
        tell(window, f"Read and do {path} — issue #{n}. Call the `done` tool with task {task} when your commit is in.", task=task)
        st = coder.wait_idle(session_dir, c["workers"]["cost_cap_usd"], after_turns=before["turns"])
        st = _wait_answers(task, n, session_dir, st)
        spent = sum(e["usd"] for e in journal.read() if e["event"] == "cost" and e.get("task") == task)
        journal.append("cost", issue=n, task=task, usd=round(st["cost_usd"] - spent, 4), tokens=st["tokens"], model=st["model"],
                       tools=dict(st["tool_calls"]))
        if st.get("stopped") or st.get("rate_limited"):
            coder.stop_window(c, window)
            journal.append("worker_gone", window=window, task=task, why=st.get("stopped") or "rate limited")
            if st.get("rate_limited") or "cost cap" in st.get("stopped", ""):
                _move(n, "rate-limited", st.get("stopped") or "quota or credit failure")
                nxt = worker_index + 1 < len(c["roles"]["coder"])
                _queue("fallback" if nxt else "budget", f"#{n}: {worker['model']} stopped ({st.get('stopped') or 'rate limited'}); "
                       + ("the next worker takes over" if nxt else "every worker in the list stopped; more budget?"), task=task)
                return "rate-limited"
            _move(n, "failed", st["stopped"])
            return "failed"
        results = check(n, since=since, locked=True)
        if all(r["ok"] for r in results):
            return "checked"
        if results[0]["name"] == "pinned-checks" and not results[0]["ok"]:
            return "needs-maintainer"
        failure = state()["items"][str(n)]["retry_text"]
        attempt += 1
    _move(n, "needs-maintainer", failure[-500:])
    _queue("failed-checks", f"#{n} failed its checks or review {attempt} times:\n{failure[-1500:]}", task=task, window=window)
    return "needs-maintainer"


def _wait_answers(task: str, issue: int, session_dir: Path, st: dict) -> dict:
    """An idle worker that asked a question waits for the maintainer's answer, then for its next idle turn."""
    t0 = time.time()
    while any(q["task"] == task and q["kind"] == "ask" for q in state()["queue"].values()):
        if time.time() - t0 > ANSWER_DEADLINE_S:
            st["stopped"] = f"question unanswered for {ANSWER_DEADLINE_S // 3600} h"
            return st
        time.sleep(15)
        st = coder.wait_idle(session_dir, cfg()["workers"]["cost_cap_usd"], after_turns=st["turns"])
    return st


def check(issue: int, since: str | None = None, locked: bool = False) -> list[dict]:
    """coding → checked only when every rung is green, for the head read BEFORE the checks ran; a commit that lands
    mid-check is a red (the sha moved). Red: retry (the caller) or needs-maintainer."""
    if not locked:
        with journal.Lock("dispatch", wait=False):
            return check(issue, since, locked=True)
    s = state()
    it = s["items"].get(str(issue))
    if not it:
        raise KeyError(f"#{issue} is not an item")
    wt = Path(s["tasks"][it["task"]]["worktree"])
    since = since or next((e["sha"] for e in reversed(journal.read()) if e["event"] == "since" and e["issue"] == issue), None)
    sha = _head(wt)
    _wait_room("pytest", it["task"])
    with journal.Lock("test-run"):
        results = checks.run_all(wt, cfg(), since=since)
    if _head(wt) != sha:
        results.append({"name": "head-moved", "ok": False, "seconds": 0, "text": f"a commit landed during the checks ({sha[:9]} -> {_head(wt)[:9]})"})
    ok = bool(results) and all(r["ok"] for r in results)
    journal.append("check", issue=issue, ok=ok, sha=sha, results=results)
    gh.cache_clear()
    if ok:
        _move(issue, "checked", f"{len(results)} rungs green at {sha[:9]}")
    elif results[0]["name"] == "pinned-checks" and not results[0]["ok"]:
        _move(issue, "needs-maintainer", results[0]["text"])
    return results


def verdict(issue: int, sha: str, verdict: str, by: str, findings: str = "") -> dict:
    """checked → reviewed on READY from the reviewer role for the worktree's LIVE head (which must be the checked
    sha); a binding NOT_READY sends the item back to coding with the findings as its retry text and counts an
    attempt. Anything else is recorded only."""
    s = state()
    it = s["items"].get(str(issue))
    if not it:
        raise KeyError(f"#{issue} is not an item")
    wt = s["tasks"][it["task"]]["worktree"]
    try:
        sha = checks.git(wt, "rev-parse", "--verify", f"{sha}^{{commit}}")
    except RuntimeError:
        pass
    head = _head(wt)
    journal.append("verdict", issue=issue, sha=sha, verdict=verdict, by=by, findings=findings[:4000])
    binding = by == "reviewer" and sha == head == it["sha"] and it["state"] in ("checked", "reviewed")
    if binding and verdict == "READY":
        if it["state"] == "checked":
            _move(issue, "reviewed", f"READY by {by} at {sha[:9]}")
        return {"issue": issue, "state": "reviewed"}
    if binding and verdict == "NOT_READY":
        journal.append("retry", issue=issue, text=f"Review NOT_READY at {sha[:9]}:\n{findings}")
        _move(issue, "coding", f"NOT_READY by {by} at {sha[:9]}; run `start {issue}` to retry with the findings")
        return {"issue": issue, "state": "coding", "attempts": it["attempts"] + 1}
    why = "" if sha == head else f"verdict is for {sha[:9]}, head is {head[:9]}: not binding"
    if head != it["sha"]:
        why = f"head {head[:9]} is not the checked sha {it['sha'][:9]}: run `check {issue}` first"
    return {"issue": issue, "state": it["state"], "recorded": verdict, "note": why}


# --- messages, queue, pointing ----------------------------------------------------------------------------------

def tell(window: str, text: str, task: str | None = None) -> dict:
    """Type into the worker's window and confirm from its session log that the turn arrived; an unconfirmed send
    is journaled `undelivered` and the page flags the worker (pipeline.messages)."""
    _require_running()
    w = state()["workers"].get(window) or {}
    session_dir = Path(w["session_dir"]) if w.get("session_dir") else None
    journal.append("intent", task=task or window, what="tell", ref=text[:300])
    delivered = coder.tell(cfg(), window, text, session_dir)
    journal.append("tell", task=task, window=window, text=text[:300], delivered=delivered)
    if not delivered:
        journal.append("undelivered", task=task, window=window, text=text[:300])
    journal.append("done", task=task or window, what="tell", ref=text[:300])
    return {"window": window, "sent": text[:120], "delivered": delivered}


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
# What a worker's shell may never run through the CLI (pipeline.jailed-agent, until the write jail exists).
WORKER_FORBIDDEN = ("verdict", "answer", "start", "check", "pause", "resume", "point", "tell")
