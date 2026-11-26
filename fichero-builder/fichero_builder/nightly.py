"""dev-workflows.run.nightly-build (#6665): one dev build a night, of one frozen sha.

Pure rules first (the night's window, a lane's median land time, the order of the parts), then the real runners that the loop
hands to `run_night`; the tests give it fakes and a fake clock. Nothing here builds in the loop's own checkout."""
from __future__ import annotations

import json
import os
import shlex
import statistics
import subprocess
import sys
import threading
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from fichero_builder import client, journal

KEYS = ("no_new_steps_at", "freeze_at", "check_runner", "build_machine", "smoke_machine", "publish", "check_footprint_mb")
OPTIONAL = {"notarize_timeout_min": 90}  # local.nightly.notarize-own-timeout
BUILD_S = 7200  # the DMG part's build budget; notarization (the app and the DMG, two round trips) gets its own on top (notarize_budget_s)
NOTARY_POLL_S = 20  # scripts/notarize.sh polls `notarytool info` this often (FICHERO_NOTARY_POLL_SECONDS)


def notarize_budget_s(cfg: "Cfg") -> int:
    """Seconds the DMG part allows for notarization: two submit-then-poll round trips (the app, then the DMG) of the configured minutes."""
    return 2 * cfg.notarize_timeout_min * 60
GRACE = timedelta(hours=6)  # a loop that is down over the freeze starts that night's nightly only until six hours after it
MEDIAN_OF = 10  # a lane's median land time is over its last ten landed steps


@dataclass(frozen=True)
class Cfg:
    no_new_steps_at: tuple[int, int]
    freeze_at: tuple[int, int]
    check_runner: str
    build_machine: str
    smoke_machine: str
    publish: str
    check_footprint_mb: int
    notarize_timeout_min: int = 90  # [nightly].notarize_timeout_min: each notarization's own submit-then-poll budget, beside the build's


def _hm(key: str, text: str) -> tuple[int, int]:
    try:
        h, m = text.split(":")
        if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
            raise ValueError
        return int(h), int(m)
    except ValueError:
        raise ValueError(f"[nightly].{key} = {text!r} is not HH:MM") from None


def load(rules: dict) -> Cfg | None:
    """The `[nightly]` table of harness.toml; None when the project has none. A missing key is an error, never a default."""
    n = rules.get("nightly")
    if n is None:
        return None
    if missing := [k for k in KEYS if not n.get(k)]:
        raise ValueError(f"[nightly] lacks {', '.join(missing)}")
    if unknown := sorted(set(n) - set(KEYS) - set(OPTIONAL)):
        raise ValueError(f"[nightly]: unknown keys {unknown}")
    nt = n.get("notarize_timeout_min", OPTIONAL["notarize_timeout_min"])
    if not isinstance(nt, int) or nt <= 0:
        raise ValueError("[nightly].notarize_timeout_min must be a whole number of minutes above 0")
    return Cfg(_hm("no_new_steps_at", n["no_new_steps_at"]), _hm("freeze_at", n["freeze_at"]), n["check_runner"], n["build_machine"],
               n["smoke_machine"], n["publish"], int(n["check_footprint_mb"]), nt)


def window(now: datetime, cfg: Cfg) -> tuple[datetime, datetime]:
    """(the latest no_new_steps_at at or before now, the freeze_at after it): the night `now` is in or has just left."""
    start = now.replace(hour=cfg.no_new_steps_at[0], minute=cfg.no_new_steps_at[1], second=0, microsecond=0)
    if start > now:
        start -= timedelta(days=1)
    freeze = start.replace(hour=cfg.freeze_at[0], minute=cfg.freeze_at[1])
    if freeze <= start:
        freeze += timedelta(days=1)
    return start, freeze


def median_land_s(rows: list[dict], lane: str) -> float | None:
    """The median seconds from a step's first `sent` row to its `landed` row over the lane's last MEDIAN_OF landed steps; None with none."""
    sent: dict = {}
    took: list[float] = []
    for r in rows:
        if r.get("event") != "queue" or r.get("lane") != lane:
            continue
        if r.get("state") == "sent":
            sent.setdefault(r.get("step"), r["ts"])
        elif r.get("state") == "landed" and r.get("step") in sent:
            t = datetime.fromisoformat(r["ts"]) - datetime.fromisoformat(sent.pop(r["step"]))
            took.append(t.total_seconds())
    return statistics.median(took[-MEDIAN_OF:]) if took else None


def hold_why(now: datetime, cfg: Cfg, median: Callable[[], float | None]) -> str:
    """'' when a lane's next step may start; else why not. Before no_new_steps_at, and from freeze_at on, every step may start."""
    start, freeze = window(now, cfg)
    if now < start or now >= freeze:
        return ""
    median_s = median()  # the journal is read only inside the night window
    if median_s is None:
        return "after the cutoff, and the lane has no landed step to take a median land time from"
    if now + timedelta(seconds=median_s) > freeze:
        return f"after the cutoff: the lane's median land time {median_s / 60:.0f} min does not fit before the freeze at {freeze:%H:%M}"
    return ""


def candidate_due(now: datetime, cfg: Cfg, read: Callable[[], list[dict]]) -> str:
    """The night's key (its no_new_steps_at date) when `now` is past the freeze of the night that has no candidate row yet, else ''.
    A night's key is the date its window opened; a freeze more than GRACE ago is not started late."""
    start, freeze = window(now, cfg)
    if now < freeze:  # inside the window, or before the first: the night that just ended is the previous one
        start, freeze = window(start - timedelta(seconds=1), cfg)
    key = f"{start:%Y-%m-%d}"
    if now < freeze or now - freeze > GRACE or any(r.get("event") == "nightly" and r.get("state") == "candidate" and r.get("night") == key for r in read()):
        return ""
    return key


@dataclass
class Runners:
    """What the nightly does to the world; each takes the frozen sha and returns (rc, output). The tests replace them."""
    head: Callable[[], str]               # the integration head now
    check: Callable[[str], tuple]         # verify-all --full in a clean tree at sha on check_runner
    dmg: Callable[[str], tuple]           # a clean tree at sha, auto-notes, then the dev DMG on build_machine
    smoke: Callable[[str], tuple]         # the smoke of that DMG on smoke_machine
    publish: Callable[[str], tuple]       # the GitHub dev prerelease and TestFlight
    text: Callable[[str], None]           # a text to the owner
    test_list: Callable[[str], str]       # sha -> what to try, one text
    cleanup: Callable[[str], tuple] | None = None  # after a green publish: the local DMGs, archives and staging of that and older releases are deleted
    sizes: Callable[[], str] | None = None         # the build folders' sizes, one line each, for the report


def run_night(cfg: Cfg, r: Runners, sha: str, night: str, alert: Callable[[str], None]) -> bool:
    """The nightly of one frozen sha: check and DMG together, then the smoke, then the publish and the text, only if all green.
    A red part: nothing is published and ONE alert names the part. Returns whether it published."""
    def row(state, detail=""):
        journal.append("nightly", state=state, night=night, sha=sha, detail=detail[-300:])
    results: dict = {}

    def part(name, fn):
        try:
            results[name] = fn(sha)
        except (RuntimeError, OSError, ValueError) as e:  # a runner that cannot run is red with its reason
            results[name] = (1, f"{type(e).__name__}: {e}")
        row(f"{name}-{'green' if results[name][0] == 0 else 'red'}", results[name][1])
    ts = [threading.Thread(target=part, args=(n, f)) for n, f in (("check", r.check), ("dmg", r.dmg))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    if any(rc for rc, _ in results.values()):
        bad = [n for n in ("check", "dmg") if results[n][0]]
        alert(f"the nightly of {sha[:9]} is red at {' and '.join(bad)}: {(results[bad[0]][1].strip().splitlines() or [''])[-1]}")
        return False
    part("smoke", r.smoke)
    if results["smoke"][0]:
        alert(f"the nightly of {sha[:9]} is red at smoke: {(results['smoke'][1].strip().splitlines() or [''])[-1]}")
        return False
    part("publish", r.publish)
    if results["publish"][0]:
        alert(f"the nightly of {sha[:9]} is red at publish: {(results['publish'][1].strip().splitlines() or [''])[-1]}")
        return False
    if r.cleanup:  # the release is on GitHub: its local copies and the older ones go; a failed clear is a row, the night stays published
        part("cleanup", r.cleanup)
    row("published")  # the release is out: a text that cannot go never makes the night read as unfinished
    try:
        r.text(r.test_list(sha) + (f"\nBuild folders:\n{r.sizes()}" if r.sizes else ""))
    except Exception as e:  # noqa: BLE001 - one alert, so a person sends it
        row("text-red", f"{type(e).__name__}: {e}")
        alert(f"the nightly of {sha[:9]} is published but the owner's text failed: {e}")
    return True


def when_due(cfg: Cfg | None, r: Runners | None, now: datetime, alert: Callable[[str], None], chains, threads: list,
             spawn: Callable[[str, str], object] | None = None) -> None:
    """At each tick: past the freeze with no candidate row for the night, journal the integration head as the candidate and start the
    nightly: inline when `chains` is None (the tests, a one-shot loop), else through `spawn` (local.nightly.detached: its own process,
    which a loop re-exec neither waits for nor kills), else in a thread as before."""
    if cfg is None or r is None:
        return
    night = candidate_due(now, cfg, journal.read)
    if not night:
        return
    sha = r.head()
    if spawn is not None and chains is not None:
        # 2026-11-25 03:23: the candidate row was written and the loop restarted before its thread ran the night; the night was lost.
        # The detached process starts FIRST: a restart before the row below starts it again, and a live pid refuses a second one
        spawn(sha, night)
        journal.append("nightly", state="candidate", night=night, sha=sha, detail="the integration head at the freeze")
        return
    journal.append("nightly", state="candidate", night=night, sha=sha, detail="the integration head at the freeze")
    if chains is None:
        run_night(cfg, r, sha, night, alert)
    else:
        t = threading.Thread(target=run_night, args=(cfg, r, sha, night, alert), name="nightly", daemon=True)
        threads.append(t)
        t.start()


# --- the real runners -------------------------------------------------------------------------------------------------------

def _on(machine: str, script: str, timeout_s: float) -> tuple:
    """Run a shell script on `machine`: 'local' here, else `host[:dir]` over ssh (the dir is where `_tree` puts the part's clone).
    (rc, output). ponytail: no placement or lock logic."""
    if machine == "local":
        argv = ["bash", "-ec", script]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", machine.split(":")[0], script]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError) as e:
        return 1, str(e)
    return p.returncode, (p.stdout + p.stderr)[-2000:]


def _q(path: str) -> str:
    """A path as one shell word; a leading ~/ is the remote's home."""
    return '"$HOME"/' + shlex.quote(path[2:]) if path.startswith("~/") else shlex.quote(path)


def _tree(machine: str, state, part: str) -> str:
    """The part's one fixed clone dir on `machine`: under the state dir here, under the machine's `:dir` (default ~/fichero-nightly) over
    ssh. A fixed path, so a night's clone replaces the last one's: nothing piles up and no name is guessable per process."""
    if machine == "local":
        return str(Path(state) / "nightly" / part)
    return f"{machine.split(':', 1)[1] if ':' in machine else '~/fichero-nightly'}/{part}"


def _clean_tree(origin: str, sha: str, tree: str) -> str:
    """Shell: a fresh clone of `origin` checked out at `sha` in `tree` (never the loop's checkout)."""
    t = _q(tree)
    return f"rm -rf {t} && git clone -q --no-checkout {shlex.quote(origin)} {t} && git -C {t} checkout -q {shlex.quote(sha)}"


def real_runners(root, cfg: Cfg, branch: str, state, texter: Callable[[str], None] | None = None) -> Runners:
    """Runners over clean clones of `origin` at the frozen sha. The check runs `builder verify-all --full` in its tree; the DMG runs
    `release_guard.py auto-notes <version>` and then `release-all.sh --dev --skip-testflight` in its own. Each part has one fixed clone
    dir (`_tree`), replaced by the next night's. The smoke runs in the DMG's tree, or, on another machine, in a clone of the sha with the
    built app copied over. ponytail: one machine per part, no placement."""
    u = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    if u.returncode:
        raise RuntimeError(f"no origin remote in {root}: the nightly clones it")
    origin = u.stdout.strip()
    app = "fichero/build/xcode/Products/Release/Fichero.app"
    if cfg.smoke_machine != cfg.build_machine and cfg.build_machine != "local":
        raise ValueError("[nightly]: a smoke_machine other than the build_machine needs a local build_machine (the app is copied from here)")

    def tree(machine: str, part: str) -> str:
        return _tree(machine, state, part)

    venv = project_venv(root)

    def env(machine: str) -> str:
        """A part on this machine runs with the project venv first on PATH (2026-11-25 03:40: a bare `python3` found no tomllib)."""
        return f"export PATH={_q(venv)}/bin:\"$PATH\" && " if machine == "local" and venv else ""

    def link_venv(machine: str, t: str) -> str:
        """The DMG clone is a plain clone, so find_project_python.sh finds no .venv in it (03:40: "project Python not found")."""
        # excluded: .gitignore's `.venv/` matches a directory, not a link, so the link would make the clone read as dirty
        return f" && ln -sfn {_q(venv)} {_q(t)}/.venv && echo .venv >> {_q(t)}/.git/info/exclude" if machine == "local" and venv else ""

    def check(sha):
        t = tree(cfg.check_runner, "check")
        return _on(cfg.check_runner, f"{env(cfg.check_runner)}{_clean_tree(origin, sha, t)} && cd {_q(t)}/fichero-builder && GATE_FOOTPRINT_MB={cfg.check_footprint_mb} PYTHONPATH=. python3 -m fichero_builder verify-all --full --root {_q(t)} --state {shlex.quote(str(state))}", 14400)

    def dmg(sha):
        t = tree(cfg.build_machine, "dmg")
        version = f"$(sed -n 's/^MARKETING_VERSION = //p' {_q(t)}/fichero/Configs/Version.xcconfig | head -1)"
        polls = cfg.notarize_timeout_min * 60 // NOTARY_POLL_S  # scripts/notarize.sh submits, then polls this many times (never --wait)
        return _on(cfg.build_machine, f"{env(cfg.build_machine)}{_clean_tree(origin, sha, t)}{link_venv(cfg.build_machine, t)} && cd {_q(t)} && python3 scripts/release_guard.py auto-notes {version} && "
                   f"FICHERO_NOTARY_POLL_SECONDS={NOTARY_POLL_S} FICHERO_NOTARY_MAX_POLLS={polls} scripts/release-all.sh --dev --skip-testflight",
                   BUILD_S + notarize_budget_s(cfg))

    def smoke(sha):
        built, here = tree(cfg.build_machine, "dmg"), tree(cfg.smoke_machine, "smoke")
        if cfg.smoke_machine == cfg.build_machine:
            return _on(cfg.smoke_machine, f"{env(cfg.smoke_machine)}cd {_q(built)} && scripts/smoke-release-embedded-backend.sh", 3600)
        host = cfg.smoke_machine.split(":")[0]  # the app is only in the build tree: clone the sha there, copy the app over, smoke it
        rc, out = _on(cfg.smoke_machine, f"{_clean_tree(origin, sha, here)} && mkdir -p {_q(here)}/{shlex.quote(app)}", 1800)
        if rc:
            return rc, out
        dest = f"{host}:{here[2:] if here.startswith('~/') else here}/{app}/"  # a remote path with no ~/ is relative to its home
        rc, out = _on("local", f"rsync -a --delete {_q(built)}/{shlex.quote(app)}/ {shlex.quote(dest)}", 3600)
        if rc:
            return rc, out
        return _on(cfg.smoke_machine, f"cd {_q(here)} && scripts/smoke-release-embedded-backend.sh", 3600)

    def publish(sha):
        return _on(cfg.build_machine, f"{env(cfg.build_machine)}cd {_q(tree(cfg.build_machine, 'dmg'))} && scripts/release-all.sh --{cfg.publish} --skip-dmg --github --prerelease", 7200)

    def test_list(sha):
        rel = client.release_branch(root)  # "" = no release branch: the last 30 commits
        p = subprocess.run(["git", "-C", str(root), "log", "--format=- %s", f"origin/{rel}..{sha}" if rel else sha], capture_output=True, text=True)
        return f"Fichero dev build {sha[:9]} is published. To try:\n" + "\n".join(p.stdout.splitlines()[:30])

    def cleanup(sha):
        t = tree(cfg.build_machine, "dmg")
        loop_releases = f" && rm -rf {_q(str(root))}/build/releases/*.dmg {_q(str(root))}/build/releases/*.xcarchive {_q(str(root))}/build/releases/dmg-stage" if cfg.build_machine == "local" else ""
        return _on(cfg.build_machine, f"rm -rf {_q(t)}/build/releases{loop_releases}", 1800)

    def sizes():
        t = tree(cfg.build_machine, "dmg")
        dirs = " ".join(f"{_q(t)}/{d}" for d in ("build", "fichero/build", "fichero-server/build"))
        return _on(cfg.build_machine, f"du -sh {dirs} 2>/dev/null; true", 600)[1].strip()

    def head():
        out = subprocess.run(["git", "-C", str(root), "rev-parse", f"origin/{branch}"], capture_output=True, text=True)
        if out.returncode:
            raise RuntimeError(f"no origin/{branch}: {out.stderr.strip()}")
        return out.stdout.strip()
    return Runners(head=head, check=check, dmg=dmg, smoke=smoke, publish=publish, text=texter or text_owner, test_list=test_list, cleanup=cleanup, sizes=sizes)


def project_venv(root) -> str:
    """The project's venv dir, as scripts/find_project_python.sh finds it from the loop's checkout ('' when it finds none)."""
    f = Path(root) / "scripts" / "find_project_python.sh"
    if not f.is_file():
        return ""
    p = subprocess.run(["bash", str(f), str(root)], capture_output=True, text=True)
    return str(Path(p.stdout.strip()).parent.parent) if p.returncode == 0 and p.stdout.strip() else ""


def preflight(root, cfg: Cfg, rules: dict, which: Callable[[str], tuple] | None = None) -> list[str]:
    """What would make tonight's nightly red before any build: each one cheap to read (local.nightly.preflight, 2026-11-25: three
    reds, each found hours into the night). [] = go. `which(script)` runs a shell line on 'local' (the tests fake it)."""
    run = which or (lambda script: _on("local", script, 60))
    out = []
    venv = project_venv(root)
    if any(m == "local" for m in (cfg.check_runner, cfg.build_machine, cfg.smoke_machine)):
        if not venv:
            out.append("no project venv: scripts/find_project_python.sh finds none from the loop's checkout, so the DMG part's "
                       "release scripts would stop at 'project Python not found'")
        else:
            rc, said = run(f"{_q(venv)}/bin/python -c 'import sys, tomllib; print(sys.version.split()[0])'")
            if rc:
                out.append(f"the project venv's python ({venv}) cannot import tomllib: {said.strip()[-120:]}")
    user = (rules.get("jail") or {}).get("user")
    if user and rules.get("jail", {}).get("enabled", True) and cfg.check_runner != "local":
        out.append(f"[nightly].check_runner = {cfg.check_runner!r}: verify-all runs as the jail user {user!r}, which exists only on "
                   "this machine (2026-11-25 03:41: 'jail user does not exist' on the iMac); set check_runner = \"local\"")
    for m in {cfg.check_runner, cfg.smoke_machine, cfg.build_machine} - {"local"}:
        rc, said = _on(m, "true", 30) if which is None else run(f"ssh {m.split(':')[0]} true")
        if rc:
            out.append(f"{m.split(':')[0]} is not reachable over ssh: {said.strip()[-120:]}")
    if not os.environ.get("FICHERO_NIGHTLY_TEXT_TO"):
        out.append("FICHERO_NIGHTLY_TEXT_TO is unset in the loop's environment: the published text would fail")
    return out


def text_owner(msg: str) -> None:
    """An iMessage to FICHERO_NIGHTLY_TEXT_TO; an unset variable is an error, not a silent skip."""
    to = os.environ.get("FICHERO_NIGHTLY_TEXT_TO")
    if not to:
        raise RuntimeError("FICHERO_NIGHTLY_TEXT_TO names nobody to text")
    script = f'tell application "Messages" to send {_as(msg)} to participant {_as(to)} of (1st account whose service type = iMessage)'
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _as(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'



# --- the detached nightly (local.nightly.detached, #6589: the loop's re-exec killed the nightly thread seconds after its candidate row) ---

PID = "nightly.pid"  # under the state dir: {"pid", "night", "sha", "started"} of the running nightly process; the lock and the adoption key


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running(state, alive: Callable[[int], bool] = _alive) -> dict:
    """The pid file's record when that process is alive, else {}."""
    try:
        doc = json.loads((Path(state) / PID).read_text())
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc.get("pid"), int) and alive(doc["pid"]) else {}


def start_detached(root, state, sha: str, night: str, popen=subprocess.Popen, alive: Callable[[int], bool] = _alive) -> int:
    """`builder nightly-run` as its own session (setsid): no loop thread holds it, so a re-exec neither waits for it nor ends it. One at a
    time: a live pid file refuses a second (a row says so). Returns the pid, or 0 when one already runs."""
    state = Path(state)
    if cur := running(state, alive):
        journal.append("nightly", state="already-running", night=night, sha=sha, detail=f"pid {cur['pid']} runs the night of {cur.get('night')}")
        return 0
    state.mkdir(parents=True, exist_ok=True)
    pkg = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(pkg)}
    with open(state / "nightly.log", "a") as log:
        p = popen([sys.executable, "-m", "fichero_builder", "nightly-run", "--root", str(root), "--state", str(state), "--sha", sha, "--night", night],
                  stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=str(pkg), env=env)
    tmp = state / f"{PID}.tmp"
    tmp.write_text(json.dumps({"pid": p.pid, "night": night, "sha": sha, "started": datetime.now().isoformat(timespec="seconds")}))
    tmp.replace(state / PID)
    journal.append("nightly", state="detached", night=night, sha=sha, detail=f"pid {p.pid}: its own process, adopted by pid after a restart")
    return p.pid


ADOPTED: set = set()  # the pids this loop process has said it adopted (one row each)


def adopt(state, alert: Callable[[str], None], alive: Callable[[int], bool] = _alive) -> None:
    """Each tick: a live nightly process from the pid file is adopted (one row per loop process); a dead one whose night has no
    `published` and no red row ended without its result: one alert, and the pid file goes."""
    f = Path(state) / PID
    try:
        doc = json.loads(f.read_text())
    except (OSError, ValueError):
        return
    pid, night = doc.get("pid"), doc.get("night", "")
    if isinstance(pid, int) and alive(pid):
        if pid not in ADOPTED:
            ADOPTED.add(pid)
            journal.append("nightly", state="adopted", night=night, sha=doc.get("sha", ""), detail=f"pid {pid} still runs: watched by pid")
        return
    f.unlink(missing_ok=True)
    ended = any(r.get("event") == "nightly" and r.get("night") == night and (r.get("state") == "published" or str(r.get("state", "")).endswith("-red"))
                for r in journal.read())
    if not ended:
        alert(f"the nightly of {str(doc.get('sha', ''))[:9]} (night {night}) ended with no result: pid {pid} is gone")


def run_detached(root, state, sha: str, night: str, alert: Callable[[str], None], runners: Runners | None = None) -> bool:
    """The body of `builder nightly-run`: the night's parts with the real runners; the pid file goes when it ends, if it is still this one."""
    import tomllib
    cfg = load(tomllib.loads((Path(root) / "harness.toml").read_text()))
    if cfg is None:
        raise ValueError("harness.toml has no [nightly]")
    rules = tomllib.loads((Path(root) / "harness.toml").read_text())
    if runners is None and (bad := preflight(root, cfg, rules)):  # said at the freeze, not hours in; the night still runs
        journal.append("nightly", state="preflight-red", night=night, sha=sha, detail="; ".join(bad)[-300:])
        alert(f"the nightly of {sha[:9]} starts with a problem: {bad[0]}")
    try:
        return run_night(cfg, runners or real_runners(root, cfg, client.land_branch(root), state), sha, night, alert)
    finally:
        f = Path(state) / PID
        try:
            if json.loads(f.read_text()).get("pid") == os.getpid():
                f.unlink()
        except (OSError, ValueError):
            pass
