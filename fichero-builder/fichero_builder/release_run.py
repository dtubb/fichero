"""dev-workflows.run.release-stages (#6726): the nightly Mac + iOS release as a list of named stages.

Each stage writes its result to the journal; a run resumes from the first stage that is not green, so nothing that passed is
rebuilt. No model runs while stages are green. A red stage starts ONE manager session with that stage's log and the stage list;
if it reports success the run resumes at that stage, else the owner is texted what is red. Pure rules and the stage loop only:
the real stage commands are `real_stages`, the tests give `run` fakes."""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from fichero_builder import journal

# Groups run one after the other; a group's chains run side by side (Mac DMG on one machine, iOS on another).
PLAN: list[list[list[str]]] = [
    [["sweep"]], [["freeze"]], [["verify"]],
    [["engine", "mac-dmg", "notarize"], ["ios"]],
    [["publish"]], [["merge"]], [["text"]],
]
STAGES = [s for g in PLAN for c in g for s in c]
Stage = Callable[[], tuple]  # () -> (rc, output)


def rows(run_id: str) -> list[dict]:
    return [r for r in journal.read() if r.get("event") == "release" and r.get("run") == run_id]


def green(run_id: str) -> set[str]:
    """Stages whose latest row in this run is green (a later red row for the same stage cancels an earlier green)."""
    last: dict = {}
    for r in rows(run_id):
        last[r["stage"]] = r["state"]
    return {s for s, st in last.items() if st == "green"}


def _stage_row(run_id: str, stage: str, state: str, detail: str = "") -> None:
    journal.append("release", run=run_id, stage=stage, state=state, detail=detail[-2000:])


def _try(fn: Stage) -> tuple:
    try:
        return fn()
    except (RuntimeError, OSError, ValueError) as e:  # a stage that cannot run is red with its reason
        return 1, f"{type(e).__name__}: {e}"


def run(run_id: str, stages: dict[str, Stage], manager: Callable[[str, str, list[str]], bool], alert: Callable[[str], None],
        plan: list = PLAN) -> bool:
    """Run (or resume) the run `run_id`. Returns whether every stage is green. The manager is called at most once per run."""
    asked = [False]

    def chain(names: list[str], failed: list) -> None:
        for name in names:
            if name in green(run_id):
                continue
            rc, out = _try(stages[name])
            _stage_row(run_id, name, "green" if rc == 0 else "red", out)
            if rc:
                failed.append((name, out))
                return

    for group in plan:
        failed: list = []
        while True:
            failed.clear()
            ts = [threading.Thread(target=chain, args=(c, failed)) for c in group]
            [t.start() for t in ts]
            [t.join() for t in ts]
            if not failed:
                break
            name, out = failed[0]
            if asked[0]:
                alert(f"the release {run_id} is red at {name} again after the manager: {(out.strip().splitlines() or [''])[-1]}")
                return False
            asked[0] = True
            _stage_row(run_id, name, "manager", "the manager session was started")
            if not _try(lambda: (0 if manager(name, out, [s for g in plan for c in g for s in c]) else 1, ""))[0] == 0:
                alert(f"the release {run_id} is red at {name} and the manager could not fix it: {(out.strip().splitlines() or [''])[-1]}")
                return False
    return True


# --- before building: a runner that is awake, reachable and over the disk floor ---------------------------------------------

def pick_runner(candidates: list[str], probe: Callable[[str], int | None], floor_gb: int) -> str:
    """The first candidate whose probe returns its free disk in GB (None = asleep or unreachable) at or over the floor."""
    seen = []
    for m in candidates:
        free = probe(m)
        if free is not None and free >= floor_gb:
            return m
        seen.append(f"{m}: {'unreachable' if free is None else f'{free} GB free'}")
    raise RuntimeError(f"no runner is awake, reachable and over {floor_gb} GB: " + "; ".join(seen))


def protected(path: Path, live: list[Path]) -> bool:
    """True when `path` is, holds or is under one of `live` (resolved: integration/.venv is a link into a venv that must stay)."""
    for p in {path.absolute(), path.resolve()}:  # the link's own place and what it points to both count
        for r in {x.absolute() for x in live} | {x.resolve() for x in live}:
            if p == r or r in p.parents or p in r.parents:
                return True
    return False


def sweep(candidates: list[Path], live: list[Path]) -> list[str]:
    """Delete each candidate that is not live; one line per path removed. Never raises on a missing path."""
    done = []
    for c in candidates:
        if not c.exists() or protected(c, live):
            continue
        shutil.rmtree(c) if c.is_dir() and not c.is_symlink() else c.unlink()
        done.append(f"removed {c}")
    return done


def engine_key(root: Path) -> str:
    """A hash of uv.lock and the engine sources: the engine bundle is reused while it is unchanged."""
    h = hashlib.sha256()
    files = [root / "fichero-server" / "uv.lock", *sorted((root / "fichero-server").rglob("*.py"))]
    for f in files:
        if f.is_file():
            h.update(str(f.relative_to(root)).encode() + b"\0" + f.read_bytes())
    return h.hexdigest()


# --- the real stages and manager -------------------------------------------------------------------------------------------

def _sh(script: str, machine: str, timeout_s: float) -> tuple:
    from fichero_builder.nightly import _on
    return _on(machine, script, timeout_s)


def real_stages(root, state, run_id: str, *, mac: str, ios: str, check_runner: str, floor_gb: int, text: Callable[[str], None]) -> dict[str, Stage]:
    """Stage callables over `root`. ponytail: the Mac app, DMG and notarize are release-all.sh's own steps (one script builds the
    app and the DMG), so mac-dmg builds both and notarize is the same script resumed; one machine per chain, no placement beyond
    `pick_runner`."""
    root, state = Path(root), Path(state)
    r = shlex.quote(str(root))
    marker = state / "release" / "engine.key"

    def disk(m):
        rc, out = _sh("df -g / | awk 'NR==2{print $4}'", m, 30)
        return int(out.strip().splitlines()[-1]) if rc == 0 and out.strip().splitlines()[-1].isdigit() else None

    def do_sweep():
        pick_runner([mac, ios], disk, floor_gb)
        live = [root / "integration" / ".venv", root / ".venv"]
        lines = sweep([root / "fichero" / "build" / "xcode" / "Products", *Path(tempfile.gettempdir()).glob("fichero-nightly-*")], live)
        subprocess.run(["tmutil", "deletelocalsnapshots", "/"], capture_output=True, text=True)
        return 0, "\n".join(lines) or "nothing to sweep"

    def freeze():
        p = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
        return p.returncode, p.stdout.strip() or p.stderr

    def engine():
        key = engine_key(root)
        if marker.exists() and marker.read_text() == key:
            return 0, "engine bundle reused: uv.lock and engine sources unchanged"
        marker.parent.mkdir(parents=True, exist_ok=True)
        rc, out = _sh(f"cd {r} && scripts/build-release.sh", mac, 7200)
        if rc == 0:
            marker.write_text(key)
        return rc, out

    def text_stage():
        text(f"Fichero release {run_id} is green on every stage.")
        return 0, "texted"
    return {
        "sweep": do_sweep, "freeze": freeze,
        "verify": lambda: _sh(f"cd {r}/fichero-builder && PYTHONPATH=. python3 -m fichero_builder verify-all --full --root {r} --state {shlex.quote(str(state))}", check_runner, 14400),
        "engine": engine,
        "mac-dmg": lambda: _sh(f"cd {r} && scripts/release-all.sh --dev --mac-only --skip-testflight --skip-notarize", mac, 7200),
        "notarize": lambda: _sh(f"cd {r} && scripts/release-all.sh --dev --mac-only --skip-testflight", mac, 7200),
        "ios": lambda: _sh(f"cd {r} && scripts/release-all.sh --dev --ios-only --skip-dmg", ios, 7200),
        "publish": lambda: _sh(f"cd {r} && scripts/release-all.sh --dev --skip-dmg --skip-testflight --github --prerelease", mac, 7200),
        "merge": lambda: _sh(f"cd {r} && gh pr merge --squash --auto", "local", 600),
        "text": text_stage,
    }


def manager_session(state, claude: str, timeout_s: float = 7200) -> Callable[[str, str, list[str]], bool]:
    """One headless Claude session given the failed stage, its log and the stage list; True when it exits 0."""
    def call(stage: str, log: str, stages: list[str]) -> bool:
        d = Path(state) / "release"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"manager-{stage}.txt"
        f.write_text(f"The nightly release stage `{stage}` is red. Stages in order: {', '.join(stages)}.\n"
                     f"Fix the cause in this checkout, or decide what to do. Exit 0 only if the stage can now be run again.\n\nLog tail:\n{log}\n")
        try:
            p = subprocess.run([claude, "-p", f"Read {f} and follow it."], capture_output=True, text=True, timeout=timeout_s, env=os.environ)
        except (subprocess.TimeoutExpired, OSError):
            return False
        return p.returncode == 0
    return call
