"""The per-item checks: the profile's ladder, each rung an existing script run FROM the pinned runner checkout WITH
the task's worktree as cwd (pipeline.pinned-checks, gate-runs-in-the-worktree), plus the built-in red-on-base."""
from __future__ import annotations

import fnmatch
import glob
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pipeline import ROOT


def sh(cmd, cwd, env=None, timeout=1800) -> subprocess.CompletedProcess:
    args = cmd if isinstance(cmd, list) else cmd.split()
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def git(wt, *args) -> str:
    r = sh(["git", *args], cwd=wt)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def changed_files(wt, since) -> list[str]:
    return [f for f in git(wt, "diff", "--name-only", f"{since}...HEAD").splitlines() if f]


def touches(files, prefixes) -> list[str]:
    return [f for f in files if any(f.startswith(p) for p in prefixes)]


def test_env(wt, cfg) -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TERM", "LANG")}
    env.update(cfg["repo"].get("test_env", {}))
    if cfg["repo"].get("python_path"):
        env["PYTHONPATH"] = ":".join(str(Path(wt) / p) for p in cfg["repo"]["python_path"].split(":"))
    if cfg["repo"].get("scratch_base_env"):
        env[cfg["repo"]["scratch_base_env"]] = tempfile.mkdtemp(prefix="pipeline-base-")
    return env


def fill(s: str, **kw) -> str:
    return s.format(pinned=kw.get("pinned", ROOT), python=sys.executable, **{k: v for k, v in kw.items() if k != "pinned"})


def red_on_base(wt, base, files, rung, cfg, pinned) -> tuple[bool, str]:
    """The branch's changed test files, copied onto a scratch worktree at `base`, must FAIL there and PASS here."""
    if not files:
        return False, "no test file changed: a source change needs a test (red on base, green on the branch)"
    head = git(wt, "rev-parse", "HEAD")
    scratch = tempfile.mkdtemp(prefix="pipeline-red-")
    git(wt, "worktree", "add", "--detach", "-q", scratch, base)
    try:
        sh(["git", "checkout", head, "--", *files], cwd=scratch)  # a new file: not on base, checkout still copies it
        cmd = fill(rung["pytest"], files=" ".join(files), pinned=pinned)
        on_base = sh(cmd, cwd=scratch, env=test_env(scratch, cfg))
        if on_base.returncode == 0:
            return False, f"NOT RED ON BASE: the changed tests pass on {base}, so they prove nothing:\n{on_base.stdout[-1500:]}"
        here = sh(cmd, cwd=wt, env=test_env(wt, cfg))
        if here.returncode:
            return False, f"RED ON THE BRANCH:\n{(here.stdout + here.stderr)[-3000:]}"
        return True, f"red on base, green on the branch ({len(files)} test file(s))"
    finally:
        sh(["git", "worktree", "remove", "--force", scratch], cwd=wt)


def run_rung(rung, wt, cfg, files, pinned) -> tuple[bool, str]:
    if rung.get("enabled") is False:
        return True, "skipped (disabled in the profile)"
    if rung.get("paths") and not touches(files, rung["paths"]):
        return True, "skipped (diff does not touch its paths)"
    if rung.get("kind") == "red-on-base":
        tests = [f for f in files if any(fnmatch.fnmatch(f, g) for g in rung["test_glob"])]
        return red_on_base(wt, cfg["repo"]["base"], tests, rung, cfg, pinned)
    env = test_env(wt, cfg)
    if "glob" in rung:  # the fast guards
        bad = []
        for s in sorted(glob.glob(fill(rung["glob"], pinned=pinned))):
            if any(k in s for k in rung.get("skip", [])):
                continue
            try:
                r = sh([sys.executable, s], cwd=wt, env=env, timeout=rung.get("timeout_s", 60))
                if r.returncode:
                    bad.append(f"{Path(s).name}: {(r.stdout + r.stderr).strip()[-400:]}")
            except subprocess.TimeoutExpired:
                bad.append(f"{Path(s).name}: timeout")
        return not bad, "\n".join(bad) or "all guards green"
    out = []
    for cmd in rung["cmd"] if isinstance(rung["cmd"], list) else [rung["cmd"]]:
        r = sh(fill(cmd, files=" ".join(files), pinned=pinned), cwd=wt, env=env)
        out.append((r.stdout + r.stderr).strip()[-2000:])
        if r.returncode:
            return False, "\n".join(out)
    return True, "\n".join(out)[-600:]


def run_all(wt, cfg, since=None, pinned=None) -> list[dict]:
    """Every rung, in order, timed; stops at the first red so the coder gets one failure at a time."""
    pinned = pinned or cfg["repo"].get("pinned") or ROOT
    files = changed_files(wt, since or cfg["repo"]["base"])
    results = []
    hit = touches(files, cfg["repo"]["check_paths"])
    if hit:
        return [{"name": "pinned-checks", "ok": False, "seconds": 0,
                 "text": f"the diff touches the checks themselves ({', '.join(hit[:5])}): needs-maintainer"}]
    for rung in cfg["ladder"]:
        t = time.time()
        try:
            ok, text = run_rung(rung, wt, cfg, files, pinned)
        except Exception as e:  # noqa: BLE001 - a broken rung is a red rung, with its text
            ok, text = False, f"{type(e).__name__}: {e}"
        results.append({"name": rung["name"], "ok": ok, "text": text, "seconds": round(time.time() - t, 1)})
        if not ok:
            break
    return results
