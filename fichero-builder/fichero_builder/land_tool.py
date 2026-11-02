"""land gate (dev-workflows Step 0.1 item 6; review 3 B6, review 4 B1/B3/B4/H5/H6): a READY verdict is keyed on the
ORDERED list of (sha256 of the diff bytes, message hash) plus the base sha of the whole range, so a subset or a replay is not the
reviewed range. The range base is the project's land branch (never a caller-named sha) and must be an ancestor of
head. The verdict store and the owner's log are owner-owned files outside the workroot, opened without following
symlinks. A merge commit or a commit without exactly one id is refused. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from fichero_builder.jail import real_git

GIT = real_git()  # never the xcrun shim (minutes of silence on a new user's first call)


_ATTR = ["-c", "core.attributesFile=/dev/null", "-c", "core.quotepath=off"]


def _check_owned(path: Path, st: os.stat_result, what: str) -> None:
    if st.st_uid != os.getuid() or st.st_mode & 0o022:
        raise PermissionError(f"{what} {path} must be owned by us and not group/other-writable")


def _safe_open(path, flags: int, mode: int = 0o600):
    """Open without following a symlink; refuse a file or parent dir we do not own or others can write
    (the worker user can plant a symlink or a file in a shared dir; macOS has no protected_symlinks)."""
    p = Path(path)
    _check_owned(p.parent, p.parent.stat(), "parent dir")
    fd = os.open(p, flags | os.O_NOFOLLOW, mode)
    try:
        _check_owned(p, os.fstat(fd), "file")
    except PermissionError:
        os.close(fd)
        raise
    return fd


def safe_read(path) -> str:
    fd = _safe_open(path, os.O_RDONLY)
    with os.fdopen(fd) as f:
        return f.read()


def safe_append(path, text: str) -> None:
    fd = _safe_open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
    with os.fdopen(fd, "a") as f:
        f.write(text)


def journal_problem(path) -> str:
    """Why a landing may not trust this journal, or '': its check row allows a push and its rows name worktrees to remove, so
    the file and its folder must be this user's and no one else's to write. A missing file has no row to trust."""
    p = Path(path)
    try:
        if p.exists() or p.is_symlink():
            _check_owned(p, p.lstat(), "journal")
            _check_owned(p.parent, p.parent.stat(), "journal folder")
    except OSError as e:
        return str(e)
    return ""


def green_row(rows: list[dict], head: str, since: str) -> dict | None:
    """The green `check` row of exactly since..head. The ladder runs once, in the check, so a row over any other range is not
    that ladder. A --maintainer row counts: a person typed the flag, no worker can; the row says so and the landing repeats it."""
    return next((r for r in reversed(rows) if r.get("event") == "check" and r.get("head") == head and r.get("since") == since and r.get("ok") is True), None)


def log_problem(path) -> str:
    """Why the land log cannot be appended to, or ''. Checked before any work, and creates nothing: a directory here once
    died with a traceback at the end of a six-minute ladder."""
    p = Path(path)
    if p.is_dir():
        return f"{p} is a directory, not a log file"
    if not p.parent.is_dir() or not os.access(p.parent, os.W_OK):
        return f"{p.parent} is not a directory this user can write"
    try:
        _check_owned(p.parent, p.parent.stat(), "parent dir")
        if p.exists() or p.is_symlink():
            safe_append(p, "")
    except OSError as e:
        return f"{p}: {e}"
    return ""


def safe_write(path, text: str) -> None:
    fd = _safe_open(path, os.O_WRONLY | os.O_CREAT)
    with os.fdopen(fd, "w") as f:
        f.truncate(0)
        f.write(text)


def _git(root, *args) -> str:
    return _gitb(root, *args).decode("utf-8", "replace")


def _gitb(root, *args) -> bytes:
    r = subprocess.run([GIT, "-C", str(root), *_ATTR, *args], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return r.stdout


def commit_keys(root, base: str, head: str) -> list[dict]:
    """[{sha, diff_hash, message_hash}] oldest first. Raises ValueError on a merge or a commit with no single id."""
    shas = _git(root, "rev-list", "--reverse", f"{base}..{head}").split()
    out = []
    for sha in shas:
        if len(_git(root, "rev-list", "--parents", "-n1", sha).split()) != 2:
            raise ValueError(f"{sha[:10]} is a merge or a root commit: land takes linear history only")
        # review 5 N2: the bytes of the diff (hunk line numbers and full blob ids included), not patch-id, which ignores
        # WHERE a hunk applies: the same lines at another site would carry the reviewed commit's id.
        diff = _gitb(root, "show", "--format=", "--full-index", "--no-ext-diff", "--no-textconv", "--text", sha)
        if not diff.strip():
            raise ValueError(f"{sha[:10]} has an empty diff (an empty commit?): refused")
        msg = _gitb(root, "log", "-n1", "--format=%B", sha)
        out.append({"sha": sha, "diff_hash": hashlib.sha256(diff).hexdigest(), "message_hash": hashlib.sha256(msg).hexdigest()})
    return out


def range_key(keys: list[dict], base: str) -> str:
    """sha256 of the base sha and the ordered (diff hash, message hash) list: what a verdict is keyed on. The base is
    in it (review 5 N3): a revert on the branch or a rebase means a new review, never a replayed verdict."""
    return hashlib.sha256(json.dumps([base, [[k["diff_hash"], k["message_hash"]] for k in keys]]).encode()).hexdigest()


def resolve_branch(root, branch: str) -> str:
    """The sha of refs/heads/<branch>: never a bare name, which git resolves to a TAG of that name first (review 5 N1)."""
    return _git(root, "rev-parse", "--verify", "--end-of-options", f"refs/heads/{branch}^{{commit}}").strip()


def write_verdict(store, root, base: str, head: str, allow_shadow=()) -> str:
    """Record READY for the exact range base..head in `store` (an owner-owned file); returns the range key."""
    base = _git(root, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
    keys = commit_keys(root, base, head)
    key = range_key(keys, base)
    try:
        v = json.loads(safe_read(store))
    except FileNotFoundError:
        v = {}
    v[key] = {"verdict": "READY", "commits": [k["sha"] for k in keys], "allow_shadow": sorted(allow_shadow)}
    safe_write(store, json.dumps(v, indent=1))
    return key


def unreviewed(root, branch: str, head: str, store) -> list[str]:
    """What stops a land: the range branch..head has no READY verdict for its exact commits, or `branch` is not an
    ancestor of head. Empty = clear."""
    try:
        base = resolve_branch(root, branch)
        if subprocess.run([GIT, "-C", str(root), "merge-base", "--is-ancestor", base, head], capture_output=True).returncode:
            return [f"{branch} is not an ancestor of {head[:10]}: land takes a fast-forward of the land branch only"]
        keys = commit_keys(root, base, head)
        verdicts = json.loads(safe_read(store))
    except (ValueError, RuntimeError, OSError) as e:  # PermissionError, a missing store, a bad ref: all refusals
        return [str(e)]
    if not keys:
        return ["nothing to land: branch..head is empty"]
    v = verdicts.get(range_key(keys, base), {})
    if v.get("verdict") != "READY":
        return [f"no READY verdict for this exact range of {len(keys)} commit(s) (diffs and messages, in order)"]
    try:
        unnamed = sorted(set(risky_paths(root, base, head)) - set(v.get("allow_shadow", [])))
    except RuntimeError as e:
        return [str(e)]
    if unnamed:
        return [f"the reviewer did not name these files in READY (review them and re-run harness_review): {', '.join(unnamed)}"]
    return []


def risky_paths(root, base: str, head: str) -> list[str]:
    """Files that make a green ladder cheap to forge: any added or changed conftest.py, and any added top-level module
    (a .py in a directory that is not a package, or a package whose parent is not one) whose name is a stdlib module or
    an installed distribution's module. THE LIMIT, plainly: tests run the worker's own code, so no ladder green is proof
    against a hostile worker; the reviewer is the wall, and a land needs these files NAMED in its READY line
    (`READY: allow-shadow a.py, b.py`). A name inside a package (core/logging.py) shadows nothing and is fine."""
    import sys
    from importlib.metadata import packages_distributions
    taken = set(sys.stdlib_module_names) | set(packages_distributions())
    out = _gitb(root, "diff", "--raw", "-z", "--no-renames", f"{base}..{head}").split(b"\0")
    found = []
    for meta, path in zip(out[0::2], out[1::2]):
        status, p = meta.split()[-1][:1].decode(), path.decode("utf-8", "replace")
        parts = p.split("/")
        if parts[-1] == "conftest.py":
            found.append(p)
            continue
        if status != "A" or not p.endswith(".py"):
            continue
        d = "/".join(parts[:-1])
        name = parts[-1][:-3]
        if name == "__init__":  # a package: its name is the directory's, and it must itself be top-level
            if len(parts) < 2:
                continue
            name, d = parts[-2], "/".join(parts[:-2])
        pkg = f"{d}/__init__.py" if d else "__init__.py"
        if _gitb_ok(root, "cat-file", "-e", f"{head}:{pkg}"):
            continue  # inside a package
        if name in taken:
            found.append(p)
    return found


def _gitb_ok(root, *args) -> bool:
    return subprocess.run([GIT, "-C", str(root), *_ATTR, *args], capture_output=True).returncode == 0


def review_diff(root, base: str, head: str, cap: int = 60000) -> str:
    """What the reviewer reads: EVERY commit of the range, oldest first, as text (no attributes, no textconv), or a
    refusal. Never truncated. Not the net diff: a line added in one commit and removed in the next is still history
    (review 5 N4)."""
    d = _gitb(root, "log", "-p", "--reverse", "--full-index", "--no-ext-diff", "--no-textconv", "--text", f"{base}..{head}")
    if b"\x00" in d:
        raise ValueError("binary content in the diff (a NUL byte): the reviewer cannot read it, refused")
    if len(d) > cap:
        raise ValueError(f"diff is {len(d)} bytes, over the {cap} cap: split the work, the reviewer must see all of it")
    return d.decode("utf-8", "replace")


def boundary(root, base: str, head: str, patterns: list[str], cap: int = 30) -> list[str]:
    """The public/private boundary: every ADDED line of the diff and every commit message matching a pattern from
    harness.toml [land].boundary. Empty = clear; at most `cap` hits are returned (more is itself a refusal reason).
    A hit names commit, file (or message) and the pattern's index, never the matching text: it goes to logs."""
    if not patterns:
        return []
    rx = [re.compile(p) for p in patterns]
    hits: list[str] = []
    cur = f = ""
    in_hunk = False
    diff = _git(root, "log", "--format=%x00%H", "-p", "--no-ext-diff", "--no-textconv", "--text", f"{base}..{head}")
    for ln in diff.split("\n"):
        if ln.startswith("\x00"):
            cur, in_hunk = ln[1:11], False
        elif ln.startswith("diff --git"):  # a content line always has a +/-/space prefix, so this is a real header
            in_hunk = False
        elif ln.startswith("@@"):
            in_hunk = True
        elif not in_hunk and ln.startswith("+++ "):
            f = ln[6:] if ln.startswith("+++ b/") else ln[4:]
        elif in_hunk and ln.startswith("+"):
            hits += [f"{cur} {f}: pattern {i}" for i, r in enumerate(rx) if r.search(ln)]
    for sha in _git(root, "rev-list", f"{base}..{head}").split():
        msg = _git(root, "log", "-n1", "--format=%B", sha)
        hits += [f"{sha[:10]} message: pattern {i}" for ln in msg.splitlines() for i, r in enumerate(rx) if r.search(ln)]
    return hits[:cap] + ([f"... and {len(hits) - cap} more"] if len(hits) > cap else [])


def gate(repo, head: str, pinned, verdicts, log) -> tuple[bool, str]:
    """`builder land` after a green check row for `head`: the rules file, the READY verdict and the boundary, no second ladder
    (the caller has found the row of exactly branch..head, which IS the ladder's result; a second run doubled the pytest load). Every refusal is a row in
    `log`; the result is the push line, which the caller prints and nobody here runs. scripts/harness_land.py keeps the ladder."""
    import time
    import tomllib
    from pathlib import Path

    from fichero_builder import check_tool

    def row(**kw):
        safe_append(log, json.dumps({"at": time.time(), "land": head, **kw}) + "\n")

    if problems := check_tool.rules_problems(pinned):
        row(refused="rules", detail=problems)
        return False, "REFUSED (rules file):\n  " + "\n  ".join(problems)
    land_cfg = tomllib.loads((Path(pinned) / "harness.toml").read_text())["land"]
    branch = land_cfg["branch"]
    try:
        base = resolve_branch(repo, branch)
        head = _git(repo, "rev-parse", "--verify", f"{head}^{{commit}}").strip()
    except RuntimeError as e:
        return False, f"REFUSED: {e}"
    if stop := unreviewed(repo, branch, head, verdicts):
        row(refused="verdict", detail=stop)
        return False, "REFUSED:\n  " + "\n  ".join(stop)
    if hits := boundary(repo, base, head, land_cfg.get("boundary", [])):
        row(refused="boundary", detail=hits)
        return False, "REFUSED (boundary):\n  " + "\n  ".join(hits)
    row(check_row=True)
    return True, f"READY TO LAND: git push origin {head}:refs/heads/{branch}   (the Lead runs this)"
