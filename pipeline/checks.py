"""The per-item checks: the profile's ladder, each rung an existing script, run in a SCRATCH TREE made of the task's
committed HEAD with the pinned checkout's check files laid over it (pipeline.pinned-checks). So a guard that scans
`ROOT = Path(__file__).parent.parent` sees the coder's diff, never the pinned tree and never uncommitted edits; and
the coder cannot change the check it is judged by. Plus the built-in red-on-base."""
from __future__ import annotations

import fnmatch
import glob
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pipeline import ROOT, STATE


# Every git the runner runs itself has hooks OFF: a coder can write `objects/` and its own ref but never `hooks/` or
# `config`; this closes the other half (round-2 review HIGH). Raw ["git", ...] calls in the runner go through GIT.
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false"]


def sh(cmd, cwd, env=None, timeout=1800) -> subprocess.CompletedProcess:
    args = cmd if isinstance(cmd, list) else cmd.split()
    if args[:1] == ["git"]:
        args = GIT + args[1:]
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def git(wt, *args) -> str:
    r = sh(["git", *args], cwd=wt)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def scratch_dir(prefix: str) -> str:
    """Scratch trees and base dirs live under the state dir, which the sandbox denies the coder, never under the
    coder's writable TMPDIR (round-2 review MED)."""
    d = STATE / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=d)


def changed_files(wt, since, filter="AMR", head="HEAD") -> list[str]:
    return [f for f in git(wt, "diff", "--name-only", f"--diff-filter={filter}", f"{since}...{head}").splitlines() if f]


def touches(files, prefixes) -> list[str]:
    return [f for f in files if any(f.startswith(p) for p in prefixes)]


def test_env(tree, cfg) -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TERM", "LANG")}
    env.update(cfg["repo"].get("test_env", {}))
    if cfg["repo"].get("python_path"):
        env["PYTHONPATH"] = ":".join(str(Path(tree) / p) for p in cfg["repo"]["python_path"].split(":"))
    if cfg["repo"].get("scratch_base_env"):
        env[cfg["repo"]["scratch_base_env"]] = scratch_dir("pipeline-base-")
    return env


def fill(s: str, tree, **kw) -> str:
    return s.format(pinned=tree, python=sys.executable, **kw)


def isolated(script: str, env: dict) -> list[str]:
    """Run a guard with `python -I`: site runs on the interpreter's own path, so a coder-added sitecustomize.py or
    .pth in the tree is never imported and PYTHONPATH is not read from the environment; the tree's script dir and
    its source paths are added only afterwards, by us."""
    paths = [p for p in [str(Path(script).parent), *env.get("PYTHONPATH", "").split(":")] if p]
    # the tree's paths go AFTER the stdlib and site entries, so a coder-added pathlib.py or json.py in a source root
    # cannot shadow the stdlib the guards import (round-3 review R1)
    code = (f"import sys, runpy; i = next((n for n, p in enumerate(sys.path) if 'site-packages' in p), len(sys.path)); "
            f"sys.path[i:i] = {paths!r}; runpy.run_path({script!r}, run_name='__main__')")
    return [sys.executable, "-I", "-c", code]


def pinned_files(pinned, check_paths) -> tuple[str, list[str]]:
    """The pinned checkout's committed HEAD and every tracked file under the check paths."""
    sha = git(pinned, "rev-parse", "HEAD")
    tracked = git(pinned, "ls-tree", "-r", "--name-only", sha).splitlines()
    return sha, touches(tracked, check_paths)


def scratch_tree(wt, at, pinned_sha=None, files=()) -> str:
    """A detached worktree of `at`, with the pinned check files checked out over it when given."""
    tree = scratch_dir("pipeline-tree-")
    git(wt, "worktree", "add", "--detach", "-q", tree, at)
    if pinned_sha and files:
        r = sh(["git", "checkout", pinned_sha, "--", *files], cwd=tree)
        if r.returncode:  # never fall through to the coder's copies
            drop_tree(wt, tree)
            raise RuntimeError(f"could not lay the pinned checks over the tree: {r.stderr.strip()[-300:]}")
    return tree


BYPASS_NAMES = ("sitecustomize.py", "usercustomize.py")


def bypass_files(wt, since, cfg, head="HEAD") -> list[str]:
    """Added files that would run before or instead of the checks: a sitecustomize/usercustomize or a .pth anywhere,
    a conftest.py outside a test dir, or a module named like a stdlib one at a root on the guards' path (scripts/
    or any `python_path` folder), which would shadow the import (round-3 review R1)."""
    roots = ["scripts", *[p.strip("/") for p in (cfg["repo"].get("python_path") or "").split(":") if p]]
    bad = []
    for f in changed_files(wt, since, "A", head):
        p = Path(f)
        if p.name in BYPASS_NAMES or p.suffix == ".pth":
            bad.append(f)
        elif p.name == "conftest.py" and not any("test" in part.lower() for part in p.parent.parts):
            bad.append(f)
        elif p.suffix == ".py" or p.name == "__init__.py":
            for root in roots:
                rel = Path(f).relative_to(root) if root != "." and f.startswith(root + "/") else (Path(f) if root == "." else None)
                if rel is not None and (rel.parts[0].removesuffix(".py") in sys.stdlib_module_names):
                    bad.append(f)
                    break
    return bad


def claude_dir_changed(wt, since, head="HEAD") -> list[str]:
    """Anything added, changed or left untracked under the worktree's .claude/: a hook put there would run outside the
    sandbox at the next session start, so it is a pinned red before every check and relaunch (round-2 review MED)."""
    committed = [f for f in changed_files(wt, since, "AMR", head) if f.startswith(".claude/")]
    # --ignored too: a global gitignore often hides `.claude/settings.local.json`, and an ignored hook still runs
    status = sh(["git", "status", "--porcelain", "--ignored", "--untracked-files=all", "--", ".claude"], cwd=wt).stdout.splitlines()
    return sorted(set(committed + [line[3:] for line in status if line.strip()]))


TAG_RE = re.compile(r"\[(?:OK|PARTIAL|MISSING|GAP|BROKEN|PROPOSED)[^\]]*\]|\(#\d+\)")


def acceptance_lines(text: str, ids) -> list[str]:
    """The item's acceptance in a spec, normalised: its behaviour bullets (continuation lines included) and the
    Behaviours/Tests lines of the build-order step that names one of its ids — with status tags and `(#N)` removed,
    so flipping [MISSING] to [OK] or adding the issue number is not a change (round-3 review R4)."""
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s*- `[a-z][a-z0-9-]*\.[a-z0-9.-]+`", line) and any(f"`{x}`" in line for x in ids):
            block = [line]
            for nxt in lines[i + 1:]:
                if nxt.startswith("  ") and not nxt.lstrip().startswith("- "):
                    block.append(nxt)
                else:
                    break
            out.append(" ".join(b.strip() for b in block))
    for m in re.finditer(r"^#### Step .*?(?=^#### Step |^### |^## |\Z)", text, re.S | re.M):
        step = m.group(0)
        if any(f"`{x}`" in step for x in ids):
            out += [s.strip() for s in step.splitlines() if s.strip().startswith(("- Tests:", "- Behaviours:"))]
    return [re.sub(r"\s+", " ", TAG_RE.sub("", s)).strip() for s in out]


def acceptance_changed(wt, since, spec_dir, ids, head="HEAD") -> list[str]:
    """The item's own acceptance differs between `since` and HEAD in some changed spec file: the coder may not
    rewrite it (dogfood 6); a tag flip or an added `(#N)` is fine (R4). Returns the lines that differ."""
    if not spec_dir or not ids:
        return []
    hits = []
    for f in changed_files(wt, since, head=head):
        if not f.startswith(spec_dir.rstrip("/") + "/") or not f.endswith(".md"):
            continue
        old = sh(["git", "show", f"{since}:{f}"], cwd=wt).stdout
        new = sh(["git", "show", f"{head}:{f}"], cwd=wt).stdout
        before, after = acceptance_lines(old, ids), acceptance_lines(new, ids)
        if before != after:
            hits += [f"{f}: - {s[:160]}" for s in before if s not in after] + [f"{f}: + {s[:160]}" for s in after if s not in before]
    return hits


def drop_tree(wt, tree) -> None:
    sh(["git", "worktree", "remove", "--force", tree], cwd=wt)


def red_on_base(wt, tree, since, files, rung, cfg, head="HEAD") -> tuple[bool, str]:
    """Each changed or new test file, copied onto a scratch tree at `since` (the item's start), must FAIL there
    on its own, and all must PASS on the branch."""
    if not files:
        return False, "no test file changed: a source change needs a test (red on base, green on the branch)"
    head = git(wt, "rev-parse", head)
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


def run_rung(rung, wt, tree, cfg, files, since, head="HEAD") -> tuple[bool, str]:
    if rung.get("enabled") is False:
        return True, "skipped (disabled in the profile)"
    if rung.get("paths") and not touches(files, rung["paths"]):
        return True, "skipped (diff does not touch its paths)"
    if rung.get("kind") == "red-on-base":
        tests = [f for f in changed_files(wt, since, "AM", head) if any(fnmatch.fnmatch(f, g) for g in rung["test_glob"])]
        return red_on_base(wt, tree, since, tests, rung, cfg, head)
    env = test_env(tree, cfg)
    if "glob" in rung:  # the fast guards
        bad = []
        for s in sorted(glob.glob(fill(rung["glob"], tree))):
            if any(k in s for k in rung.get("skip", [])):
                continue
            try:
                budget = rung.get("budget_s", {}).get(Path(s).stem, rung.get("timeout_s", 60))
                r = sh(isolated(s, env), cwd=tree, env=env, timeout=budget)
                if r.returncode:
                    bad.append(f"{Path(s).name}:\n{tail(r.stdout + r.stderr)}")
            except subprocess.TimeoutExpired:
                bad.append(f"{Path(s).name}: over its {budget} s budget (move it to the profile's [ladder.skip] with a reason, or raise [ladder.budget_s])")
        if not bad:
            return True, "all guards green"
        # the HEAD of the list of failing guards is never lost; each guard's output is its own tail
        names = ", ".join(b.split(":", 1)[0] for b in bad)
        return False, f"{len(bad)} guard(s) red: {names}\n\n" + "\n\n".join(bad)[:12000]
    out = []
    for cmd in rung["cmd"] if isinstance(rung["cmd"], list) else [rung["cmd"]]:
        r = sh(fill(cmd, tree, files=" ".join(files)), cwd=tree, env=env)
        out.append(tail(r.stdout + r.stderr))
        if r.returncode:
            return False, "\n".join(out)
    return True, "\n".join(out)[-600:]


def tail(text: str, lines: int = 40, chars: int = 4000, line_chars: int = 300) -> str:
    """A failing rung's text carries its tool's actual output: the last 40 lines, each at most 300 chars, 4000 in
    all (a coder told only "ruff failed" fixed the wrong thing twice on 2026-10-25; the caps keep the journal and
    the brief bounded)."""
    kept = [ln[:line_chars] for ln in text.strip().splitlines()[-lines:]]
    return "\n".join(kept)[-chars:]


def changed_checks(wt, since, cfg, pinned=None, approved=(), head="HEAD") -> tuple[str, list[str], list[str]]:
    """(pinned sha, the pinned check files to lay over the tree, the pinned checks the diff changes). A check change
    the maintainer approved (`approve-checks`) is neither laid over nor a red: the coder's copy is what runs."""
    pinned = pinned or cfg["repo"].get("pinned") or ROOT
    pinned_sha, overlay = pinned_files(pinned, cfg["repo"]["check_paths"])
    overlay = [f for f in overlay if f not in approved]
    return pinned_sha, overlay, [f for f in changed_files(wt, since, "MDR", head) if f in overlay]


def run_all(wt, cfg, since=None, pinned=None, protected_ids=(), approved=(), head="HEAD") -> list[dict]:
    """Every rung, in order, timed; stops at the first red so the coder gets one failure at a time. First the
    pinned-checks rules, which end in needs-maintainer: a changed pinned check, a file that would bypass the checks,
    or a rewrite of the item's own acceptance in the spec. `head`: the commit to judge (a done sha, so a
    worker that moved on to the next issue does not change what this one is judged on; the live HEAD by default)."""
    since = since or cfg["repo"]["base"]
    files = changed_files(wt, since, head=head)
    # a coder may add a guard, and keep editing a guard of its own that the pinned runner does not have yet (a
    # Stage 1 step over several commits); it may never change or remove a check the PINNED checkout runs
    pinned_sha, overlay, hit = changed_checks(wt, since, cfg, pinned, approved, head)
    why = f"the diff changes the checks themselves ({', '.join(hit[:5])})" if hit else ""
    bypass = bypass_files(wt, since, cfg, head)
    if bypass and not why:
        why = f"the diff adds a file that would run before or instead of the checks ({', '.join(bypass[:5])})"
    claude = claude_dir_changed(wt, since, head)
    if claude and not why:
        why = f"the worktree's .claude/ changed ({', '.join(claude[:5])}): a hook there would run outside the sandbox"
    changed = acceptance_changed(wt, since, cfg["repo"].get("specs"), protected_ids, head)
    if changed and not why:
        why = "the diff rewrites the item's own acceptance in the spec; use `ask` instead:\n" + "\n".join(changed[:8])
    if why:
        return [{"name": "pinned-checks", "ok": False, "seconds": 0, "text": f"{why}: needs-maintainer"}]
    try:
        tree = scratch_tree(wt, git(wt, "rev-parse", head), pinned_sha, overlay)
    except RuntimeError as e:  # the overlay failed: never judge the coder's copies
        return [{"name": "pinned-checks", "ok": False, "seconds": 0, "text": str(e)}]
    results = [{"name": "pinned-checks", "ok": True, "seconds": 0,
                "text": f"checks from {pinned_sha[:9]} ({len(overlay)} files) over the task's HEAD"}]
    try:
        for rung in cfg["ladder"]:
            t = time.time()
            try:
                ok, text = run_rung(rung, wt, tree, cfg, files, since, head)
            except Exception as e:  # noqa: BLE001 - a broken rung is a red rung, with its text
                ok, text = False, f"{type(e).__name__}: {e}"
            results.append({"name": rung["name"], "ok": ok, "text": text, "seconds": round(time.time() - t, 1)})
            if not ok:
                break
    finally:
        drop_tree(wt, tree)
    return results
