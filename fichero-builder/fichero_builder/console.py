"""`builder status`: the owner's console (dev-workflows.run.loop-status, Console). A stdlib server on 127.0.0.1:
GET / (console.html), GET /api/status (journal + queue.json), GET /api/events (an SSE tail of the journal), POST /api/action
(an allow-list onto the existing verbs, nothing else). Every action writes one `console` row: who, the verb, its exit.
A POST needs the token the page was served with and a loopback Host, so another site in the browser cannot drive it.
ponytail: a Tailscale bind comes later, behind the same token."""
from __future__ import annotations

import getpass
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

from fichero_builder import journal, queue, watch

ROOT = Path.cwd()  # set by main: the checkout whose harness.toml the verbs read
TOKEN = secrets.token_urlsafe(24)
PAGE = Path(__file__).with_name("console.html")
PKG = Path(__file__).resolve().parents[1]
LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


def _builder(*args: str) -> list[str]:
    return [sys.executable, "-m", "fichero_builder", *args]


def _st() -> list[str]:
    return ["--state", str(journal.STATE)]


def _plist() -> str:
    return str(Path.home() / "Library" / "LaunchAgents" / "local.builder.loop.plist")


# verb -> (the argument names it takes, argv from them). Values are checked in `argv_for`: text only, never a flag.
VERBS = {
    "pause": (("lane",), lambda a: _builder("queue", "pause", "--lane", a["lane"], *_st())),
    "resume": (("lane",), lambda a: _builder("queue", "resume", "--lane", a["lane"], "--root", str(ROOT), *_st())),
    "stop": (("lane",), lambda a: _builder("queue", "stop", "--lane", a["lane"], *_st())),
    "loop-start": ((), lambda a: ["launchctl", "bootstrap", f"gui/{os.getuid()}", _plist()]),
    "loop-stop": ((), lambda a: ["launchctl", "bootout", f"gui/{os.getuid()}/local.builder.loop"]),
    "alert": (("id", "action"), lambda a: _builder("alert", a["id"], a["action"], "--root", str(ROOT), *_st())),
    "build": ((), lambda a: _builder("build", "--dev", "--root", str(ROOT), *_st())),
    "done": (("lane", "sha"), lambda a: _builder("done", a["lane"], a["sha"], *_st())),
    "start-milestone": (("milestone",), lambda a: _builder("milestone", a["milestone"], "--enqueue", "--repo-dir", str(ROOT), *_st(),
                                                          "--out", str(journal.STATE / f"briefs-{queue.slug(a['milestone'])}"))),
    "order": (("file",), lambda a: _builder("order", "--file", a["file"], "--root", str(ROOT), *_st())),
    "sweep": (("worktree",), lambda a: _builder("sweep", "--worktree", a["worktree"], "--root", str(ROOT), *_st())),
    "queue-add": (("lane", "worktree", "step", "brief", "issues", "kind"),
                  lambda a: _builder("queue", "add", "--lane", a["lane"], "--worktree", a["worktree"], "--step", a["step"], "--brief", a["brief"],
                                     "--kind", a.get("kind") or "worker", *_st(), "--issues", *a.get("issues", []))),
}
OPTIONAL = {"issues", "kind"}


def argv_for(verb: str, args: dict) -> list[str]:
    """The verb's argv, or ValueError: an unlisted verb, a missing argument, or a value that is not plain text."""
    if verb not in VERBS:
        raise ValueError(f"{verb!r} is not a console verb")
    names, make = VERBS[verb]
    clean: dict = {}
    for n in names:
        v = args.get(n)
        if v is None or v == "":
            if n in OPTIONAL:
                continue
            raise ValueError(f"{verb} needs {n}")
        vals = v if isinstance(v, list) else [v]
        for x in vals:
            if not isinstance(x, (str, int)) or str(x).startswith("-") or "\0" in str(x) or not str(x).strip():
                raise ValueError(f"{verb}: {n} must be plain text, never a flag")
        clean[n] = [str(x) for x in vals] if isinstance(v, list) else str(v)
    return make(clean)


def run_verb(argv: list[str]) -> tuple[int, str]:  # the tests replace this
    try:
        r = subprocess.run(argv, capture_output=True, text=True, cwd=str(PKG), env={**os.environ, "PYTHONPATH": str(PKG)}, timeout=7200)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr)[-2000:]


def act(verb: str, args: dict, who: str) -> dict:
    """One action: refused (a row) or started in a thread whose exit is a second row; returns at once."""
    try:
        argv = argv_for(verb, args)
    except ValueError as e:
        journal.append("console", who=who, verb=verb, ok=False, state="refused", detail=str(e))
        return {"ok": False, "error": str(e)}
    journal.append("console", who=who, verb=verb, state="started", args={k: v for k, v in args.items() if k in VERBS[verb][0]})

    def go():
        rc, out = run_verb(argv)
        _TREES.clear()  # a Clean up (or any action) shows at once
        journal.append("console", who=who, verb=verb, state="ended", ok=rc == 0, rc=rc, detail=out[-500:])
    t = threading.Thread(target=go, daemon=True)
    t.start()
    return {"ok": True, "started": verb, "thread": t}


def _last_commit(worktree: str) -> tuple[str, int]:
    """("<sha> <subject> (<age>)", its commit time) of the worktree's HEAD; ("", 0) when unreadable."""
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", worktree, "log", "-1", "--format=%ct %h %s (%cr)"], capture_output=True, text=True)
    ct, _, text = r.stdout.strip().partition(" ")
    return (text, int(ct)) if r.returncode == 0 and ct.isdigit() else ("", 0)


def _title(brief: str) -> str:
    """A heading of the brief, else its first line that is not the RULES preamble, to its first full stop."""
    try:
        lines = [ln.strip() for ln in Path(brief).read_text().splitlines() if ln.strip()]
    except OSError:
        return ""
    head = next((ln.lstrip("# ") for ln in lines if ln.startswith("#")), None)
    first = head or next((ln for ln in lines if not ln.upper().startswith("RULES")), "")
    return first.split(". ")[0][:120]


def _head(brief: str, n: int = 3000) -> str:
    try:
        return Path(brief).read_text()[:n]
    except OSError:
        return ""


_PROGRESS: dict = {}  # (worktree, head) -> progress: a commit's step never changes


def progress(worktree: str, step: str = "", milestone: str = "") -> dict:
    """{step, i, n, spec, milestone} for a lane: the step given (a worker lane's queue step), else the newest commit's
    `Step X.Y` or the step whose Build order section names its `Behaviour:` id (an external lane, re-read each call).
    N is the spec's build order, read from the lane's own worktree. {} when nothing says."""
    from fichero_builder import milestone as ms
    head = _git_text(worktree, "rev-parse", "HEAD").strip()
    if (worktree, head, step) in _PROGRESS:
        return _PROGRESS[(worktree, head, step)]
    msg = _git_text(worktree, "log", "-1", "--format=%B")
    beh = re.search(r"^Behaviour:\s*`?([a-z][\w.-]+\.[\w.-]+)", msg, re.M)
    out: dict = {}
    spec = ""
    if beh:
        spec = next(iter(_git_text(worktree, "grep", "-l", "-F", f"`{beh.group(1)}`", "--", "docs/contributor_manual/specs").split()), "")
    if not spec and milestone:
        from fichero_builder import triage
        spec = next((str(triage.SPECS / sp) for name, sp in triage.ORDER_LINE.findall((Path(worktree) / triage.BUILD_ORDER).read_text())
                     if queue.slug(name) == milestone and sp), "") if (Path(worktree) / triage.BUILD_ORDER).is_file() else ""
    st = step or (m.group(1) if (m := re.search(r"\bStep (\d+\.\d+)", msg)) else "")
    if spec:
        try:
            order = ms.build_order(Path(worktree) / spec)
            text = (Path(worktree) / spec).read_text()
            if not st and beh:  # the step whose section names the behaviour
                sec = text.split("Build order", 1)[-1]
                for part in re.split(r"(?m)^#### Step ", sec)[1:]:
                    if f"`{beh.group(1)}`" in part:
                        st = part.split()[0]
                        break
            nums = [o["number"] for o in order]
            out = {"step": st, "i": nums.index(st) + 1 if st in nums else None, "n": len(nums), "spec": spec, "milestone": ms.spec_slug(Path(worktree) / spec)}
        except (ValueError, OSError):
            out = {"step": st, "spec": spec}
    elif st:
        out = {"step": st}
    _PROGRESS[(worktree, head, step)] = out
    return out


WORKING_S = 15 * 60  # an external lane whose HEAD moved this recently is working
LOOP_STALE_S = 3 * 30  # three ticks: no tick row since = the loop is off


def api_status(rows: list[dict], lanes: list[dict], now: float | None = None, commit=_last_commit) -> dict:
    """watch.status plus the last review, the heartbeat, and per lane: its steps, the step now (id + title), elapsed since it
    was sent, the worker's spend and turns, its last commit, and the lane's last row."""
    now = now or time.time()
    st = watch.status(rows, lanes)
    reviews = [r for r in rows if r.get("event") == "landed" and r.get("step") == "verdict"]
    ticks = [r for r in rows if r.get("event") == "loop" and r.get("state") == "tick"]
    st["last_review"] = {k: reviews[-1].get(k) for k in ("ts", "sha", "ok", "detail")} if reviews else None
    st["heartbeat"] = ticks[-1]["ts"] if ticks else None
    st["loop_on"] = bool(ticks) and now - time.mktime(time.strptime(ticks[-1]["ts"], "%Y-%m-%dT%H:%M:%S")) <= LOOP_STALE_S
    st["console"] = [r for r in rows if r.get("event") == "console"][-20:]
    st["loop_lanes"] = LOOP_LANES
    st["order_saving"] = any(x["id"] == "build-order" and any(s["state"] != "landed" for s in x["steps"]) for x in lanes)
    by_id = {x["id"]: x for x in lanes}
    for row in st["lanes"]:
        x = by_id[row["lane"]]
        cur = x["steps"][x["cursor"]] if x["cursor"] < len(x["steps"]) else None
        sent = [r for r in rows if r.get("event") == "queue" and r.get("lane") == x["id"] and r.get("state") == "sent"]
        cost = [r for r in rows if r.get("event") == "cost" and r.get("task") == x["id"]]
        mine = [r for r in rows if r.get("lane") == x["id"] or r.get("task") == x["id"]]
        started = time.mktime(time.strptime(sent[-1]["ts"], "%Y-%m-%dT%H:%M:%S")) if sent and cur and cur["state"] not in ("queued", "blocked") else None
        last, ct = commit(x["worktree"]) if Path(x["worktree"]).is_dir() else ("", 0)
        if x.get("kind") == "external" and row["state"] == "queued":  # no worker of ours: its own commits say whether it works
            row["state"] = "working" if ct and now - ct <= WORKING_S else "idle"
        if Path(x["worktree"]).is_dir():
            pr = progress(x["worktree"], "" if x.get("kind") == "external" else (cur or {}).get("step", ""), x["id"])
            if x.get("kind") == "external" and pr.get("step"):
                row["step"] = f"Step {pr['step']}"  # its own newest commit says where it is (the queue's step is the batch's name)
            row["progress"] = pr
        row.update(
            worktree=x["worktree"], title=_title(cur["brief"]) if cur else "", brief_text=_head(cur["brief"]) if cur else "",
            commit_ts=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ct)) if ct else "",
            steps=[{"step": s["step"], "state": s["state"], "issues": s["issues"], "why": s["why"][:300]} for s in x["steps"]],
            elapsed_s=int(now - started) if started else None,
            usd=round(sum(float(r.get("usd") or 0) for r in cost), 2), turns=cost[-1].get("turns") if cost else None,
            tokens=cost[-1].get("tokens") if cost else None,
            last_commit=last,
            doing=(mine[-1].get("state") or mine[-1].get("event", "")) + (f": {str(mine[-1].get('detail', ''))[:160]}" if mine and mine[-1].get("detail") else "") if mine else "")
    return st


SECTIONS = ("In order", "Then", "Parked")  # Then: an older file; the owner's list is In order + Parked
RANK = ("open", "in progress", "built, waiting to land", "landed", "released")


def _cited(log: str) -> list[tuple[str, str, int]]:
    """(sha, kind, issue) for every `Fixes|Closes|Part of #N` line of a `git log --format=%x1e%H%x00%B` text."""
    from fichero_builder.landed import ISSUE_LINES
    out = []
    for rec in log.split("\x1e"):
        sha, _, body = rec.partition("\x00")
        out += [(sha.strip(), m.group(1).lower(), int(m.group(2))) for m in ISSUE_LINES.finditer(body)]
    return out


def statuses(open_ns: set, closed_ns: set, branches: dict, landing_log: str, unreleased: set) -> dict:
    """{issue: (status, where)}. `branches`: {lane: its unlanded log text}; `landing_log`: the land branch's log;
    `unreleased`: the land branch's shas not on main. A closed issue is landed, released when its Fixes commit is on main."""
    landing = {n: sha for sha, kind, n in _cited(landing_log) if kind in ("fixes", "closes")}
    built: dict = {}
    for lane, log in branches.items():
        for sha, kind, n in _cited(log):
            st = "built, waiting to land" if kind in ("fixes", "closes") else "in progress" if kind == "part of" else None
            if st and (n not in built or RANK.index(st) > RANK.index(built[n][0])):
                built[n] = (st, f"{lane} {sha[:9]}")
    out = {}
    for n in open_ns:
        out[n] = built.get(n, ("open", ""))
    for n in closed_ns:
        sha = landing.get(n, "")
        out[n] = ("released" if sha and sha not in unreleased else "landed", sha[:9])
    return out


def _git_text(repo: str, *args: str) -> str:
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", repo, *args], capture_output=True, text=True, timeout=120)
    return r.stdout if r.returncode == 0 else ""


def git_reads(root, lanes: list[dict], branch: str) -> tuple[dict, str, set]:
    """The unlanded log of every lane's worktree, the land branch's log (90 days) and its shas not on main."""
    _git_text(str(root), "fetch", "-q", "origin", branch, "main")
    fmt = "--format=%x1e%H%x00%B"
    branches = {x["id"]: _git_text(x["worktree"], "log", fmt, f"origin/{branch}..HEAD") for x in lanes if Path(x["worktree"]).is_dir()}
    # the landing queue: every branch worktree of the repo (land-*, lanes started by hand) with unlanded commits.
    # ponytail: commits of the last 7 days only, so the hundreds of stale branches from before the history rewrite never count
    for block in _git_text(str(root), "worktree", "list", "--porcelain").strip().split("\n\n"):
        f = dict((ln.split(" ", 1) + [""])[:2] for ln in block.splitlines())
        name = f.get("branch", "").removeprefix("refs/heads/")
        if name and name not in (branch, "main") and name not in branches:
            if log := _git_text(f["worktree"], "log", fmt, "--since=7.days", f"origin/{branch}..HEAD"):
                branches[name] = log
    landing = _git_text(str(root), "log", fmt, "--since=90.days", f"origin/{branch}")
    unreleased = set(_git_text(str(root), "rev-list", f"origin/main..origin/{branch}").split())
    return branches, landing, unreleased


def milestones(root, gh: str = "gh", lanes: list[dict] | None = None, reads=None, closed=None) -> dict:
    """The build-order list by section, each milestone's open/closed counts (one gh call), and for an In order one with a
    spec its steps from the `builder milestone` plan (done / running / next / waiting) and questions, and its open issues
    with labels and the step that names them. Read through gh only here: the console serves the cached copy."""
    from fichero_builder import milestone as ms
    from fichero_builder import triage

    text = (Path(root) / triage.BUILD_ORDER).read_text()
    r = subprocess.run([gh, "api", "repos/{owner}/{repo}/milestones?state=all&per_page=100", "--paginate"], capture_output=True, text=True,
                       timeout=120, cwd=str(root))
    counts = {m["title"]: (m["open_issues"], m["closed_issues"]) for m in json.loads(r.stdout or "[]")} if r.returncode == 0 else {}
    held = {x["id"]: x for x in (lanes if lanes is not None else queue.load())}
    try:
        import tomllib
        branch = tomllib.loads((Path(root) / "harness.toml").read_text()).get("land", {}).get("branch", "integration")
    except (OSError, ValueError):
        branch = "integration"
    branches, landing, unreleased = reads(root, list(held.values()), branch) if reads else git_reads(root, list(held.values()), branch)
    out = []
    for sec in SECTIONS:
        body = next((part.split("\n", 1)[1] for part in text.split("\n## ")[1:] if part.startswith(sec)), "")
        specs = dict(triage.ORDER_LINE.findall(body)) if sec == "In order" else {}
        for name in dict.fromkeys(re.findall(r"`([^`]+)`", body)):
            o, c = counts.get(name, (None, None))
            m = {"name": name, "section": sec, "open": o, "closed": c, "spec": specs.get(name, ""), "steps": [], "questions": [], "issues": [],
                 "lane": queue.slug(name) if queue.slug(name) in held else ""}
            if sec == "In order" and m["spec"] and o:
                try:
                    issues = ms.list_issues(name, gh=gh)
                    shut = closed(name) if closed else _closed_issues(name, gh)
                    sp = Path(root) / triage.SPECS / m["spec"]
                    order, slug = ms.build_order(sp), ms.spec_slug(sp)
                    planned = ms.plan(issues, order, slug)
                    every = ms.plan(issues + shut, order, slug)  # closed ones too: a step's status needs all its issues
                except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as e:
                    m["questions"] = [f"could not plan: {e}"]
                    out.append(m)
                    continue
                lane = held.get(m["lane"]) or {"steps": []}
                live = {s["step"]: s["state"] for s in lane["steps"]}
                open_steps = {c["step"]: c for c in planned["clusters"]}
                nxt = next((c["step"] for c in planned["clusters"] if not c["waits"] and live.get(c["step"]) in (None, "queued")), None)
                status = statuses({i["number"] for i in issues}, {i["number"] for i in shut}, branches, landing, unreleased)
                all_steps = {c["step"]: c for c in every["clusters"]}
                for st in order:
                    c = open_steps.get(st["number"])
                    state = ("done" if c is None else "running" if live.get(st["number"]) not in (None, "queued", "landed", "blocked")
                             else "question" if live.get(st["number"]) == "blocked" else "next" if st["number"] == nxt else "waiting")
                    ns = [i["number"] for i in all_steps[st["number"]]["issues"]] if st["number"] in all_steps else []
                    low = min((status[n][0] for n in ns), key=RANK.index, default="")
                    m["steps"].append({"step": st["number"], "title": st["title"], "state": state, "status": low,
                                       "issues": [i["number"] for i in c["issues"]] if c else []})
                m["questions"] = planned["questions"]
                m["issues"] = [{"number": i["number"], "title": i["title"], "labels": [lb.get("name", "") for lb in i.get("labels") or []],
                                "step": ms.step_of(i, slug) or "", "status": status[i["number"]][0], "where": status[i["number"]][1]} for i in issues]
                m["counts"] = {k: sum(1 for v in status.values() if v[0] == k) for k in RANK}
                if not m["lane"]:  # a lane named otherwise holds it when its commits cite the milestone's issues
                    m["lane"] = next((w.split()[0] for st_, w in status.values() if st_ in RANK[1:3] and w.split()[0] in held), "")
                m["startable"] = not m["lane"] and any(x["status"] == "open" for x in m["steps"])
                m["held_by"] = "Lane running" if m["lane"] else ("" if m["startable"] else "Built, waiting to land" if m["counts"]["built, waiting to land"] else "")
            out.append(m)
    return {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "milestones": out, "gh_ok": r.returncode == 0}


def _closed_issues(name: str, gh: str) -> list[dict]:
    r = subprocess.run([gh, "issue", "list", "--milestone", name, "--state", "closed", "--limit", "500", "--json", "number,title,body,labels"],
                       capture_output=True, text=True, timeout=120)
    return json.loads(r.stdout) if r.returncode == 0 else []


def _ts(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)) if t else ""


def worktrees(root, git=_git_text) -> dict:
    """Every worktree of the owner's checkout and of the jail root: branch, last commit, dirty, landed (HEAD on origin/<land
    branch>), the sweep's grace deadline, and whether Clean up is offered (landed, clean, not a main tree, no lane in it)."""
    import tomllib
    from fichero_builder import landed
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    branch, grace = doc.get("land", {}).get("branch", "integration"), float(doc.get("land", {}).get("worktree_grace_hours", 36))
    workroot = doc.get("jail", {}).get("workroot", "")
    live = landed.live_worktrees()
    todo = []
    for repo, where in ((str(root), "checkout"), (f"{workroot}/root", "jail")) if workroot else ((str(root), "checkout"),):
        blocks = git(repo, "worktree", "list", "--porcelain").strip().split("\n\n")
        for k, block in enumerate(b for b in blocks if b.strip()):
            f = dict((ln.split(" ", 1) + [""])[:2] for ln in block.splitlines())
            if f.get("worktree") and Path(f["worktree"]).is_dir():
                todo.append((repo, where, k, f))

    def one(item) -> dict:
        repo, where, k, f = item
        wt = f["worktree"]
        ct = int((git(wt, "log", "-1", "--format=%ct").strip() or "0"))
        dirty = bool(git(wt, "status", "--porcelain").strip())
        landed_ = bool(f.get("HEAD")) and subprocess.run(["git", "-c", "safe.directory=*", "-C", repo, "merge-base", "--is-ancestor", f["HEAD"], f"origin/{branch}"],
                                                         capture_output=True).returncode == 0
        return ({"path": wt, "where": where + (" (main tree)" if k == 0 else ""), "branch": f.get("branch", "").removeprefix("refs/heads/"),
                    "commit_ts": _ts(ct), "dirty": dirty, "landed": landed_, "grace_until": _ts(ct + grace * 3600) if k and ct else "",
                    "can_clean": k > 0 and landed_ and not dirty and os.path.realpath(wt) not in live and os.path.realpath(wt) != os.path.realpath(root)})
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:  # git status of ~35 trees one by one took 25 s
        out = list(pool.map(one, todo))
    return {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "trees": out}


_TREES: dict = {}  # {"at": time, "data": ...}: a minute's cache; a console action (a Clean up) clears it


def worktrees_cached(root) -> dict:
    if not _TREES or time.time() - _TREES["at"] > 60:
        _TREES.update(at=time.time(), data=worktrees(root))
    return _TREES["data"]


def _cache() -> Path:
    return journal.STATE / "console-milestones.json"


def refresh(who: str) -> threading.Thread:
    """Recompute the milestones cache in a thread; a console row each way."""
    journal.append("console", who=who, verb="refresh", state="started")

    def go():
        try:
            data = milestones(ROOT)
            _cache().write_text(json.dumps(data))
            journal.append("console", who=who, verb="refresh", state="ended", ok=True, rc=0, detail=f"{len(data['milestones'])} milestones")
        except Exception as e:  # noqa: BLE001 - a row, never a dead thread
            journal.append("console", who=who, verb="refresh", state="ended", ok=False, rc=1, detail=str(e)[-500:])
    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t


def _json(h, code: int, body) -> None:
    b = json.dumps(body, default=str).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


class Handler(http.server.BaseHTTPRequestHandler):
    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "").rsplit(":", 1)[0] in LOOPBACK

    def do_GET(self):
        path = self.path.split("?")[0]
        if not self._host_ok():
            return _json(self, 403, {"error": "a loopback Host only"})
        if path == "/":
            b = PAGE.read_text().replace("__TOKEN__", TOKEN).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        if path in ("/api/status", "/status.json"):
            return _json(self, 200, api_status(watch.rows_of(ROOT), queue.load()))
        if path == "/api/milestones":
            try:
                return _json(self, 200, json.loads(_cache().read_text()))
            except (OSError, ValueError):
                return _json(self, 200, {"ts": None, "milestones": []})
        if path == "/api/worktrees":
            return _json(self, 200, worktrees_cached(ROOT))
        if path == "/api/events":
            return self._events()
        return _json(self, 404, {"error": "not found"})

    def _events(self):
        """Each new journal line as one SSE `data:` event; a comment line every 15 s keeps the stream open."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        p, pos, idle = journal.path(), journal.path().stat().st_size if journal.path().exists() else 0, 0
        try:
            while True:
                size = p.stat().st_size if p.exists() else 0
                if size < pos:
                    pos = 0  # rotated
                if size > pos:
                    with p.open("rb") as f:
                        f.seek(pos)
                        chunk = f.read(size - pos)
                    pos = size
                    for ln in chunk.decode(errors="replace").splitlines():
                        if ln.strip():
                            self.wfile.write(f"data: {ln}\n\n".encode())
                    self.wfile.flush()
                    idle = 0
                elif (idle := idle + 1) >= 15:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    idle = 0
                time.sleep(EVENT_POLL_S)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Builder-Token") != TOKEN:
            journal.append("console", who="?", verb=self.path, ok=False, state="refused", detail="no token or a foreign Host")
            return _json(self, 403, {"error": "the console's token and a loopback Host are required"})
        if self.path.split("?")[0] == "/api/order":  # the owner's reorder: the body to a file, then the `order` verb
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                req = journal.STATE / f"order-request-{int(time.time())}.json"
                req.write_text(json.dumps({"order": [str(x) for x in body["order"]], "parked": [str(x) for x in body.get("parked", [])]}))
            except (ValueError, KeyError, TypeError):
                return _json(self, 400, {"error": "order needs {order: [...], parked: [...]}"})
            r = act("order", {"file": str(req)}, f"{getpass.getuser()}@console")
            r.pop("thread", None)
            return _json(self, 200 if r["ok"] else 400, r)
        if self.path.split("?")[0] == "/api/refresh":
            refresh(f"{getpass.getuser()}@console")
            return _json(self, 200, {"ok": True, "started": "refresh"})
        if self.path.split("?")[0] != "/api/action":
            return _json(self, 404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return _json(self, 400, {"error": "not JSON"})
        who = f"{getpass.getuser()}@console"
        r = act(str(body.get("verb", "")), body.get("args") or {}, who)
        r.pop("thread", None)
        return _json(self, 200 if r["ok"] else 400, r)

    def log_message(self, *a):
        pass


EVENT_POLL_S = 1.0
LOOP_LANES = 1  # [loop].lanes, read by main: the page starts no more lanes than this


def server(host: str, port: int) -> http.server.ThreadingHTTPServer:
    s = http.server.ThreadingHTTPServer((host, port), Handler)
    s.daemon_threads = True
    return s


def main(a) -> int:
    global ROOT
    global LOOP_LANES
    ROOT = Path(a.root)
    try:
        import tomllib
        LOOP_LANES = int(tomllib.loads((ROOT / "harness.toml").read_text()).get("loop", {}).get("lanes", 1))
    except (OSError, ValueError):
        pass
    srv = server("127.0.0.1", a.port)
    print(f"the builder console at http://127.0.0.1:{srv.server_address[1]}/ (Ctrl-C stops)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
