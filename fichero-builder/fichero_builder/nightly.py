"""dev-workflows.run.nightly-build (#6665): one dev build a night, of one frozen sha.

Pure rules first (the night's window, a lane's median land time, the order of the parts), then the real runners that the loop
hands to `run_night`; the tests give it fakes and a fake clock. Nothing here builds in the loop's own checkout."""
from __future__ import annotations

import os
import shlex
import statistics
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from fichero_builder import journal

KEYS = ("no_new_steps_at", "freeze_at", "check_runner", "build_machine", "smoke_machine", "publish", "check_footprint_mb")
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
    return Cfg(_hm("no_new_steps_at", n["no_new_steps_at"]), _hm("freeze_at", n["freeze_at"]), n["check_runner"], n["build_machine"],
               n["smoke_machine"], n["publish"], int(n["check_footprint_mb"]))


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


def hold_why(now: datetime, cfg: Cfg, median_s: float | None) -> str:
    """'' when a lane's next step may start; else why not. Before no_new_steps_at, and from freeze_at on, every step may start."""
    start, freeze = window(now, cfg)
    if now >= freeze:
        return ""
    if median_s is None:
        return "after the cutoff, and the lane has no landed step to take a median land time from"
    if now + timedelta(seconds=median_s) > freeze:
        return f"after the cutoff: the lane's median land time {median_s / 60:.0f} min does not fit before the freeze at {freeze:%H:%M}"
    return ""


def candidate_due(now: datetime, cfg: Cfg, rows: list[dict]) -> str:
    """The night's key (its no_new_steps_at date) when `now` is past the freeze of the night that has no candidate row yet, else ''.
    A night's key is the date its window opened; a freeze more than GRACE ago is not started late."""
    start, freeze = window(now, cfg)
    if now < freeze:  # inside the window, or before the first: the night that just ended is the previous one
        start, freeze = window(start - timedelta(seconds=1), cfg)
    key = f"{start:%Y-%m-%d}"
    if now < freeze or now - freeze > GRACE or any(r.get("event") == "nightly" and r.get("state") == "candidate" and r.get("night") == key for r in rows):
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
    r.text(r.test_list(sha))
    row("published")
    return True


def when_due(cfg: Cfg | None, r: Runners | None, now: datetime, alert: Callable[[str], None], chains, threads: list) -> None:
    """At each tick: past the freeze with no candidate row for the night, journal the integration head as the candidate and start the
    nightly in its own thread (inline when `chains` is None, as the loop's other long jobs)."""
    if cfg is None or r is None:
        return
    night = candidate_due(now, cfg, journal.read())
    if not night:
        return
    sha = r.head()
    journal.append("nightly", state="candidate", night=night, sha=sha, detail="the integration head at the freeze")
    if chains is None:
        run_night(cfg, r, sha, night, alert)
    else:
        t = threading.Thread(target=run_night, args=(cfg, r, sha, night, alert), name="nightly", daemon=True)
        threads.append(t)
        t.start()


# --- the real runners -------------------------------------------------------------------------------------------------------

def _on(machine: str, script: str, timeout_s: float) -> tuple:
    """Run a shell script on `machine`: 'local' here, else `host[:dir]` over ssh. (rc, output). ponytail: no placement or lock logic."""
    if machine == "local":
        argv = ["bash", "-ec", script]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", machine.split(":")[0], script]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError) as e:
        return 1, str(e)
    return p.returncode, (p.stdout + p.stderr)[-2000:]


def _clean_tree(origin: str, sha: str, tree: str) -> str:
    """Shell: a fresh clone of `origin` checked out at `sha` in `tree` (never the loop's checkout)."""
    return f"rm -rf {shlex.quote(tree)} && git clone -q --no-checkout {shlex.quote(origin)} {shlex.quote(tree)} && git -C {shlex.quote(tree)} checkout -q {shlex.quote(sha)}"


def real_runners(root, cfg: Cfg, branch: str, state, texter: Callable[[str], None] | None = None) -> Runners:
    """Runners over clean clones of `origin` at the frozen sha. The check runs `builder verify-all --full` in its tree; the DMG runs
    `release_guard.py auto-notes <version>` and then `release-all.sh --dev --skip-testflight` in its own. ponytail: the smoke and the
    publish assume the DMG machine is where they run; one machine per part, no placement."""
    u = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    if u.returncode:
        raise RuntimeError(f"no origin remote in {root}: the nightly clones it")
    origin = u.stdout.strip()
    work = f"/tmp/fichero-nightly-{os.getpid()}"

    def tree(part: str) -> str:
        return f"{work}-{part}"

    def check(sha):
        t = tree("check")
        return _on(cfg.check_runner, f"{_clean_tree(origin, sha, t)} && cd {t}/fichero-builder && GATE_FOOTPRINT_MB={cfg.check_footprint_mb} PYTHONPATH=. python3 -m fichero_builder verify-all --full --root {t} --state {shlex.quote(str(state))}", 14400)

    def dmg(sha):
        t = tree("dmg")
        version = f"$(sed -n 's/^MARKETING_VERSION = //p' {t}/fichero/Configs/Version.xcconfig | head -1)"
        return _on(cfg.build_machine, f"{_clean_tree(origin, sha, t)} && cd {t} && python3 scripts/release_guard.py auto-notes {version} && scripts/release-all.sh --dev --skip-testflight", 7200)

    def smoke(sha):
        return _on(cfg.smoke_machine, f"cd {tree('dmg')} && scripts/smoke-release-embedded-backend.sh", 3600)

    def publish(sha):
        return _on(cfg.build_machine, f"cd {tree('dmg')} && scripts/release-all.sh --{cfg.publish} --skip-dmg --github --prerelease", 7200)

    def text(msg):
        to = os.environ.get("FICHERO_NIGHTLY_TEXT_TO")
        if not to:
            raise RuntimeError("FICHERO_NIGHTLY_TEXT_TO names nobody to text")
        script = f'tell application "Messages" to send {_as(msg)} to participant {_as(to)} of (1st account whose service type = iMessage)'
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)

    def test_list(sha):
        p = subprocess.run(["git", "-C", str(root), "log", "--format=- %s", f"origin/main..{sha}"], capture_output=True, text=True)
        return f"Fichero dev build {sha[:9]} is published. To try:\n" + "\n".join(p.stdout.splitlines()[:30])

    def head():
        out = subprocess.run(["git", "-C", str(root), "rev-parse", f"origin/{branch}"], capture_output=True, text=True)
        if out.returncode:
            raise RuntimeError(f"no origin/{branch}: {out.stderr.strip()}")
        return out.stdout.strip()
    return Runners(head=head, check=check, dmg=dmg, smoke=smoke, publish=publish, text=texter or text, test_list=test_list)


def _as(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

