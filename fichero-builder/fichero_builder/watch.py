"""`builder watch [--port 8765] [--state DIR]`: a live progress page from the journal (dev-workflows.tool.watch).

Stdlib http.server on 127.0.0.1, one HTML page with a meta refresh, newest first: each run (worker + cost rows), each check,
each landing. ponytail: a naive page; the SwiftUI Builder app replaces it later and reads the same journal."""
from __future__ import annotations

import html
import http.server
import json
import tomllib
from itertools import groupby
from pathlib import Path

from fichero_builder import journal

REFRESH_S = 5


ROOT = Path.cwd()  # ponytail: set once by main; one page, one rules file


WORKER_ROWS = ("worker", "cost")  # what `builder run` writes to the shared state; everything else there is the worker's word


def rows_of(root) -> list[dict]:
    """The owner's journal (checks, landings) and the worker's under the shared state (runs), by time. From the shared file, which
    the worker can write, only run rows are read, so a worker cannot put a check or a landing on this page; a line that does not
    parse is skipped. A page of one file alone shows half of this."""
    rows = journal.read()
    f = Path(root) / "harness.toml"
    workroot = tomllib.loads(f.read_text()).get("jail", {}).get("workroot") if f.is_file() else None
    shared = Path(workroot) / "state" / "journal.jsonl" if workroot else None
    if shared and shared.is_file() and shared.resolve() != journal.path().resolve():
        for ln in shared.read_text(errors="replace").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("event") in WORKER_ROWS:
                rows.append(r)
    return sorted(rows, key=lambda r: r.get("ts", ""))


def _runs(rows: list[dict]) -> list[list]:
    out = {}
    for r in rows:
        if r.get("event") == "worker":
            out.setdefault(r.get("task"), {"name": r.get("task"), "started": r.get("ts", ""), "model": r.get("model", ""),
                                           "worktree": r.get("worktree", ""), "turns": 0, "usd": 0.0, "status": "running"})
            out[r.get("task")]["status"] = "running"  # the next generation after a handoff
        elif r.get("event") == "cost" and r.get("task") in out:
            run = out[r["task"]]
            run["usd"] = round(run["usd"] + float(r.get("usd") or 0), 4)
            run["turns"] = r.get("turns", run["turns"])
            run["status"] = r.get("end") or run["status"]
    return [[v["name"], v["worktree"], v["model"], v["started"], v["turns"], f"{v['usd']:.2f}", v["status"]] for v in reversed(list(out.values()))]


def _checks(rows: list[dict]) -> list[list]:
    cs = [r for r in rows if r.get("event") == "check"]
    return [[r.get("ts", ""), f"{str(r.get('since', ''))[:9]}..{str(r.get('head', ''))[:9]}", "green" if r.get("ok") else "red",
             r.get("failed") or "-"] for r in reversed(cs)]


def _lands(rows: list[dict]) -> list[list]:
    ls = [r for r in rows if r.get("event") == "landed"]
    out = []
    for sha, steps in groupby(ls, key=lambda r: r.get("sha")):
        steps = list(steps)
        last = steps[-1]
        verdict = last.get("step") if last.get("ok") else f"red at {last.get('step')}"
        out.append([last.get("ts", ""), str(sha)[:9], verdict, last.get("branch", "-"), "yes" if last.get("pushed") else "no"])
    return list(reversed(out))


def _table(title: str, heads: list[str], body: list[list]) -> str:
    h = "".join(f"<th>{html.escape(x)}</th>" for x in heads)
    rs = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in body)
    return f"<h2>{title}</h2><table><tr>{h}</tr>{rs or '<tr><td colspan=9>none yet</td></tr>'}</table>"


def render(rows: list[dict]) -> str:
    return (f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="{REFRESH_S}"><title>builder watch</title>'
            "<style>body{font:14px system-ui;margin:16px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 8px;text-align:left}</style>"
            + _table("Runs", ["name", "worktree", "model", "started", "turns", "USD", "status"], _runs(rows))
            + _table("Checks", ["at", "range", "result", "failed rung"], _checks(rows))
            + _table("Lands", ["at", "tip", "last step", "branch", "pushed"], _lands(rows))
            + _table("Queue", ["lane", "step", "state", "issues", "head", "why"], _queue()))


def _queue() -> list[list]:
    from fichero_builder import queue

    return queue.table()


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = render(rows_of(ROOT)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


def server(host: str, port: int) -> http.server.HTTPServer:
    return http.server.HTTPServer((host, port), _Handler)


def main(a) -> int:
    global ROOT
    ROOT = Path(a.root)
    srv = server("127.0.0.1", a.port)
    print(f"watching {journal.path()} and the shared state of {ROOT / 'harness.toml'} at http://127.0.0.1:{srv.server_address[1]}/ (Ctrl-C stops)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
