"""`builder measure <lane> --machine <name> [--sha S] -- <script> [args]` (dev-workflows.run.measure): a lane's commit runs a
measurement on a test machine. Its engine source and the script are shipped with `git archive` (never the worktree, which an
agent is working in) to `<dir>/wt/<sha12>` on the `[machines].<name>` host, run with that host's venv under TMPDIR=<dir>/tmp
(emptied after); one `measure` row with the last JSON line, told to the lane's pane. A host short of disk refuses first."""
from __future__ import annotations

import json
import shlex
import subprocess
import tomllib
from pathlib import Path

from fichero_builder import journal, queue

SRC = "fichero-server/src"


def _ssh(host: str, script: str, stdin: bytes | None = None, timeout: float = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script], input=stdin, capture_output=True, timeout=timeout)


def run(root, lane_id: str, machine: str, argv: list[str], sha: str = "") -> tuple[int, str]:
    """(exit, the JSON line or why). Every outcome is one `measure` row."""
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    m = doc.get("machines", {}).get(machine)
    lane = next((x for x in queue.load() if x["id"] == lane_id), None)

    def row(rc: int, out: str, **kw) -> tuple[int, str]:
        journal.append("measure", lane=lane_id, machine=machine, sha=sha, args=argv, rc=rc, detail=out[-500:], **kw)
        return rc, out
    if not m or not m.get("ssh") or not m.get("dir"):
        return row(1, f"no [machines].{machine} with ssh and dir in harness.toml")
    if lane is None or not argv:
        return row(1, f"no lane {lane_id!r}" if lane is None else "no script to run")
    host, d = m["ssh"], m["dir"]  # the owner's config: `dir` may start with ~, expanded by the remote shell
    sha = sha or queue.lane_head(lane["worktree"])
    free = _ssh(host, f"df -g {d} | tail -1 | awk '{{print $4}}'", timeout=60)
    gb = int(free.stdout.decode().strip() or -1) if free.returncode == 0 and free.stdout.decode().strip().isdigit() else -1
    if gb < float(m.get("min_free_gb", 5)):
        return row(1, f"{machine} has {gb} GiB free (under {m.get('min_free_gb', 5)}): not shipped" if gb >= 0 else f"{machine} unreachable: {free.stderr.decode().strip()[-200:]}")
    paths = [SRC] + ([argv[0]] if not argv[0].startswith("-") and (Path(lane["worktree"]) / argv[0]).exists() else [])
    tar = subprocess.run(["git", "-c", "safe.directory=*", "-C", lane["worktree"], "archive", "--format=tar", sha, "--", *paths], capture_output=True)
    if tar.returncode:
        return row(1, f"git archive failed: {tar.stderr.decode().strip()[-200:]}")
    wt = f"{d}/wt/{sha[:12]}"
    up = _ssh(host, f"mkdir -p {wt} {d}/tmp && tar -x -C {wt}", stdin=tar.stdout, timeout=600)
    if up.returncode:
        return row(1, f"shipping failed: {up.stderr.decode().strip()[-200:]}")
    r = _ssh(host, f"cd {wt} && TMPDIR={d}/tmp PYTHONPATH={SRC} {d}/venv/bin/python {shlex.join(argv)}; rc=$?; rm -rf {d}/tmp/*; exit $rc")
    out = r.stdout.decode(errors="replace")
    line = next((ln for ln in reversed(out.splitlines()) if ln.strip().startswith("{") and _json(ln)), "")
    rc, text = row(r.returncode, line or (out + r.stderr.decode(errors="replace"))[-500:], json=line)
    told = ""
    if lane.get("pane") and (tell := doc.get("loop", {}).get("tell")):
        t = subprocess.run([str(Path(tell).expanduser()), lane["pane"], f"MEASURE {machine} {sha[:9]} exit {rc}: {(line or text)[:600]}"], capture_output=True, text=True)
        told = "" if t.returncode == 0 else t.stderr.strip()[-200:]
    if told:
        journal.append("queue", lane=lane_id, step="-", state="tell-refused", detail=told)
    return rc, text


def _json(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except ValueError:
        return False


def main(a) -> int:
    rc, out = run(a.root, a.lane, a.machine, a.argv[1:] if a.argv[:1] == ["--"] else a.argv, a.sha)
    print(out)
    return rc
