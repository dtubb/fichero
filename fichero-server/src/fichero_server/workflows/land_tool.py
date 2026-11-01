"""land gate (dev-workflows Step 0.1 item 6; review 3 B6, review 4 B1/B3/B4/H5/H6): a READY verdict is keyed on the
ORDERED list of (`git patch-id --verbatim`, message hash) of the whole range, so a subset or a replay is not the
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

from fichero_server.workflows.jail import real_git

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
    """[{sha, patch_id, message_hash}] oldest first. Raises ValueError on a merge or a commit with no single id."""
    shas = _git(root, "rev-list", "--reverse", f"{base}..{head}").split()
    out = []
    for sha in shas:
        if len(_git(root, "rev-list", "--parents", "-n1", sha).split()) != 2:
            raise ValueError(f"{sha[:10]} is a merge or a root commit: land takes linear history only")
        diff = _gitb(root, "show", "--format=", "--no-ext-diff", "--no-textconv", "--text", sha)
        ids = subprocess.run([GIT, "patch-id", "--verbatim"], input=diff, capture_output=True).stdout.decode().split("\n")
        ids = [x.split()[0] for x in ids if x.strip()]
        if len(ids) != 1:
            raise ValueError(f"{sha[:10]} has {len(ids)} patch ids (an empty commit?): refused")
        msg = _gitb(root, "log", "-n1", "--format=%B", sha)
        out.append({"sha": sha, "patch_id": ids[0], "message_hash": hashlib.sha256(msg).hexdigest()})
    return out


def range_key(keys: list[dict]) -> str:
    """sha256 of the ordered (patch-id, message hash) list: what a verdict is keyed on."""
    return hashlib.sha256(json.dumps([[k["patch_id"], k["message_hash"]] for k in keys]).encode()).hexdigest()


def write_verdict(store, root, base: str, head: str) -> str:
    """Record READY for the exact range base..head in `store` (an owner-owned file); returns the range key."""
    keys = commit_keys(root, base, head)
    key = range_key(keys)
    try:
        v = json.loads(safe_read(store))
    except FileNotFoundError:
        v = {}
    v[key] = {"verdict": "READY", "commits": [k["sha"] for k in keys]}
    safe_write(store, json.dumps(v, indent=1))
    return key


def unreviewed(root, branch: str, head: str, store) -> list[str]:
    """What stops a land: the range branch..head has no READY verdict for its exact commits, or `branch` is not an
    ancestor of head. Empty = clear."""
    try:
        base = _git(root, "rev-parse", "--verify", f"{branch}^{{commit}}").strip()
        if subprocess.run([GIT, "-C", str(root), "merge-base", "--is-ancestor", base, head], capture_output=True).returncode:
            return [f"{branch} is not an ancestor of {head[:10]}: land takes a fast-forward of the land branch only"]
        keys = commit_keys(root, base, head)
        verdicts = json.loads(safe_read(store))
    except (ValueError, RuntimeError, OSError) as e:  # PermissionError, a missing store, a bad ref: all refusals
        return [str(e)]
    if not keys:
        return ["nothing to land: branch..head is empty"]
    if verdicts.get(range_key(keys), {}).get("verdict") != "READY":
        return [f"no READY verdict for this exact range of {len(keys)} commit(s) (diffs and messages, in order)"]
    return []


def review_diff(root, base: str, head: str, cap: int = 60000) -> str:
    """The diff the reviewer reads: all of it as text (no attributes, no textconv), or a refusal. Never truncated."""
    d = _gitb(root, "diff", "--no-ext-diff", "--no-textconv", "--text", f"{base}..{head}")
    if b"\x00" in d:
        raise ValueError("binary content in the diff (a NUL byte): the reviewer cannot read it, refused")
    if len(d) > cap:
        raise ValueError(f"diff is {len(d)} bytes, over the {cap} cap: split the work, the reviewer must see all of it")
    return d.decode("utf-8", "replace")


def boundary(root, base: str, head: str, patterns: list[str], cap: int = 30) -> list[str]:
    """The public/private boundary: every ADDED line of the diff and every commit message matching a pattern from
    harness.toml [land].boundary. Empty = clear; at most `cap` hits are returned (more is itself a refusal reason)."""
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
        elif in_hunk and ln.startswith("+") and any(r.search(ln) for r in rx):
            hits.append(f"{cur} {f}: {ln[:120]}")
    for sha in _git(root, "rev-list", f"{base}..{head}").split():
        msg = _git(root, "log", "-n1", "--format=%B", sha)
        hits += [f"{sha[:10]} message: {ln[:120]}" for ln in msg.splitlines() if any(r.search(ln) for r in rx)]
    return hits[:cap] + ([f"... and {len(hits) - cap} more"] if len(hits) > cap else [])
