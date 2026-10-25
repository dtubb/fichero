"""The per-item checks: the profile's ladder, each rung an existing script, run in a SCRATCH TREE made of the task's
committed HEAD with the pinned checkout's check files laid over it (pipeline.pinned-checks). So a guard that scans
`ROOT = Path(__file__).parent.parent` sees the coder's diff, never the pinned tree and never uncommitted edits; and
the coder cannot change the check it is judged by. Plus the built-in red-on-base."""
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


def changed_files(wt, since, filter="AMR") -> list[str]:
    return [f for f in git(wt, "diff", "--name-only", f"--diff-filter={filter}", f"{since}...HEAD").splitlines() if f]


def touches(files, prefixes) -> list[str]:
    return [f for f in files if any(f.startswith(p) for p in prefixes)]


def test_env(tree, cfg) -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TERM", "LANG")}
    env.update(cfg["repo"].get("test_env", {}))
    if cfg["repo"].get("python_path"):
        env["PYTHONPATH"] = ":".join(str(Path(tree) / p) for p in cfg["repo"]["python_path"].split(":"))
    if cfg["repo"].get("scratch_base_env"):
        env[cfg["repo"]["scratch_base_env"]] = tempfile.mkdtemp(prefix="pipeline-base-")
    return env


def fill(s: str, tree, **kw) -> str:
    return s.format(pinned=tree, python=sys.executable, **kw)


def pinned_files(pinned, check_paths) -> tuple[str, list[str]]:
    """The pinned checkout's committed HEAD and every tracked file under the check paths."""
    sha = git(pinned, "rev-parse", "HEAD")
    tracked = git(pinned, "ls-tree", "-r", "--name-only", sha).splitlines()
    return sha, touches(tracked, check_paths)


def scratch_tree(wt, at, pinned_sha=None, files=()) -> str:
    """A detached worktree of `at`, with the pinned check files checked out over it when given."""
    tree = tempfile.mkdtemp(prefix="pipeline-tree-")
    git(wt, "worktree", "add", "--detach", "-q", tree, at)
    if pinned_sha and files:
        sh(["git", "checkout", pinned_sha, "--", *files], cwd=tree)
    return tree


def drop_tree(wt, tree) -> None:
    sh(["git", "worktree", "remove", "--force", tree], cwd=wt)


def red_on_base(wt, tree, since, files, rung, cfg) -> tuple[bool, str]:
    """Each changed or new test file, copied onto a scratch tree at `since` (the item's start), must FAIL there
    on its own, and all must PASS on the branch."""
    if not files:
        return False, "no test file changed: a source change needs a test (red on base, green on the branch)"
    head = git(wt, "rev-parse", "HEAD")
    base = scratch_tree(wt, since)
    try:
        sh(["git", "checkout", head, "--", *files], cwd=base)  # a new file: not on base, checkout still copies it
        env = test_env(base, cfg)
        for f in files:
            on_base = sh(fill(rung["pytest"], tree, files=f), cwd=base, env=env)
            if on_base.returncode == 0:
                return False, f"NOT RED ON BASE: {f} passes at {since[:9]}, so it proves nothing:\n{on_base.stdout[-1200:]}"
        here = sh(fill(rung["pytest"], tree, files=" ".join(files)), cwd=tree, env=test_env(tree, cfg))
        if here.returncode:
            return False, f"RED ON THE BRANCH:\n{(here.stdout + here.stderr)[-3000:]}"
        return True, f"red on base, green on the branch ({len(files)} test file(s))"
    finally:
        drop_tree(wt, base)


def run_rung(rung, wt, tree, cfg, files, since) -> tuple[bool, str]:
    if rung.get("enabled") is False:
        return True, "skipped (disabled in the profile)"
    if rung.get("paths") and not touches(files, rung["paths"]):
        return True, "skipped (diff does not touch its paths)"
    if rung.get("kind") == "red-on-base":
        tests = [f for f in changed_files(wt, since, "AM") if any(fnmatch.fnmatch(f, g) for g in rung["test_glob"])]
        return red_on_base(wt, tree, since, tests, rung, cfg)
    env = test_env(tree, cfg)
    if "glob" in rung:  # the fast guards
        bad = []
        for s in sorted(glob.glob(fill(rung["glob"], tree))):
            if any(k in s for k in rung.get("skip", [])):
                continue
            try:
                r = sh([sys.executable, s], cwd=tree, env=env, timeout=rung.get("timeout_s", 60))
                if r.returncode:
                    bad.append(f"{Path(s).name}: {(r.stdout + r.stderr).strip()[-400:]}")
            except subprocess.TimeoutExpired:
                bad.append(f"{Path(s).name}: timeout")
        return not bad, "\n".join(bad) or "all guards green"
    out = []
    for cmd in rung["cmd"] if isinstance(rung["cmd"], list) else [rung["cmd"]]:
        r = sh(fill(cmd, tree, files=" ".join(files)), cwd=tree, env=env)
        out.append((r.stdout + r.stderr).strip()[-2000:])
        if r.returncode:
            return False, "\n".join(out)
    return True, "\n".join(out)[-600:]


def run_all(wt, cfg, since=None, pinned=None) -> list[dict]:
    """Every rung, in order, timed; stops at the first red so the coder gets one failure at a time."""
    pinned = pinned or cfg["repo"].get("pinned") or ROOT
    since = since or cfg["repo"]["base"]
    files = changed_files(wt, since)
    # a coder may ADD a guard (a Stage 1 step) but never change or remove a check it is judged by
    hit = touches(changed_files(wt, since, "MDR"), cfg["repo"]["check_paths"])
    if hit:
        return [{"name": "pinned-checks", "ok": False, "seconds": 0,
                 "text": f"the diff changes the checks themselves ({', '.join(hit[:5])}): needs-maintainer"}]
    pinned_sha, overlay = pinned_files(pinned, cfg["repo"]["check_paths"])
    tree = scratch_tree(wt, git(wt, "rev-parse", "HEAD"), pinned_sha, overlay)
    results = [{"name": "pinned-checks", "ok": True, "seconds": 0,
                "text": f"checks from {pinned_sha[:9]} ({len(overlay)} files) over the task's HEAD"}]
    try:
        for rung in cfg["ladder"]:
            t = time.time()
            try:
                ok, text = run_rung(rung, wt, tree, cfg, files, since)
            except Exception as e:  # noqa: BLE001 - a broken rung is a red rung, with its text
                ok, text = False, f"{type(e).__name__}: {e}"
            results.append({"name": rung["name"], "ok": ok, "text": text, "seconds": round(time.time() - t, 1)})
            if not ok:
                break
    finally:
        drop_tree(wt, tree)
    return results
