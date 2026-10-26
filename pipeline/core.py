"""The state machine and the one set of functions the CLI, the MCP server and the page call (`API`).
States: queued → coding → checked → reviewed → candidate → gated → pushed → closed, plus failed, needs-maintainer,
rate-limited, waiting. An item moves only through the transitions in ALLOWED, each running its own check and
writing one journal line; a model's report never moves an item (pipeline.one-state-machine).

An item is keyed by its issue number, or by `<number>@<task>` for a step run from a local file (several unfilled
steps share "Part of #N"; round-3 review R3). Every function that takes `issue` accepts either form."""
from __future__ import annotations

import json
import re
import shlex
import time
import uuid
from pathlib import Path

from pipeline import ROOT, STATE, budget, checks, coder, config, feeder, gh, journal, localise, steps

STATES = ("queued", "coding", "checked", "reviewed", "candidate", "gated", "pushed", "closed",
          "failed", "needs-maintainer", "rate-limited", "waiting", "asking")
# The states table of the spec, as code: (from, to). `start`/`retry` on an item the maintainer sent back re-enters coding.
ALLOWED = {
    ("queued", "coding"), ("coding", "coding"), ("coding", "checked"), ("coding", "needs-maintainer"),
    ("coding", "rate-limited"), ("coding", "failed"), ("coding", "waiting"), ("waiting", "coding"), ("coding", "asking"), ("asking", "coding"),
    ("checked", "reviewed"), ("checked", "coding"), ("checked", "checked"), ("checked", "needs-maintainer"),
    ("reviewed", "checked"), ("reviewed", "coding"), ("reviewed", "needs-maintainer"),
    ("needs-maintainer", "coding"), ("needs-maintainer", "checked"), ("failed", "coding"), ("rate-limited", "coding"),
    ("reviewed", "candidate"), ("candidate", "gated"), ("gated", "pushed"), ("pushed", "closed"),
}
CFG: dict = {}
ISSUE = gh.issue  # the one read of an issue; tests replace it
DRY_RUN = True    # GitHub writes: the CLI flips this with --apply; tests and the proof run never do
TOOLS_WANTED = ("jcodemunch",)
ITEM_FIELDS = ("issue", "task", "sha", "to", "why", "ok", "results", "verdict", "by", "findings", "usd", "tokens", "model",
               "tools", "session", "text")


def cfg() -> dict:
    global CFG
    if not CFG:
        CFG = config.load()
    return CFG


# --- keys ------------------------------------------------------------------------------------------------------

def item_key(issue: int, task: str | None = None, from_file: str | None = None) -> str:
    return f"{issue}@{task}" if from_file else str(issue)


def resolve(issue, items: dict) -> str:
    """The item key for what the caller typed: a key as is, a number that is an item, or a number with exactly one
    `number@task` item."""
    k = str(issue)
    if k in items:
        return k
    hits = [x for x in items if x.startswith(f"{k}@")]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise KeyError(f"#{k} names several items: {', '.join(sorted(hits))}; give the key")
    raise KeyError(f"#{k} is not an item")


def _n(key: str) -> int:
    return int(str(key).split("@")[0])


# --- state = the journal replayed -------------------------------------------------------------------------------

USAGE = ("turns", "tokens", "usd", "fresh", "cache_read", "cache_write")  # what an issue_done line counts so far in its window


def state() -> dict:
    lastdone: dict = {}
    s = {"items": {}, "tasks": {}, "queue": {}, "point": None, "paused": False, "workers": {}, "machine": None}
    for e in journal.read():
        ev = e["event"]
        k = e.get("key") or (str(e["issue"]) if "issue" in e else None)
        it = s["items"].get(k) if k else None
        if ev == "item":
            args = {x: e.get(x) for x in ("task", "milestone", "base", "from_file", "ids")}
            if it:  # the item moves to a new task (a retry on another base): keep its record, re-bind it
                it.update(task=e["task"], start_args=args)
            else:
                s["items"][k] = {"key": k, "issue": e["issue"], "task": e["task"], "title": e.get("title", ""),
                                 "state": "queued", "attempts": 0, "checks": [], "verdicts": [], "cost_usd": 0.0,
                                 "history": [], "sha": "", "check_ok": False, "retry_text": "", "start_args": args}
            s["tasks"].setdefault(e["task"], {"issues": [], "window": e.get("window"), "worktree": e.get("worktree")})
            if k not in s["tasks"][e["task"]]["issues"]:
                s["tasks"][e["task"]]["issues"].append(k)
        elif ev == "transition" and it:
            it["state"] = e["to"]
            it["history"].append(f"{e['ts']} {e['to']}: {e.get('why', '')}")
        elif ev == "check" and it:
            it["checks"], it["sha"], it["check_ok"] = e["results"], e["sha"], e["ok"]
            if not e["ok"]:
                it["attempts"] += 1
                it["retry_text"] = "\n\n".join(f"[{r['name']}] {r['text']}" for r in e["results"] if not r["ok"])
        elif ev == "retry" and it:  # a binding NOT_READY: counts as an attempt, its findings are the retry text
            it["attempts"] += 1
            it["retry_text"] = e["text"]
        elif ev == "reset" and it:  # the maintainer: the attempts so far were the runner's fault, not the coder's
            it["attempts"] = 0
        elif ev == "approve_checks" and it:  # the maintainer OKs this check change and sends the findings
            it["approved_checks"] = {**it.get("approved_checks", {}), **e["blobs"]}  # path -> the approved blob sha
            it["attempts"], it["retry_text"] = 0, e["text"]
        elif ev == "verdict" and it:
            it["verdicts"].append({x: e[x] for x in ("sha", "verdict", "by", "findings")})
        elif ev == "cost" and it:
            it["cost_usd"] = round(it["cost_usd"] + e["usd"], 4)
            it["tokens"], it["model"] = e["tokens"], e["model"]
        elif ev == "done_requested" and it and e.get("text"):
            it["residue"] = e["text"]
        elif ev == "closer" and it:
            it["closer"] = e["what"]
        elif ev == "issue_done" and it:
            it.setdefault("dones", []).append({x: e[x] for x in ("sha", "turns", "tokens", "usd")})
            u = it.setdefault("usage", dict.fromkeys(USAGE, 0))  # this issue's own share: the step from the task's last done line
            prev = lastdone.get(e["task"]) or {}
            now = {x: e.get(x, 0) for x in USAGE}
            for x in USAGE:
                u[x] = round(u[x] + now[x] - prev.get(x, 0), 4)
            lastdone[e["task"]] = now
        elif ev == "note" and it:
            it.setdefault("notes", []).append(e["text"])
        elif ev == "queue":
            s["queue"][e["id"]] = {x: e.get(x) for x in ("id", "kind", "text", "options", "task", "window", "key", "ts")}
        elif ev == "answer":
            q = s["queue"].pop(e["id"], None)
            if q and q.get("key") in s["items"]:  # the answer waits on the item until the worker is woken with it
                s["items"][q["key"]]["answer"] = e["text"]
        elif ev == "point":
            s["point"] = e["milestone"]
        elif ev in ("pause", "resume"):
            s["paused"] = ev == "pause"
        elif ev == "worker":
            if e.get("role") == "coder":
                lastdone.pop(e["task"], None)  # a new coder window counts from zero again
            s["workers"][e["window"]] = {x: e.get(x) for x in ("window", "task", "model", "session_dir", "cwd", "role")}
        elif ev == "worker_gone":
            s["workers"].pop(e["window"], None)
        elif ev in ("park", "wake") and e["window"] in s["workers"]:
            s["workers"][e["window"]].update(parked=e["ts"] if ev == "park" else None, park_milestone=e.get("milestone"))
        elif ev == "undelivered" and e.get("window") in s["workers"]:
            s["workers"][e["window"]]["undelivered"] = e["text"][:120]
        elif ev == "tell" and e.get("delivered") and e.get("window") in s["workers"]:
            s["workers"][e["window"]].pop("undelivered", None)
        elif ev in ("report", "tell", "ask", "done_requested", "wait") and e.get("task") in s["tasks"]:
            s["tasks"][e["task"]].setdefault("messages", []).append(f"{e['ts']} {ev}: {e.get('text', '')[:200]}")
    for w in s["workers"].values():
        st = coder.status(Path(w["session_dir"])) if w.get("session_dir") else {}
        task_done = all(s["items"][k]["state"] not in ("queued", "coding") for k in s["tasks"].get(w["task"], {}).get("issues", []))
        w.update(idle=st.get("idle"), cost_usd=round(st.get("cost_usd", 0.0), 3), tokens=st.get("tokens", 0),
                 last_text=(st.get("last_text") or "")[-300:], last_said=last_sentence(st.get("last_text") or ""),
                 idle_text="idle — task done" if st.get("idle") and task_done else "idle" if st.get("idle") else
                 "busy" if st.get("idle") is False else "—")
    s["stuck"] = [k for k, it in s["items"].items() if _stuck(it)]
    for it in s["items"].values():
        it["verdict_now"] = verdict_now(it)
        it["summary"] = summary(it)
    s["queue_done"] = {qid: q for qid, q in s["queue"].items() if resolved(q, s)}
    for qid in s["queue_done"]:
        s["queue"].pop(qid)
    s["spend_today"], s["daily_cap"] = spend_today(), daily_cap()
    costs = [e for e in journal.read() if e["event"] == "cost"]
    for name, t in s["tasks"].items():  # dollars per issue = the task's session cost over the issues it finished
        t["cost_usd"] = round(sum(e["usd"] for e in costs if e.get("task") == name), 4)
        done = [k for k in t["issues"] if s["items"][k]["state"] in ("checked", "reviewed", "candidate", "gated", "pushed", "closed")]
        t["issues_done"] = len(done)
        t["cost_per_issue"] = round(t["cost_usd"] / len(done), 4) if done else t["cost_usd"]
    s["now"] = now_line(s)
    return s


# --- words for the page (pipeline.dashboard-minimal): what is happening, what is done, what needs you -----------

def last_sentence(text: str, limit: int = 160) -> str:
    """The last full sentence of what a worker said, never a fragment from mid-text."""
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[.!?])\s+", text)
    s = next((p for p in reversed(parts) if p.strip()), "")
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


def verdict_now(it: dict) -> dict | None:
    """The one verdict that counts: the last one recorded at the item's checked sha, if its check was green."""
    for v in reversed(it["verdicts"]):
        if v["sha"] == it["sha"] and it["check_ok"]:
            return v
    return None


def summary(it: dict) -> str:
    """One sentence per item: its state, what that means, and the next step."""
    sha, n, st = it["sha"][:9], len(it["checks"]), it["state"]
    green = n and all(c["ok"] for c in it["checks"])
    v = it.get("verdict_now")
    red = next((c["name"] for c in it["checks"] if not c["ok"]), None)
    if st == "queued":
        return "Queued; next: a coder starts it."
    if st == "coding":
        return f"Coding, attempt {it['attempts'] + 1}" + (f" after a red {red} check" if red else "") + "; next: the checks run when the coder calls done."
    if st == "checked":
        if v and v["verdict"] == "PENDING":
            return f"Checked at {sha}, all {n} checks green; review PENDING ({v['by']}); next: the reviewer's verdict."
        return f"Checked at {sha}, all {n} checks green; next: a review."
    if st == "reviewed":
        return f"Reviewed READY at {sha}, all {n} checks green; next: the lead lands it."
    if st == "needs-maintainer":
        return f"Needs you at {sha}: {(it['retry_text'] or 'attempts exhausted').splitlines()[0][:90]}; next: `retry` or `reset`."
    if st == "rate-limited":
        return "Stopped on a quota or credit error; next: `retry` takes the fallback list's next worker."
    if st == "failed":
        return f"Failed: {it['history'][-1].split(': ', 1)[-1][:90] if it['history'] else ''}; next: `retry`."
    return f"{st.capitalize()} at {sha}" + (", checks green" if green else "") + "."


def resolved(q: dict, s: dict) -> bool:
    """A queue item resolves itself when its condition clears: a fallback once the next worker has run, a failed-checks
    item once the item is later checked or reviewed, a question once answered (answers are already popped)."""
    task_items = [s["items"][k] for k in s["tasks"].get(q.get("task"), {}).get("issues", [])]
    later = [e for e in journal.read() if e["ts"] > (q.get("ts") or "")]
    if q["kind"] == "fallback":
        return any(e["event"] == "worker" and e.get("task") == q.get("task") for e in later)
    if q["kind"] == "failed-checks":
        return any(e["event"] == "transition" and e.get("to") in ("checked", "reviewed")
                   and (e.get("key") or str(e.get("issue"))) in [it["key"] for it in task_items] for e in later)
    return False


def now_line(s: dict) -> str:
    items = list(s["items"].values())
    busy = [w for w in s["workers"].values() if w.get("idle") is False]
    parts = []
    if not items:
        parts.append("No items yet.")
    for it in items:
        title = it["title"] if len(it["title"]) <= 44 else it["title"][:44].rsplit(" ", 1)[0] + "…"
        label = f"{it['key']} {title}"
        v = it.get("verdict_now")
        if it["state"] == "coding":
            w = next((w for w in s["workers"].values() if w["task"] == it["task"]), None)
            parts.append(f"{label}: coding ({(w or {}).get('model', '?')}, attempt {it['attempts'] + 1}, ${it['cost_usd']:.2f}).")
        elif it["state"] == "reviewed":
            parts.append(f"{label}: reviewed READY, ready to land.")
        elif it["state"] == "checked":
            parts.append(f"{label}: checked, review {v['verdict'] if v else 'awaited'}.")
        else:
            parts.append(f"{label}: {it['state']}.")
    parts.append(f"{len(busy)} worker{'s' if len(busy) != 1 else ''} busy." if busy else "No worker busy.")
    n = len([q for q in s["queue"].values() if q["kind"] != "write-up"])  # write-ups are work for the runner, not questions
    parts.append(f"Needs you: {n}." if n else "Nothing needs you.")
    if len(s["queue"]) > n:
        parts.append(f"Needs write-up: {len(s['queue']) - n}.")
    return " ".join(parts)


def _stuck(it: dict) -> bool:
    if it["state"] not in ("coding", "checked") or not it["history"]:
        return False
    last = time.mktime(time.strptime(it["history"][-1][:19], "%Y-%m-%dT%H:%M:%S"))
    return time.time() - last > cfg()["workers"]["stuck_minutes"] * 60


def status() -> dict:
    s = state()
    s["machine"] = budget.machine()
    return s


def _item(issue) -> tuple[str, dict, dict]:
    s = state()
    k = resolve(issue, s["items"])
    return k, s["items"][k], s


def _move(key: str, to: str, why: str = "") -> None:
    cur = state()["items"][key]["state"]
    if (cur, to) not in ALLOWED:
        raise RuntimeError(f"{key}: no transition {cur} -> {to} in the states table")
    journal.append("transition", issue=_n(key), key=key, to=to, why=why)


def _queue(kind: str, text: str, options=None, task=None, window=None, key=None) -> str:
    qid = uuid.uuid4().hex[:8]
    journal.append("queue", id=qid, kind=kind, text=text, options=options or [], task=task, window=window, key=key)
    return qid


def _require_running() -> None:
    if state()["paused"]:
        raise RuntimeError("paused: `python -m pipeline resume` first (pipeline.pause-all)")


# --- the daily API cap (owner, 2026-10-25: no runaway spend before the runner is proven) -------------------------------

def today() -> str:
    return time.strftime("%Y-%m-%d")


def spend_today() -> float:
    """API dollars recorded in the journal today, every item and role together."""
    return round(sum(e["usd"] for e in journal.read() if e["event"] == "cost" and e["ts"][:10] == today()), 4)


def daily_cap() -> float:
    """The profile's daily cap, or what `resume --raise-cap N` set for today."""
    raised = [e["usd"] for e in journal.read() if e["event"] == "raise_cap" and e["ts"][:10] == today()]
    return max([cfg()["workers"].get("daily_cap_usd", 25.0), *raised])


def cap_for(session_dir) -> float:
    """What wait_idle may let this session spend: the session cap, or what is left of today's cap if that is less
    (#6145: the daily cap used to be checked only after a turn, so one session could overshoot it)."""
    mine = sum(e["usd"] for e in journal.read() if e["event"] == "cost" and e.get("session") == str(session_dir))
    return min(cfg()["workers"]["cost_cap_usd"], mine + max(0.0, daily_cap() - spend_today()))


def _require_budget() -> None:
    """Nothing new starts once today's spend has reached the cap; the next day or `resume --raise-cap` lifts it."""
    spent, cap = spend_today(), daily_cap()
    if spent >= cap:
        raise RuntimeError(f"daily cap: ${spent:.2f} of ${cap:.2f} spent today; `resume --raise-cap <usd>` lifts it for today")


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


def issue_ids(issue: dict) -> list[str]:
    return sorted(set(BEHAVIOUR_ID.findall(issue.get("body") or "")))


def localised(issue: dict, task: str, key: str) -> dict:
    """Where the issue's change goes, found without a model (the spec citations, then git grep); only when that finds
    nothing, ONE small-tier call names the paths, which are then checked like any other. Journaled `localised`."""
    c = cfg()
    text = (issue.get("body") or "") + "\n" + "\n".join(spec_lines(set(issue_ids(issue))))
    loc = localise.localise(c["repo"]["path"], text)
    if loc["size"] == "unknown":
        w = config.at_tier(c, workers()[0], "small")
        dirs = sorted({str(Path(f).parent) for f in checks.git(c["repo"]["path"], "ls-files").splitlines()
                       if f.count("/") <= 3})[:400]  # ponytail: directories, not files; a repo map when this misses
        prompt = "\n".join([f"Issue: {issue['title']}", text[:4000], "", "Directories:", *dirs, "",
                             "Name up to 5 existing repo file paths this issue changes and its test file, one per line, nothing else."])
        session = STATE / "sessions" / task / f"localise-{key}-{time.strftime('%Y%m%d-%H%M%S')}"
        st = coder.ask_once(c, w, prompt, session)
        journal.append("cost", issue=_n(key), key=key, task=task, session=str(session), usd=round(st["cost_usd"], 4),
                       tokens=st["tokens"], model=st["model"] or w["model"], tools={})
        loc = dict(localise.localise(c["repo"]["path"], text + "\n" + st["answer"]), by_model=True)
    journal.append("localised", issue=_n(key), key=key, task=task, files=loc["files"], symbols=sorted(loc["symbols"]),
                   tests=[t["path"] + (f"::{t['name']}" if t["name"] else "") for t in loc["tests"]], size=loc["size"],
                   by_model=loc.get("by_model", False))
    return loc


# The brief's stable prefix: no issue number, task or timestamp, so every brief starts with the same bytes and a
# prefix cache hits (pipeline.prompt-cache); the issue, its spec lines, where and the test come after.
def brief_rules() -> list[str]:
    g = cfg()["github"]
    return ["# How to work (the same for every issue)",
             "1. Do not explore: the issue section below names what to change. Read only the symbols you edit (jcodemunch "
             "`get_symbol_source` / `get_file_outline`), then edit. The `mcp` tool (the wide set) is a brief miss: "
             "use it only when the brief truly lacks something, and say what in `pipeline_report`.",
             "2. Ponytail: the shortest correct diff; no new abstractions; a `ponytail:` comment on each known ceiling.",
             "3. Write the test first from the spec's words and see it fail; then make it pass. Run only your own tests.",
             f"4. Do not change or delete anything under {', '.join(cfg()['repo']['check_paths'])}: those are the checks you are judged by (adding a new guard is fine).",
             "5. Never change your own acceptance: the text of the spec lines for your behaviour ids and the build order's "
             "Behaviours/Tests lines stay as they are (flipping the [TAG] to [OK] or [PARTIAL] is fine). If they are wrong, call `pipeline_ask`.",
             f"6. Commit your own work, once per issue: `git commit --author='Claude <{g['agent_email']}>' -m '<what> (<keyword> #<n>)' -m '{g['commit_trailer']}'`, "
             "the issue line below says which. Uncommitted work counts as nothing.",
             "7. When committed, call the pipeline MCP tool `done` (shown to you as `pipeline_done`) with the task named below. "
             "Use `pipeline_ask` for a question (the maintainer answers), `pipeline_report` for progress.",
             "8. Work only in this directory. Do not run the app or the engine; tests use the scratch paths the runner sets. "
             "Never push, never `git stash`, never touch the maintainer's data or settings.", ""]


def brief(issue: dict, task: str, failure: str = "") -> str:
    """The coder's prompt: the stable rules, then the issue (only text by allow-listed authors), its spec lines,
    where the change goes and the test to write. Outside text never enters a prompt (pipeline.outside-bugs)."""
    g = cfg()["github"]
    if issue.get("author") not in g["allowed_authors"]:
        raise PermissionError(f"#{issue['number']} is by {issue.get('author')}: not allow-listed, triage it first")
    lines = spec_lines(set(issue_ids(issue)))
    fixes = "Part of" if issue.get("part_of") else "Fixes"
    text = [*brief_rules(), f"# Issue #{issue['number']}: {issue['title']}",
            f"Task `{task}`; commit with `({fixes} #{issue['number']})`.", "", issue.get("body") or "", ""]
    if issue.get("handoff"):
        text += [f"## Handoff: the previous session ended near its context limit; read {issue['handoff']} first (what is done, what failed).", ""]
    if lines:
        text += ["## Spec lines", *lines, ""]
    text += localise.section(issue.get("localised") or {"files": [], "symbols": {}, "tests": []})
    if failure:
        text += ["## The checks or the review FAILED on your last commit. Fix this, then commit again:", "```", failure[-6000:], "```", ""]
    return "\n".join(text)


# --- transitions --------------------------------------------------------------------------------------------------

def _worktree(task: str, base: str | None = None) -> Path:
    c = cfg()
    base = base or c["repo"]["base"]
    wt = Path(c["repo"]["path"]) / c["repo"]["worktrees"] / task
    if not wt.exists():
        journal.append("intent", task=task, what="worktree", ref=str(wt))
        remotes = checks.git(c["repo"]["path"], "remote").split()
        if base.split("/")[0] in remotes:  # a remote-tracking base is refreshed first; a local branch is used as is
            checks.sh(["git", "fetch", "-q", base.split("/")[0]], cwd=c["repo"]["path"])
        checks.git(c["repo"]["path"], "worktree", "add", "-q", "-b", f"pipeline/{task}", str(wt), base)
        checks.sh(["git", "config", "extensions.worktreeConfig", "true"], cwd=wt)  # every runner git: hooks off (checks.GIT)
        for k, v in (("user.name", "Claude"), ("user.email", c["github"]["agent_email"])):
            checks.sh(["git", "config", "--worktree", k, v], cwd=wt)
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


def workers(role: str = "coder") -> list[dict]:
    """The role's ordered fallback list, without the entries switched off in the profile (Qwen today)."""
    return [w for w in cfg()["roles"][role] if w.get("enabled", True)]


def cites_docs(issue: dict) -> bool:
    """jdocmunch joins the worker's tools only when the issue names a doc page beyond the spec lines in its brief."""
    return bool(re.search(r"(?<![\w/])docs/\S+\.md", issue.get("body") or ""))


def _start_worker(task: str, wt: Path, worker: dict, window: str, docs: bool = False) -> Path:
    """Each window start gets its OWN timestamped session dir, so delivery and idleness are read from the new
    session's file, never from an older one (review MED B)."""
    c = cfg()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    journal.append("intent", task=task, what="worker", ref=window)
    session = STATE / "sessions" / task / f"{worker['provider']}-{worker['model'].replace('/', '_')}-{stamp}"
    session.mkdir(parents=True, exist_ok=True)
    cmd = coder.pi_command(c, worker, session, task=task, docs=docs)
    coder.start_window(c, window, wt, cmd, coder.allowed_env(c, task, "coder"))
    journal.append("worker", window=window, task=task, role="coder", model=config.pi_model_id(worker), kind=worker["kind"],
                   session_dir=str(session), cwd=str(wt))
    journal.append("done", task=task, what="worker", ref=window)
    return session


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
          from_file: str | None = None, base: str | None = None, writeup: bool = False) -> dict:
    """queued → coding → (checks) for a batch of issues in one coder context; blocks until the batch is done.
    `from_file`: a local JSON issue (number, title, body, author, part_of) for a step not yet filed on GitHub; such
    an item is keyed `<number>@<task>`, so several steps may share "Part of #N".
    `base`: the branch the worktree comes off (default the profile's), e.g. the runner branch for a bootstrap step.
    `writeup`: an issue brief-lint refuses gets ONE write-up turn from the small worker first (pipeline.brief-lint)."""
    with journal.Lock("dispatch", wait=False):
        return _start(issues, milestone, task, worker_index, from_file, base, writeup)


def retry(issue, worker: int | None = None) -> dict:
    """Run the item again with the start arguments its record keeps (task, base, from_file, milestone); the brief
    carries the retry text from the red check or the NOT_READY review (dogfood 5). The worker is the next entry of
    the role's fallback list after each rate-limited stop, unless given. A record without start arguments (made
    before they were kept) is refused: `repair` it first."""
    key, it, _ = _item(issue)
    a = it["start_args"]
    if a.get("ids") is None:
        raise RuntimeError(f"{key}: its record has no start arguments; run `python -m pipeline repair {key} "
                           f"--base <ref> [--from-file <json>] [--since <sha>]` first")
    if worker is None:
        stops = sum(1 for h in it["history"] if " rate-limited:" in h)
        worker = min(stops, len(workers()) - 1)
    return start([it["issue"]], milestone=a.get("milestone"), task=a.get("task"), from_file=a.get("from_file"), base=a.get("base"),
                 worker_index=worker)


def repair(issue, base: str | None = None, from_file: str | None = None, since: str | None = None, why: str = "") -> dict:
    """Correct an item's record by APPENDING: an `item` line with the start arguments, and/or a tagged `since` line
    for its task. Nobody edits the journal by hand; the repair is journaled with its reason (round-3 review)."""
    key, it, s = _item(issue)
    t = s["tasks"][it["task"]]
    done = []
    if base or from_file:
        iss = json.loads(Path(from_file).read_text()) if from_file else {"title": it["title"], "body": ""}
        journal.append("item", issue=it["issue"], key=key, task=it["task"], title=iss.get("title", it["title"]), window=t["window"],
                       worktree=t["worktree"], milestone=it["start_args"].get("milestone"), base=base, from_file=from_file,
                       ids=issue_ids(iss))
        done.append("start args")
    if since:
        sha = checks.git(t["worktree"], "rev-parse", "--verify", f"{since}^{{commit}}")
        journal.append("since", issue=it["issue"], key=key, task=it["task"], sha=sha)
        done.append(f"since {sha[:9]}")
    journal.append("note", issue=it["issue"], key=key, text=f"repair: {', '.join(done) or 'nothing'}; {why}")
    return {"key": key, "repaired": done}


def _start(issues, milestone, task, worker_index, from_file, base, writeup=False) -> dict:
    _require_running()
    _require_budget()
    coder.require_mcp_sdk()
    c = cfg()
    s = state()
    woken = _parked(s, milestone, c) if milestone and not from_file else None
    task = woken["task"] if woken else task or f"{(milestone or 'issues').replace(' ', '-').lower()}-{issues[0]}"
    live = _live_coders(s, task)
    if len(live) >= c["workers"]["caps"]["coders"]:
        raise RuntimeError(f"coder cap {c['workers']['caps']['coders']}: {', '.join(live)} running")
    read_issue = ISSUE if not from_file else (lambda n: json.loads(Path(from_file).read_text()))
    briefs = {}
    for n in issues:  # every issue is read and allow-listed before anything starts
        k = item_key(n, task, from_file)
        it = s["items"].get(k)
        if it and it["state"] not in ("queued", "coding", "failed", "needs-maintainer", "rate-limited"):
            continue  # finished or under review: never redone (pipeline.resume-from-journal)
        briefs[k] = read_issue(n)
        if briefs[k].get("author") not in c["github"]["allowed_authors"]:
            _queue("triage", f"#{n} by {briefs[k].get('author')}: outside text, rewrite it into a triaged issue", task=task)
            raise PermissionError(f"#{n} is by {briefs[k].get('author')}: not allow-listed (pipeline.outside-bugs)")
    if not briefs:
        return {"task": task, "done": "nothing left to do"}
    wt = _worktree(task, base)
    window = woken["window"] if woken else f"coder-{task}"
    for k, iss in briefs.items():
        if k not in s["items"] or s["items"][k]["task"] != task:
            journal.append("item", issue=_n(k), key=k, task=task, title=iss["title"], window=window, worktree=str(wt),
                           milestone=milestone, base=base, from_file=from_file, ids=issue_ids(iss))
    approved = _approved() if writeup else set()
    unfit = [k for k, iss in briefs.items() if writeup and feeder.lint(iss, c["labels"], approved)]
    if not unfit:
        for k, iss in briefs.items():
            iss["localised"] = localised(iss, task, k)
    # the batch's size routes it: every issue small => the small tier; anything bigger or unplaced => the big one
    tier = "small" if unfit or all(b["localised"]["size"] == "small" for b in briefs.values()) else "big"
    worker = config.at_tier(c, workers()[worker_index], tier)
    docs = any(cites_docs(i) for i in briefs.values())
    if woken:  # the parked worker keeps its window and context: only the new briefs go in
        journal.append("wake", window=window, task=task, milestone=milestone)
        session_dir = Path(woken["session_dir"])
    else:
        _wait_room(worker["kind"], task)
        session_dir = _start_worker(task, wt, worker, window, docs=docs)
    out = {}
    for k in unfit:  # written up first, in the worker's own session; a fit result goes straight on to be coded (no re-exploration)
        _move(k, "coding", "write-up turn")
        parts = _writeup(task, k, briefs[k], wt, window, session_dir, worker)
        briefs[k] = feeder.apply_writeup(briefs[k], parts)
        if miss := feeder.lint(briefs[k], c["labels"], _approved(wt)):  # the worktree's specs: the new [GAP] line is there
            briefs.pop(k)
            out[k] = "needs-maintainer"
            why = f"written up, not fit to dispatch (lacks {'; '.join(miss)}): ID {parts.get('id', '?')}; ACCEPTANCE {parts.get('acceptance', '?')}; TEST {parts.get('test', '?')}"
            _move(k, "needs-maintainer", why)
            _queue("proposal", f"{k}: {why}\nA new [GAP] line is on the task branch; approve the spec, then `start` again.", task=task)
    if not briefs:
        coder.stop_window(c, window)
        journal.append("worker_gone", window=window, task=task, why="write-up done")
        return {"task": task, "window": window, "worktree": str(wt), "items": out}
    for k, iss in briefs.items():
        if "localised" not in iss:
            iss["localised"] = localised(iss, task, k)
    out |= _run_batch(task, briefs, wt, window, session_dir, worker, worker_index, docs)
    if milestone and all(v == "checked" for v in out.values()):  # nothing ready now: the window stays, no model calls
        journal.append("park", window=window, task=task, milestone=milestone)
    return {"task": task, "window": window, "worktree": str(wt), "items": out}


def _parked(s: dict, milestone: str, c: dict) -> dict | None:
    """A parked coder of this milestone that is live, idled less than park_ttl and has context room (pipeline.batch-
    session). Parked windows past the ttl are stopped here, when the next start looks (ponytail: no timer until the
    runner has a daemon)."""
    w, live, found = c["workers"], coder.live_windows(c), None
    for win, p in list(s["workers"].items()):
        if not p.get("parked") or p["window"] not in live:
            continue
        age = time.time() - time.mktime(time.strptime(p["parked"], "%Y-%m-%dT%H:%M:%S"))
        room = coder.status(Path(p["session_dir"]))["context"] < w["context_tokens"] * w["batch_end_pct"] / 100
        if age > w["park_ttl_minutes"] * 60 or not room:
            coder.stop_window(c, win)
            journal.append("worker_gone", window=win, task=p["task"], why="parked past park_ttl or context full")
        elif p.get("park_milestone") == milestone:
            found = p
    return found


def _handoff(task: str, wt: Path, since: str, n: int) -> Path:
    """The short note a fresh window starts from: issues done with their commits, files touched, failures. From the
    journal and git, never a transcript replay (pipeline.batch-session)."""
    its = [(e["issue"], e["sha"][:9]) for e in journal.read() if e["event"] == "issue_done" and e.get("task") == task]
    state_ = state()["items"]
    lines = [f"# Handoff for task {task}", "", "Done (issue, commit, state):"]
    lines += [f"- #{i} {sha} {state_[k]['state']}" for i, sha in its for k in [item_key(i, task)] if k in state_]
    lines += ["", "Files touched so far:", *(f"- {f}" for f in checks.git(wt, "diff", "--name-only", f"{since}..HEAD").split()[:40])]
    failed = [f"- {k}: {it['retry_text'][-300:]}" for k, it in state_.items() if it["task"] == task and it["retry_text"]]
    return coder.brief_file(task, f"handoff-{n}", "\n".join(lines + (["", "Failures seen:", *failed] if failed else [])))


def _since(key: str, task: str) -> str | None:
    """The sha the item started from in this task: the first `since` recorded for (key, task). Red-on-base and
    the changed-files set are measured from there, not from a retry's own start, or a retry that only fixes lint
    in a test file could never be red on the base (live, 2026-10-25)."""
    lines = [e for e in journal.read() if e["event"] == "since" and (e.get("key") or str(e["issue"])) == key]
    tagged = [e["sha"] for e in lines if e.get("task") == task]
    if tagged:
        return tagged[0]
    tasks = {e.get("task") for e in lines}
    return lines[0]["sha"] if lines and tasks == {None} else None  # untagged lines, one task so far: the first one


def _turn(task, key, iss, wt, window, session_dir, worker, worker_index, since, failure, attempt, resume=None) -> tuple[str | None, str]:
    """One coding turn: tell the brief, wait for the worker's idle turn, journal its cost and the `done` line (sha and
    usage so far; an issue's turns, tokens and dollars are the difference between two done lines). → (terminal
    state or None, the commit the worker finished on). A stopped worker ends the item here."""
    c, n = cfg(), _n(key)
    _move(key, "coding", f"{worker['provider']}/{worker['model']}, attempt {attempt + 1}")
    before = coder.status(session_dir)
    if resume:  # the same session, woken by the maintainer's answer: no new brief
        tell(window, f"The maintainer answered your question: {resume}\nCarry on with issue #{n}. Call the `done` tool with task {task} and issue {n} when your commit is in.", task=task)
    else:
        path = coder.brief_file(task, f"issue-{n}-attempt-{attempt + 1}", brief(iss, task, failure))
        tell(window, f"Read and do {path} — issue #{n}. Call the `done` tool with task {task} and issue {n} when your commit is in.", task=task)
    st = coder.wait_idle(session_dir, cap_for(session_dir), after_turns=before["turns"], token_cap=worker.get("token_cap"))
    # per-issue cost is the delta of THIS session file's running total (a new window = a new session = from 0)
    spent = sum(e["usd"] for e in journal.read() if e["event"] == "cost" and e.get("session") == str(session_dir))
    journal.append("cost", issue=n, key=key, task=task, session=str(session_dir), usd=round(st["cost_usd"] - spent, 4),
                   tokens=st["tokens"], model=st["model"], tools=dict(st["tool_calls"]))
    sha = _head(wt)
    if state()["items"][key]["state"] == "asking":  # the worker asked: park its window, no polling; an answer wakes it (resume_asked)
        journal.append("park", window=window, task=task, milestone=None)
        return "asking", sha
    journal.append("issue_done", issue=n, key=key, task=task, sha=sha, turns=st["turns"], tokens=st["tokens"], usd=st["cost_usd"],
                   fresh=st.get("fresh", 0), cache_read=st.get("cache_read", 0), cache_write=st.get("cache_write", 0))
    if st.get("proxy_calls", 0) > before.get("proxy_calls", 0):  # the worker reached for the wide set
        journal.append("brief_miss", issue=n, key=key, task=task, calls=st["proxy_calls"] - before.get("proxy_calls", 0))
    unused = [t for t, used in coder.uses_tools(st, *TOOLS_WANTED).items() if not used]
    if unused:  # information only, never a failure (dogfood 7)
        journal.append("note", issue=n, key=key, text=f"tools unused by the first done: {', '.join(unused)}")
    daily = spend_today() >= daily_cap()
    if daily:  # every worker is under the same cap: the queue asks for budget, not for the next worker
        st["stopped"] = f"daily cap: ${spend_today():.2f} of ${daily_cap():.2f}"
        st["rate_limited"] = True
    if st.get("stopped") or st.get("rate_limited"):
        coder.stop_window(c, window)
        journal.append("worker_gone", window=window, task=task, why=st.get("stopped") or "rate limited")
        if st.get("rate_limited") or "cost cap" in st.get("stopped", ""):
            _move(key, "rate-limited", st.get("stopped") or "quota or credit failure")
            nxt = worker_index + 1 < len(workers()) and not daily
            _queue("fallback" if nxt else "budget", f"{key}: {worker['model']} stopped ({st.get('stopped') or 'rate limited'}); "
                   + ("the next worker takes over" if nxt else "every worker in the list stopped; more budget?"), task=task)
            return "rate-limited", sha
        _move(key, "failed", st["stopped"])
        return "failed", sha
    return None, sha


def _run_issue(task, key, iss, wt, window, session_dir, worker, worker_index, first=None) -> str:
    """The item's turn/check/retry loop. `first` = (turn result, check results, the attempt count before them) when the batch already ran the first
    turn and is checking it while the worker codes the next issue."""
    c = cfg()
    since = _since(key, task) or _head(wt)
    if not first:
        journal.append("since", issue=_n(key), key=key, task=task, sha=since)
    it = state()["items"][key]
    failure, attempt = it["retry_text"], first[2] if first else it["attempts"]
    while attempt <= c["workers"]["retries"]:
        if first:
            end, results, _ = first
            first = None
        else:
            end, sha = _turn(task, key, iss, wt, window, session_dir, worker, worker_index, since, failure, attempt)
            results = check(key, since=since, locked=True, sha=sha) if not end else None
        if end:
            return end
        if steps.route(c["steps"], "checks", 0 if all(r["ok"] for r in results) else 1) != "code":  # the profile's route
            return "checked"
        if results[0]["name"] == "pinned-checks" and not results[0]["ok"]:
            return "needs-maintainer"
        failure = state()["items"][key]["retry_text"]
        u, w = state()["items"][key].get("usage") or {}, c["workers"]
        if u.get("turns", 0) > w.get("issue_turns_max", 10) or u.get("tokens", 0) > w.get("issue_tokens_max", 150000):
            why = f"{key} is over its budget ({u.get('turns', 0)} turns, {u.get('tokens', 0):,} tokens) and still red; no further attempt"
            _move(key, "needs-maintainer", why)
            _queue("ask", f"{why}:\n{failure[-1500:]}", task=task, window=window)
            return "needs-maintainer"
        attempt += 1
    _move(key, "needs-maintainer", failure[-500:])
    _queue("failed-checks", f"{key} failed its checks or review {attempt} times:\n{failure[-1500:]}", task=task, window=window)
    return "needs-maintainer"


def _run_batch(task, briefs, wt, window, session_dir, worker, worker_index, docs=False) -> dict:
    """The issues in order in one worker context. Each issue's first turn is checked on its done sha in a thread while
    the worker already codes the next one (pipeline.batch-session); a red check is handled (retry turns) before the
    batch goes on, so a failed item blocks the later ones."""
    from concurrent.futures import ThreadPoolExecutor
    out, pending, sess, c = {}, None, [session_dir], cfg()  # pending: (key, future of its first check results, attempts before them)
    first_since = _since(next(iter(briefs)), task) or _head(wt)

    def settle(p):
        k, fut, attempts = p
        out[k] = _run_issue(task, k, briefs[k], wt, window, sess[0], worker, worker_index, first=(None, fut.result(), attempts))
        return out[k]

    with ThreadPoolExecutor(max_workers=1) as pool:
        for k, iss in briefs.items():
            w = c["workers"]
            if coder.status(sess[0])["context"] >= w["context_tokens"] * w["batch_end_pct"] / 100:
                # near the end of the context: a fresh window takes the rest from a short note (a pending check finishes first)
                if pending and settle(pending) != "checked":
                    out[k] = "queued"
                    break
                pending = None
                note = _handoff(task, wt, first_since, len([e for e in journal.read() if e["event"] == "handoff" and e.get("task") == task]) + 1)
                coder.stop_window(c, window)
                journal.append("handoff", task=task, window=window, note=str(note), session=str(sess[0]))
                sess[0] = _start_worker(task, wt, worker, window, docs=docs)
                for rest in list(briefs)[list(briefs).index(k):]:
                    briefs[rest]["handoff"] = str(note)
            since = _since(k, task) or _head(wt)
            journal.append("since", issue=_n(k), key=k, task=task, sha=since)
            it = state()["items"][k]
            end, sha = _turn(task, k, iss, wt, window, sess[0], worker, worker_index, since, it["retry_text"], it["attempts"])
            if pending and settle(pending) != "checked":
                out[k] = "queued"  # blocked behind the failed item; its commit stays on the branch
                break
            pending = None
            if end:
                out[k] = end
                break  # the fallback list: the next worker takes the rest of the batch in a fresh context
            pending = (k, pool.submit(check, k, since, True, sha), it["attempts"])
        if pending:
            settle(pending)
    return out


def check(issue, since: str | None = None, locked: bool = False, sha: str | None = None) -> list[dict]:
    """→ checked only when every rung is green, for the head read BEFORE the checks ran; a commit that lands
    mid-check is a red (the sha moved). Red: a checked or reviewed item goes back to coding (review HIGH N1), a
    pinned-checks red goes to needs-maintainer, a coding item stays for the caller's retry. `sha`: judge this commit
    (an issue's done sha while the worker codes the next one), not the live head."""
    if not locked:
        with journal.Lock("dispatch", wait=False):
            return check(issue, since, locked=True, sha=sha)
    key, it, s = _item(issue)
    wt = Path(s["tasks"][it["task"]]["worktree"])
    since = since or _since(key, it["task"])
    given = sha  # a given sha is judged as it is; the live head must also hold still while its checks run
    sha = sha or _head(wt)
    _wait_room("pytest", it["task"])
    with journal.Lock("test-run"):
        results = checks.run_all(wt, cfg(), since=since, protected_ids=tuple(it["start_args"].get("ids") or ()),
                                approved=it.get("approved_checks"), head=sha)
    if not given and _head(wt) != sha:
        results.append({"name": "head-moved", "ok": False, "seconds": 0, "text": f"a commit landed during the checks ({sha[:9]} -> {_head(wt)[:9]})"})
    ok = bool(results) and all(r["ok"] for r in results)
    journal.append("check", issue=it["issue"], key=key, ok=ok, sha=sha, results=results)
    gh.cache_clear()
    if ok:
        _move(key, "checked", f"{len(results)} rungs green at {sha[:9]}")
    elif results[0]["name"] == "pinned-checks" and not results[0]["ok"]:
        _move(key, "needs-maintainer", results[0]["text"])
    elif it["state"] in ("checked", "reviewed"):
        _move(key, "coding", f"red check at {sha[:9]}: {next(r['name'] for r in results if not r['ok'])}")
    return results


def verdict(issue, sha: str, verdict: str, by: str, findings: str = "") -> dict:
    """checked → reviewed on READY from the reviewer role for the worktree's LIVE head, which must be the sha the
    last check PASSED on; a binding NOT_READY sends the item back to coding with the findings as its retry text and
    counts an attempt. Anything else is recorded only."""
    key, it, s = _item(issue)
    wt = s["tasks"][it["task"]]["worktree"]
    try:
        sha = checks.git(wt, "rev-parse", "--verify", f"{sha}^{{commit}}")
    except RuntimeError:
        pass
    head = _head(wt)
    journal.append("verdict", issue=it["issue"], key=key, sha=sha, verdict=verdict, by=by, findings=findings[:4000])
    binding = by == "reviewer" and sha == head == it["sha"] and it["check_ok"] and it["state"] in ("checked", "reviewed")
    if binding and verdict == "READY":
        if it["state"] == "checked":
            _move(key, "reviewed", f"READY by {by} at {sha[:9]}")
        return {"issue": key, "state": "reviewed"}
    if binding and verdict == "NOT_READY":
        journal.append("retry", issue=it["issue"], key=key, text=f"Review NOT_READY at {sha[:9]}:\n{findings}")
        _move(key, "coding", f"NOT_READY by {by} at {sha[:9]}; `retry {key}` sends the findings to the coder")
        return {"issue": key, "state": "coding", "attempts": it["attempts"] + 1}
    why = "" if sha == head else f"verdict is for {sha[:9]}, head is {head[:9]}: not binding"
    if head != it["sha"] or not it["check_ok"]:
        why = f"head {head[:9]} has not passed a check (last check: {it['sha'][:9]} {'green' if it['check_ok'] else 'red'}): run `check {key}` first"
    return {"issue": key, "state": it["state"], "recorded": verdict, "note": why}


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
    key = next((k for k, it in s["items"].items() if it["task"] == task and it["state"] == "coding"), None)
    qid = _queue("ask", question, options, task=task, window=window, key=key)
    if key:  # the item waits visibly; the window is parked when its turn ends and woken by the answer
        _move(key, "asking", question[:200])
    return {"queued": qid, "note": "end your turn: the maintainer's answer wakes this session with the answer as its next message"}


def done(task: str, issue: int | None = None, residue: str = "") -> dict:
    """Only REQUESTS the check transition: the runner runs the checks when the worker's turn ends. `issue`: the one
    just committed; `residue`: anything the issue's acceptance left undone (the closer updates the issue with it)."""
    journal.append("done_requested", task=task, issue=issue, text=residue)
    return {"ok": True, "note": "the runner runs the checks; nothing moves on your word"}


def queue() -> list[dict]:
    return sorted(state()["queue"].values(), key=lambda q: q["ts"] or "")


def answer(qid: str, text: str, resume: bool = True) -> dict:
    """Journal the answer. An item that asked (state `asking`) is then resumed in the background: its parked window
    is woken with the answer as its next message (`resume_asked`); any other question just tells the window."""
    q = state()["queue"].get(qid)
    if not q:
        raise KeyError(f"no open queue item {qid}")
    journal.append("answer", id=qid, text=text)
    if q.get("key") and state()["items"][q["key"]]["state"] == "asking":
        if resume:
            import threading
            threading.Thread(target=resume_asked, args=(q["key"],), daemon=True).start()
        return {"answered": qid, "resuming": q["key"]}
    if q.get("window"):
        tell(q["window"], f"Answer to your question ({q['text'][:80]}): {text}", task=q.get("task"))
    return {"answered": qid, "told": q.get("window")}


def resume_asked(issue) -> dict:
    """An answered `asking` item continues in the SAME worker session: the parked window is woken with the answer as its
    next message, then the usual checks and review path follow. Everything comes from the journal, so it works after a
    runner or page restart; the dispatch lock keeps a second resume (the page's and the scheduler's) out."""
    with journal.Lock("dispatch", wait=False):
        _require_running()
        key, it, s = _item(issue)
        if it["state"] != "asking" or not it.get("answer"):
            raise RuntimeError(f"{key} is {it['state']}: nothing answered to resume")
        task, wt = it["task"], Path(s["tasks"][it["task"]]["worktree"])
        window = s["tasks"][task]["window"]
        w = s["workers"][window]
        worker = next((x for x in workers() if config.pi_model_id(x) == w["model"]), workers()[0])
        iss = json.loads(Path(it["start_args"]["from_file"]).read_text()) if it["start_args"].get("from_file") else ISSUE(_n(key))
        since = _since(key, task) or _head(wt)
        journal.append("wake", window=window, task=task, milestone=None)
        _move(key, "coding", "answered: waking the worker")
        end, sha = _turn(task, key, iss, wt, window, Path(w["session_dir"]), worker, 0, since, "", it["attempts"], resume=it["answer"])
        results = check(key, since=since, locked=True, sha=sha) if not end else None
        return {"issue": key, "state": end or _run_issue(task, key, iss, wt, window, Path(w["session_dir"]), worker, 0,
                                                          first=(None, results, it["attempts"]))}


def point(milestone: str) -> dict:
    journal.append("point", milestone=milestone)
    return {"point": milestone}


def reset(issue, why: str = "") -> dict:
    """The maintainer zeroes an item's attempts when the reds were the runner's fault, not the coder's."""
    key, it, _ = _item(issue)
    journal.append("reset", issue=it["issue"], key=key, text=why)
    return {"issue": key, "attempts": 0}


def approve_checks(issue, findings: str) -> dict:
    """The maintainer approves the check change that sent an item to needs-maintainer (pinned-checks), records which
    files, and re-dispatches it with the findings as the coder's retry text."""
    key, it, s = _item(issue)
    if it["state"] != "needs-maintainer":
        raise RuntimeError(f"{key} is {it['state']}; approve-checks is for a needs-maintainer item whose diff changes the checks")
    wt = Path(s["tasks"][it["task"]]["worktree"])
    _, _, hit = checks.changed_checks(wt, _since(key, it["task"]), cfg(), approved=it.get("approved_checks"))
    if not hit:
        raise RuntimeError(f"{key}: the diff changes no pinned check; nothing to approve (use `retry`)")
    journal.append("approve_checks", issue=it["issue"], key=key, files=hit, text=findings,
                   blobs={f: checks.blob(wt, "HEAD", f) for f in hit})
    return {"approved": hit, **retry(key)}


def _approved(root=None) -> set[str]:
    specs = Path(root or cfg()["repo"]["path"]) / cfg()["repo"]["specs"]
    return feeder.approved_ids(p.read_text() for p in specs.rglob("*.md"))


def nearest_spec(issue: dict) -> Path | None:
    """The spec file the issue most likely belongs in: one it names (localise), else the one sharing most words with it."""
    root = Path(cfg()["repo"]["path"])
    specs, text = root / cfg()["repo"]["specs"], f"{issue['title']} {issue.get('body') or ''}"
    named = [root / f for f in localise.localise(str(root), text)["files"] if (root / f).is_relative_to(specs) and f.endswith(".md")]
    if named:
        return named[0]
    words = {w for w in re.findall(r"[a-z]{4,}", text.lower())}
    best = max(((len(words & set(re.findall(r"[a-z]{4,}", p.read_text().lower()))), p) for p in sorted(specs.rglob("*.md"))), default=(0, None))
    return best[1] if best[0] else None


def _writeup(task, key, iss, wt, window, session_dir, worker) -> dict:
    """ONE write-up turn for an issue brief-lint refused (pipeline.brief-lint): the small worker, given the issue and
    the nearest spec, answers ID / ACCEPTANCE / TEST. The runner (not the worker) adds the id to that spec as a new [GAP]
    line, committed on the branch before the item's `since`, and never touches an existing line. At most one per issue:
    a later start reuses the journaled answer."""
    n = _n(key)
    prior = [e for e in journal.read() if e["event"] == "writeup" and e["key"] == key]
    if prior:
        return prior[-1]["parts"]
    spec = nearest_spec(iss)
    rel = str(spec.relative_to(cfg()["repo"]["path"])) if spec else "(none found)"
    path = coder.brief_file(task, f"writeup-{n}", "\n".join([
        f"# Write up #{n}: {iss['title']}", "", iss.get("body") or "", "", f"Nearest spec: {rel}", "",
        "The issue lacks a spec behaviour id, an acceptance line or a test path. Do not edit any file. Answer with exactly three "
        "lines and nothing else:", "ID: `area.name` (a NEW lowercase dotted behaviour id, not one already in the spec)",
        "ACCEPTANCE: one sentence a test can check", "TEST: tests/path/test_x.py::test_name"]))
    before = coder.status(session_dir)
    tell(window, f"Read and do {path} — write-up for #{n}. Reply with the three lines; edit nothing.", task=task)
    st = coder.wait_idle(session_dir, cap_for(session_dir), after_turns=before["turns"], token_cap=worker.get("token_cap"))
    journal.append("cost", issue=n, key=key, task=task, session=str(session_dir), usd=round(st["cost_usd"], 4),
                   tokens=st["tokens"], model=st["model"], tools=dict(st["tool_calls"]))
    parts = feeder.parse_writeup(st.get("last_text") or "")
    if spec and parts.get("id") and f"`{parts['id']}`" not in spec.read_text():  # only ever a new [GAP] line, in the worktree
        spec = wt / spec.relative_to(cfg()["repo"]["path"])
        line = f"- `{parts['id']}` [GAP] — {parts.get('acceptance', 'proposed by the write-up worker')}" + (f" Test: {parts['test']}" if parts.get("test") else "")
        spec.write_text(spec.read_text().rstrip("\n") + "\n" + line + "\n")
        checks.git(wt, "add", "--", str(spec))
        checks.git(wt, "-c", "user.name=Claude", "-c", f"user.email={cfg()['github']['agent_email']}", "commit", "-qm",
                   f"spec: proposed [GAP] line for {parts['id']} (write-up of #{n})")
    journal.append("writeup", issue=n, key=key, task=task, parts=parts, spec=rel)
    return parts


def next_issues(count: int = 3) -> dict:
    """What to hand a coder next: the pointed milestone, else the first open one with a ready issue (pipeline.feeder-
    picks-the-milestone). Issues already in a task are skipped; the unfit go to the queue once as "write it up" /
    "triage", never to a coder."""
    c, s = cfg(), state()
    specs = Path(c["repo"]["path"]) / c["repo"]["specs"]
    approved = feeder.approved_ids(p.read_text() for p in specs.rglob("*.md"))
    ms = [s["point"]] if s["point"] else feeder.milestone_order(gh.read("api", "repos/{owner}/{repo}/milestones?state=open"))
    for m in ms:
        found = gh.read("issue", "list", "--milestone", m, "--state", "open", "--limit", "200", "--json", gh.ISSUE_FIELDS)
        issues = [gh._slim(d) for d in found]
        got = feeder.pick(issues, c["labels"], c["github"]["allowed_authors"], approved, {_n(k) for k in s["items"]})
        queued = {q["text"] for q in s["queue"].values()}
        for n, miss in got["write_up"].items():
            text = f"#{n} is not fit to dispatch, write it up: it lacks {'; '.join(miss)}"
            if text not in queued:
                _queue("write-up", text)
        for n in got["triage"]:
            text = f"#{n} is by someone outside the allow-list (or from-user): triage it"
            if text not in queued:
                _queue("triage", text)
        if got["ready"]:
            return {"milestone": m, "ready": [{"number": i["number"], "title": i["title"]} for i in got["ready"][:count]]}
    return {"milestone": s["point"], "ready": []}


def pause() -> dict:
    journal.append("pause")
    return {"paused": True}


def resume(raise_cap: float | None = None) -> dict:
    """Unpause; with `raise_cap`, lift today's daily API cap to that figure (journaled, the maintainer's call)."""
    journal.append("resume")
    if raise_cap is not None:
        journal.append("raise_cap", usd=float(raise_cap))
    return {"paused": False, "daily_cap": daily_cap(), "spend_today": spend_today()}


def _review_base(key: str, task: str, since: str) -> str:
    """Where this issue's own commits start: the sha of the last other issue's done line before this one's first
    (issues of a batch share a branch, so the item's `since` range can hold a neighbour's commit)."""
    base = since
    for e in journal.read():
        if e["event"] == "issue_done" and e.get("task") == task:
            if e["key"] == key:
                return base
            base = e["sha"]
    return since


def review(issue, worker_index: int = 0) -> dict:
    """The reviewer: a Pi window (role reviewer: the ponytail lens, the `verdict` tool) told a brief with the item's
    diff, spec lines and check results, for the item's checked head. It blocks until a verdict for that sha is in
    the journal (or the reviewer stops), then stops the window. Its cost counts toward the item's cap."""
    with journal.Lock("dispatch", wait=False):
        _require_running()
        _require_budget()
        key, it, s = _item(issue)
        if it["state"] != "checked" or not it["check_ok"]:
            raise RuntimeError(f"{key} is {it['state']}: a review needs a green check first")
        c = cfg()
        wt = Path(s["tasks"][it["task"]]["worktree"])
        worker = workers("reviewer")[worker_index]
        window, task = "reviewer", it["task"]
        session = STATE / "sessions" / task / f"reviewer-{worker['model'].replace('/', '_')}-{time.strftime('%Y%m%d-%H%M%S')}"
        session.mkdir(parents=True, exist_ok=True)
        coder.start_window(c, window, wt, coder.pi_command(c, worker, session, role="reviewer", task=task), coder.allowed_env(c, task, "reviewer"))
        journal.append("worker", window=window, task=task, role="reviewer", model=config.pi_model_id(worker), kind="pi",
                       session_dir=str(session), cwd=str(wt))
        since = _review_base(key, task, _since(key, task) or c["repo"]["base"])
        diff = checks.sh(["git", "diff", "--stat", f"{since}...{it['sha']}"], cwd=wt).stdout[-3000:]
        text = "\n".join([f"# Review {key}: {it['title']}", "", f"Head {it['sha']} (checked green: {', '.join(r['name'] for r in it['checks'])}).",
                          f"Diff range: `git diff {since[:9]}...{it['sha'][:9]}`", "```", diff, "```", "",
                          *(["## Spec lines", *spec_lines(set(it["start_args"].get("ids") or []))] if it["start_args"].get("ids") else []),
                          "", "## How to review", "1. Read the diff with jcodemunch and the spec lines with jdocmunch; the spec-diff rule: a behaviour "
                          "change must touch its spec and manual.", "2. Named checks: correctness and regressions, the spec diff, security, "
                          "and the ponytail lens (your rules file).",
                          f"3. Record your verdict ONCE with the `pipeline_verdict` tool: issue `{key}`, sha `{it['sha']}`, READY or NOT_READY, "
                          "by `reviewer`, findings as one line per finding with severity. Nothing else moves the item."])
        path = coder.brief_file(task, f"review-{it['sha'][:9]}", text)
        before = coder.status(session)
        tell(window, f"Read and do {path} — review {key} at {it['sha'][:9]}; record your verdict with pipeline_verdict.", task=task)
        st = coder.wait_idle(session, cap_for(session), after_turns=before["turns"])
        journal.append("cost", issue=it["issue"], key=key, task=task, session=str(session), usd=round(st["cost_usd"], 4),
                       tokens=st["tokens"], model=st["model"], tools=dict(st["tool_calls"]))
        coder.stop_window(c, window)
        journal.append("worker_gone", window=window, task=task, why=st.get("stopped") or "review done")
        it = state()["items"][key]
        return {"issue": key, "state": it["state"], "verdict": it.get("verdict_now"), "reviewer_cost_usd": round(st["cost_usd"], 4),
                "stopped": st.get("stopped")}


STEP = re.compile(r"^#### Step [\d.]+ .*$", re.MULTILINE)


def unfiled_steps(milestone: str) -> list[str]:
    """Build-order steps (`#### Step N.M — title`, no `(#NNNN)`) in the specs whose header names this milestone."""
    c = cfg()
    out = []
    for p in (Path(c["repo"]["path"]) / c["repo"]["specs"]).rglob("*.md"):
        text = p.read_text()
        if f"Milestone: {milestone}" in "\n".join(text.splitlines()[:20]):
            out += [m for m in STEP.findall(text) if not re.search(r"\(#\d+\)\s*$", m)]
    return out


def _reopened_after(closer, n: int, date: str) -> bool:
    """A human reopened the issue after the fixing commit (the closer script's rule, read through the one gh seam)."""
    events = gh.read("api", f"repos/{{owner}}/{{repo}}/issues/{n}/events?per_page=100")
    return any(e.get("event") == "reopened" and closer._when(e["created_at"]) > closer._when(date) for e in events if e.get("created_at"))


def close_landed() -> dict:
    """The closer (pipeline.closes-issues): an item whose checked commit is on the base branch and whose last check was
    green gets its issue closed through scripts/close_fixed_issues.py's own rules (never `residue` or `needs-your-test`,
    never one a human reopened) with a comment naming the sha and the checks; a reported residue is posted on the
    issue, which gets the residue label and stays open; a milestone closes with its last open issue. Every write is
    dry-run unless --apply, and a dry-run line is journaled before the real one. A milestone whose spec still has build
    steps without an issue stays open."""
    import importlib.util
    c, lab = cfg(), cfg()["labels"]
    spec = importlib.util.spec_from_file_location("close_fixed_issues", ROOT / "scripts" / "close_fixed_issues.py")
    closer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(closer)
    out, touched = {"closed": [], "residue": [], "milestones": []}, {}
    for key, it in state()["items"].items():
        if it.get("closer") or it["start_args"].get("from_file") or not it["check_ok"] or not it["sha"]:
            continue
        if checks.sh(["git", "merge-base", "--is-ancestor", it["sha"], c["repo"]["base"]], cwd=c["repo"]["path"]).returncode:
            continue  # not on the base branch yet
        n = _n(key)
        gh.cache_clear()
        iss = gh.read("issue", "view", str(n), "--json", "state,labels,milestone,comments")
        names = {x["name"] for x in iss["labels"]}
        if iss["state"] != "OPEN" or names & {lab["residue"], "needs-your-test"}:
            continue
        if closer.owes_more((iss.get("comments") or [{}])[-1].get("body")):
            continue  # its last comment says what is left
        subject = checks.git(c["repo"]["path"], "log", "-1", "--format=%s", it["sha"])
        if it.get("residue"):
            write = [["issue", "comment", str(n), "--body", f"Landed in {it['sha'][:9]}, but this is still owed:\n\n{it['residue']}"],
                     ["issue", "edit", str(n), "--add-label", lab["residue"]]]
            what = "residue"
        elif n not in closer.cited(checks.git(c["repo"]["path"], "log", "-1", "--format=%B", it["sha"])):
            continue  # the commit only says "Part of": it does not claim to finish the issue (a residue is still posted)
        elif not _reopened_after(closer, n, checks.git(c["repo"]["path"], "log", "-1", "--format=%cI", it["sha"])):
            rungs = ", ".join(r["name"] for r in it["checks"])
            write = [["issue", "close", str(n), "--comment", f"Fixed in {it['sha'][:9]} on integration: {subject}. Checks green: {rungs}."]]
            what = "closed"
        else:
            continue  # a human reopened it after the fix: it did not hold
        for args in write:
            gh.write(*args, dry_run=True)  # the dry-run line first, then the real one
            if not DRY_RUN:
                gh.write(*args, dry_run=False)
        if not DRY_RUN:
            journal.append("closer", issue=n, key=key, what=what, sha=it["sha"])
        out["closed" if what == "closed" else "residue"].append(n)
        if what == "closed" and (m := (iss.get("milestone") or {}).get("title")):
            touched[m] = touched.get(m, 0) + 1
    for m in gh.read("api", "repos/{owner}/{repo}/milestones?state=open") if touched else []:
        if unfiled_steps(m["title"]):
            continue  # a spec of this milestone still has build steps with no issue: not finished
        if m["title"] in touched and m["open_issues"] <= touched[m["title"]] and m["closed_issues"] + touched[m["title"]] >= 1:
            gh.write("api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/milestones/{m['number']}", "-f", "state=closed", dry_run=DRY_RUN)
            out["milestones"].append(m["title"])
    return out


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
API = {"status": status, "start": start, "retry": retry, "approve_checks": approve_checks, "repair": repair, "check": check, "review": review, "verdict": verdict,
       "tell": tell, "report": report, "ask": ask, "resume_asked": resume_asked, "done": done, "queue": queue, "answer": answer, "point": point, "next": next_issues, "pause": pause,
       "resume": resume, "file_bug": file_bug, "close_landed": close_landed, "reset": reset}
# Per-role MCP tools (pipeline.three-faces): approve/answer are never over MCP. Every worker role is SERVED the same
# list (WORKER_TOOLS, one order, so the prompt prefix caches); a tool outside the role's own refuses at call time.
WORKER_TOOLS = ("report", "ask", "done", "verdict")
ROLE_TOOLS = {"coder": ("report", "ask", "done"), "reviewer": ("verdict", "report"),
              "manager": ("status", "start", "retry", "check", "review", "tell", "file_bug", "point", "next", "queue", "report")}
# What a worker's shell may never run through the CLI (pipeline.jailed-agent, until the write jail exists).
WORKER_FORBIDDEN = ("verdict", "approve_checks", "answer", "start", "retry", "repair", "check", "review", "pause", "resume", "resume_asked", "point", "tell", "reset", "close_landed")
