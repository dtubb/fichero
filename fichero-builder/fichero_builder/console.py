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
        journal.append("console", who=who, verb=verb, state="ended", ok=rc == 0, rc=rc, detail=out[-500:])
    t = threading.Thread(target=go, daemon=True)
    t.start()
    return {"ok": True, "started": verb, "thread": t}


def _last_commit(worktree: str) -> str:
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", worktree, "log", "-1", "--format=%h %s (%cr)"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _title(brief: str) -> str:
    try:
        return next((ln.lstrip("# ").strip() for ln in Path(brief).read_text().splitlines() if ln.strip()), "")[:120]
    except OSError:
        return ""


def api_status(rows: list[dict], lanes: list[dict], now: float | None = None, commit=_last_commit) -> dict:
    """watch.status plus the last review, the heartbeat, and per lane: its steps, the step now (id + title), elapsed since it
    was sent, the worker's spend and turns, its last commit, and the lane's last row."""
    now = now or time.time()
    st = watch.status(rows, lanes)
    reviews = [r for r in rows if r.get("event") == "landed" and r.get("step") == "verdict"]
    ticks = [r for r in rows if r.get("event") == "loop" and r.get("state") == "tick"]
    st["last_review"] = {k: reviews[-1].get(k) for k in ("ts", "sha", "ok", "detail")} if reviews else None
    st["heartbeat"] = ticks[-1]["ts"] if ticks else None
    st["console"] = [r for r in rows if r.get("event") == "console"][-20:]
    st["loop_lanes"] = LOOP_LANES
    by_id = {x["id"]: x for x in lanes}
    for row in st["lanes"]:
        x = by_id[row["lane"]]
        cur = x["steps"][x["cursor"]] if x["cursor"] < len(x["steps"]) else None
        sent = [r for r in rows if r.get("event") == "queue" and r.get("lane") == x["id"] and r.get("state") == "sent"]
        cost = [r for r in rows if r.get("event") == "cost" and r.get("task") == x["id"]]
        mine = [r for r in rows if r.get("lane") == x["id"] or r.get("task") == x["id"]]
        started = time.mktime(time.strptime(sent[-1]["ts"], "%Y-%m-%dT%H:%M:%S")) if sent and cur and cur["state"] not in ("queued", "blocked") else None
        row.update(
            worktree=x["worktree"], title=_title(cur["brief"]) if cur else "",
            steps=[{"step": s["step"], "state": s["state"], "issues": s["issues"], "why": s["why"][:300]} for s in x["steps"]],
            elapsed_s=int(now - started) if started else None,
            usd=round(sum(float(r.get("usd") or 0) for r in cost), 2), turns=cost[-1].get("turns") if cost else None,
            tokens=cost[-1].get("tokens") if cost else None,
            last_commit=commit(x["worktree"]) if Path(x["worktree"]).is_dir() else "",
            doing=(mine[-1].get("state") or mine[-1].get("event", "")) + (f": {str(mine[-1].get('detail', ''))[:160]}" if mine and mine[-1].get("detail") else "") if mine else "")
    return st


SECTIONS = ("In order", "Then", "Parked")


def milestones(root, gh: str = "gh", lanes: list[dict] | None = None) -> dict:
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
                    sp = Path(root) / triage.SPECS / m["spec"]
                    order, slug = ms.build_order(sp), ms.spec_slug(sp)
                    planned = ms.plan(issues, order, slug)
                except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as e:
                    m["questions"] = [f"could not plan: {e}"]
                    out.append(m)
                    continue
                lane = held.get(m["lane"]) or {"steps": []}
                live = {s["step"]: s["state"] for s in lane["steps"]}
                open_steps = {c["step"]: c for c in planned["clusters"]}
                nxt = next((c["step"] for c in planned["clusters"] if not c["waits"] and live.get(c["step"]) in (None, "queued")), None)
                for st in order:
                    c = open_steps.get(st["number"])
                    state = ("done" if c is None else "running" if live.get(st["number"]) not in (None, "queued", "landed", "blocked")
                             else "question" if live.get(st["number"]) == "blocked" else "next" if st["number"] == nxt else "waiting")
                    m["steps"].append({"step": st["number"], "title": st["title"], "state": state, "issues": [i["number"] for i in c["issues"]] if c else []})
                m["questions"] = planned["questions"]
                m["issues"] = [{"number": i["number"], "title": i["title"], "labels": [lb.get("name", "") for lb in i.get("labels") or []],
                                "step": ms.step_of(i, slug) or ""} for i in issues]
            out.append(m)
    return {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "milestones": out, "gh_ok": r.returncode == 0}


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
