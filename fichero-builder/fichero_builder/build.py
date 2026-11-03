"""`builder build --dev`: the owner's dev DMG as one command, so nobody re-derives the procedure (dev-workflows.tool.build). It runs
the project's own `scripts/build-release-dmg.sh` and rewrites none of it: the dev tier (Dev Embedded, every feature), the current
version so the script's auto-stamp leaves the tree alone, no notarizing. One journal row (event `build`), and the DMG's path
and PASSED or FAILED printed. A full release stays out: it needs the owner's yes and `scripts/release-all.sh`."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from fichero_builder import jail, journal


def _as_jail_user(root) -> bool:
    j = jail.load(root)
    return bool(j and j.user and j.is_self())


def _git(root, *args) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout.strip()


def main(a) -> int:
    root = Path(a.root)
    if not a.dev:
        print("REFUSED: only --dev builds here; a full release needs the owner's yes and scripts/release-all.sh")
        return 1
    if _as_jail_user(root):
        print("REFUSED: a worker never builds; the manager runs this as the owner")
        return 1
    script = root / "scripts" / "build-release-dmg.sh"
    version = root / "fichero" / "Configs" / "Version.xcconfig"
    m = re.search(r"^MARKETING_VERSION = (\S+)", version.read_text(), re.M) if version.is_file() else None
    if not m:
        print(f"REFUSED: no MARKETING_VERSION in {version}")
        return 1
    if not script.is_file():
        print(f"REFUSED: no {script}")
        return 1
    if not os.access(script, os.X_OK):
        print(f"REFUSED: {script} is not executable")
        return 1
    dmg = root / "build" / "releases" / "Fichero-dev.dmg"
    sha, dirty = _git(root, "rev-parse", "HEAD"), bool(_git(root, "status", "--porcelain"))
    journal.STATE.mkdir(parents=True, exist_ok=True)
    log = journal.STATE / f"build-{sha[:7]}.log"
    env = {**os.environ, "FICHERO_RELEASE_TIER": "dev", "FICHERO_RELEASE_VERSION": m.group(1), "FICHERO_DMG_PATH": str(dmg),
           "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])}  # the engine preflight calls a bare python3
    started = time.time()
    journal.append("activity", kind="build", key=f"build {sha[:9]}", state="start")
    print(f"building the dev DMG of {sha[:9]}{' with uncommitted changes' if dirty else ''}; log {log}", flush=True)
    with log.open("w") as f, journal.heavy("the dev build", yields=True):
        rc = subprocess.run([str(script)], cwd=str(root), env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    fresh = dmg.is_file() and dmg.stat().st_mtime >= started - 1
    ok = rc == 0 and fresh
    journal.append("activity", kind="build", key=f"build {sha[:9]}", state="end", ok=ok)
    journal.append("build", tier="dev", sha=sha, dirty=dirty, ok=ok, rc=rc, dmg=str(dmg) if ok else "", log=str(log), seconds=int(time.time() - started))
    if ok:
        print(f"PASSED {dmg}")
        return 0
    print(f"FAILED: exit {rc}{'' if rc else ', no new DMG'}; log {log}\n" + "\n".join(log.read_text(errors="replace").splitlines()[-20:]))
    return 1
