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
    if lane.get("pane"):
        note = f"MEASURE {machine} {sha[:9]} exit {rc}: {(line or text)[:600]}"
        if tell := doc.get("loop", {}).get("tell"):
            t = subprocess.run([str(Path(tell).expanduser()), lane["pane"], note], capture_output=True, text=True)
            told = "" if t.returncode == 0 else t.stderr.strip()[-200:]
        else:
            from fichero_builder import tell as tell_mod
            trc, tout = tell_mod.send(lane["pane"], note)
            told = "" if trc == 0 else tout
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


INSTALL = r'''set -e
dmg={dmg}
mnt=$(hdiutil attach -nobrowse -readonly "$dmg" | tail -1 | cut -f3-)
app=$(ls -d "$mnt"/*.app | head -1); name=$(basename "$app")
[ -n "$name" ] && [ -d "$app" ] || {{ echo "no .app in the mounted image"; exit 1; }}  # never rm -rf an empty name
mkdir -p ~/Applications && rm -rf ~/Applications/"$name" && cp -R "$app" ~/Applications/
hdiutil detach "$mnt" -quiet || true
rm -f "$dmg"
open ~/Applications/"$name" || echo "OPEN-FAILED (no GUI session?)"
sleep {wait}
echo "APP $name"
pgrep -fl "$name/Contents/MacOS" | head -3 | sed 's/^/RUNNING /' || true
pgrep -fl -i "fichero.*engine|fichero_server|uvicorn" | head -3 | sed 's/^/ENGINE /' || true
'''


def install(root, machine: str, dmg: str = "", wait: int = 20) -> tuple[int, str]:
    """`builder install <machine> [dmg]`: the dev DMG (default: the newest built one in the journal) streamed over ssh to the
    `[machines]` host, its app copied to ~/Applications there and opened; reports whether the app and its engine are running.
    One `install` row. The owner tests on that machine next."""
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    m = doc.get("machines", {}).get(machine)

    def row(rc: int, out: str, **kw) -> tuple[int, str]:
        journal.append("install", machine=machine, dmg=dmg, rc=rc, detail=out[-800:], **kw)
        return rc, out
    if not m or not m.get("ssh") or not m.get("dir"):
        return row(1, f"no [machines].{machine} with ssh and dir in harness.toml")
    dmg = dmg or next((r.get("dmg") for r in reversed(journal.read()) if r.get("event") == "build" and r.get("ok") and r.get("dmg")), "")
    if not dmg or not Path(dmg).is_file():
        return row(1, f"no dev DMG to install ({dmg or 'none built'}): run `builder build --dev` first")
    host, d = m["ssh"], m["dir"]
    free = _ssh(host, f"df -g {d} | tail -1 | awk '{{print $4}}'", timeout=60)
    gb = int(free.stdout.decode().strip()) if free.returncode == 0 and free.stdout.decode().strip().isdigit() else -1
    if gb < float(m.get("min_free_gb", 5)):
        return row(1, f"{machine} has {gb} GiB free: not copied" if gb >= 0 else f"{machine} unreachable: {free.stderr.decode().strip()[-200:]}")
    remote = f"{d}/install/{shlex.quote(Path(dmg).name)}"  # the dir is the owner's config (a leading ~ expands there)
    with open(dmg, "rb") as f:
        up = subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"mkdir -p {d}/install && cat > {remote}"],
                            stdin=f, capture_output=True, timeout=3600)
    if up.returncode:
        return row(1, f"copy failed: {up.stderr.decode().strip()[-200:]}")
    r = _ssh(host, INSTALL.format(dmg=remote, wait=int(wait)), timeout=600)
    out = r.stdout.decode(errors="replace") + r.stderr.decode(errors="replace")
    running, engine = "RUNNING " in out, "ENGINE " in out
    return row(0 if r.returncode == 0 and running else 1, out.strip(), app_running=running, engine_running=engine)


TEST_PLUGINS = ("pytest", "anyio", "hypothesis", "langsmith", "pytest-timeout", "pytest-asyncio")
CLOSURE = r'''
import json, re, sys
from importlib import metadata
want, seen = list(sys.argv[1:]), {}
while want:
    n = re.split(r"[ ;<>=!~\[(]", want.pop())[0].strip().lower().replace("_", "-")
    if not n or n in seen:
        continue
    try:
        d = metadata.distribution(n)
    except metadata.PackageNotFoundError:
        continue
    seen[n] = d.version
    want += [r for r in (d.requires or []) if "extra ==" not in r]
print(json.dumps(seen))
'''


JAIL_PYTHON = "/Users/Shared/fichero-worker/venv/bin/python"


def default_python(root) -> str:
    """[check].python of root's harness.toml, else the jail's venv interpreter."""
    f = Path(root) / "harness.toml"
    return (tomllib.loads(f.read_text()) if f.is_file() else {}).get("check", {}).get("python") or JAIL_PYTHON


def sync(root, machine: str, python: str = "") -> tuple[int, str]:
    """`builder machines sync <name>` (manager 2026-11-02): the test plugins and their dependencies, at the exact versions the
    jail's venv has, installed into the machine's `<dir>/venv`, so a remote check collects what a local one does. Disk floor
    first; one `machines` row."""
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    m = doc.get("machines", {}).get(machine)
    python = python or default_python(root)

    def row(rc: int, out: str) -> tuple[int, str]:
        journal.append("machines", machine=machine, step="sync", rc=rc, detail=out[-800:])
        return rc, out
    if not m or not m.get("ssh") or not m.get("dir"):
        return row(1, f"no [machines].{machine} with ssh and dir in harness.toml")
    r = subprocess.run([python, "-I", "-c", CLOSURE, *TEST_PLUGINS], capture_output=True, text=True)
    if r.returncode:
        return row(1, f"could not read the jail venv's pins: {r.stderr.strip()[-200:]}")
    pins = json.loads(r.stdout)
    host, d = m["ssh"], m["dir"]
    free = _ssh(host, f"df -g {d} | tail -1 | awk '{{print $4}}'", timeout=60).stdout.decode().strip()
    if not free.isdigit() or int(free) < float(m.get("min_free_gb", 5)):
        return row(1, f"{machine}: {free or '?'} GiB free, under {m.get('min_free_gb', 5)}: not synced")
    req = "\n".join(f"{n}=={v}" for n, v in sorted(pins.items())) + "\n"
    out = _ssh(host, (f"cat > {d}/test-pins.txt && export PATH={d}/bin:$PATH UV_CACHE_DIR={d}/uvcache && "  # a uv venv has no pip (the iMac's)
                                f"if command -v uv >/dev/null; then uv pip install -q --python {d}/venv/bin/python -r {d}/test-pins.txt; "
                                f"else {d}/venv/bin/python -m pip install -q -r {d}/test-pins.txt; fi"), stdin=req.encode(), timeout=1800)
    text = (out.stdout + out.stderr).decode(errors="replace").strip()
    return row(out.returncode, f"{len(pins)} pinned packages -> {machine}:{d}/venv" + (f": {text[-600:]}" if out.returncode or text else ""))


SCANNER_PATH = '"$HOME/.local/bin":/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'  # the security rung's own (check_tool.SECURITY_PATH)
VERSION = {"bandit": "bandit --version", "semgrep": "semgrep --version", "gitleaks": "gitleaks version", "osv-scanner": "osv-scanner --version"}


def _scanner_install(pins: dict, tools: list[str]) -> str:
    """Each pinned scanner where the rung looks (~/.local/bin): bandit and semgrep as uv tools at the pin, gitleaks and osv-scanner
    as their release binaries at the pin. Only a tool not already at its pin is touched."""
    parts = ["mkdir -p \"$HOME/.local/bin\""]
    for t in tools:
        v, q = pins[t], shlex.quote(pins[t])
        have = f"[ \"$({VERSION[t]} 2>/dev/null | grep -Eo '[0-9]+[.][0-9]+[.][0-9]+' | head -1)\" = {q} ] || "
        if t in ("bandit", "semgrep"):
            parts.append(have + f"uv tool install --force {t}=={q}")
        elif t == "gitleaks":
            url = f"https://github.com/gitleaks/gitleaks/releases/download/v{v}/gitleaks_{v}_darwin_$(uname -m | sed s/x86_64/x64/).tar.gz"
            parts.append(have + f"curl -fsSL {url} | tar -xz -C \"$HOME/.local/bin\" gitleaks")
        else:
            url = f"https://github.com/google/osv-scanner/releases/download/v{v}/osv-scanner_darwin_$(uname -m | sed s/x86_64/amd64/)"
            parts.append(have + f"(curl -fsSL -o \"$HOME/.local/bin/osv-scanner\" {url} && chmod +x \"$HOME/.local/bin/osv-scanner\")")
    return " && ".join(parts)


def scanner_problems(found: dict, pins: dict, tools: list[str]) -> list[str]:
    return [f"{t} is {found.get(t) or 'not installed'}, the pin is {pins[t]}" for t in tools if found.get(t) != pins[t]]


def scanners(root, install: bool = False, only: str = "") -> tuple[int, str]:
    """`builder machines scanners [--install] [<host>]` (manager 2026-11-27): the runner preflight for the security rung. Over each
    host of [check].remote (and build_remote), under the rung's own PATH: each pinned scanner's version, held against
    [check.security].pins; `--install` puts a missing or other-version one there first. One `machines` row a host; rc 1 when any
    host is short."""
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    chk, sec = doc.get("check", {}), doc.get("check", {}).get("security", {})
    pins = dict(sec.get("pins") or {})
    tools = [t for t in ("bandit", "semgrep", "gitleaks", "osv-scanner") if pins.get(t) and (t != "osv-scanner" or sec.get("osv"))]
    hosts = list(dict.fromkeys(x.partition(":")[0] for x in [chk.get("build_remote", ""), *chk.get("remote", [])] if x))
    rc, lines = 0, []
    for host in [h for h in hosts if not only or h == only]:
        pre = f"export PATH={SCANNER_PATH}; "
        if install:
            r = _ssh(host, pre + _scanner_install(pins, tools), timeout=1800)
            if r.returncode:
                lines.append(f"{host}: install failed: {(r.stdout + r.stderr).decode(errors='replace').strip()[-300:]}")
        probe = pre + "; ".join(f"printf '%s ' {t}; {VERSION[t]} 2>/dev/null | grep -Eo '[0-9]+[.][0-9]+[.][0-9]+' | head -1; echo" for t in tools)
        r = _ssh(host, probe, timeout=120)
        found = {}
        for ln in r.stdout.decode(errors="replace").splitlines():
            name, _, v = ln.strip().partition(" ")
            if name in tools and v.strip():
                found[name] = v.strip()
        bad = ["unreachable"] if r.returncode and not found else scanner_problems(found, pins, tools)
        journal.append("machines", machine=host, step="scanners", rc=int(bool(bad)), found=found, detail="; ".join(bad) or "every pinned scanner at its pin")
        lines.append(f"{host}: " + ("; ".join(bad) if bad else "ok (" + ", ".join(f"{t} {found[t]}" for t in tools) + ")"))
        rc |= bool(bad)
    return rc, "\n".join(lines) or "no [check].remote runner"
