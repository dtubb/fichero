"""land gate (dev-workflows Step 0.1 item 6; review 3 B6): every commit of base..head needs a READY verdict
keyed by `git patch-id --verbatim` (indentation is behaviour in Python) plus its message, from a store the worker
user cannot write. A merge commit or a commit without exactly one id is refused. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from fichero_server.workflows.jail import real_git

GIT = real_git()  # never the xcrun shim (minutes of silence on a new user's first call)


def _git(root, *args) -> str:
    r = subprocess.run([GIT, "-C", str(root), *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:200]}")
    return r.stdout


def commit_keys(root, base: str, head: str) -> list[dict]:
    """[{sha, patch_id, message_hash}] oldest first. Raises ValueError on a merge or a commit with no single id."""
    shas = _git(root, "rev-list", "--reverse", f"{base}..{head}").split()
    out = []
    for sha in shas:
        if len(_git(root, "rev-list", "--parents", "-n1", sha).split()) != 2:
            raise ValueError(f"{sha[:10]} is a merge or a root commit: land takes linear history only")
        diff = subprocess.run([GIT, "-C", str(root), "show", "--format=", "--no-ext-diff", "--no-textconv", sha],
                              capture_output=True, text=True).stdout
        ids = subprocess.run([GIT, "patch-id", "--verbatim"], input=diff, capture_output=True, text=True).stdout.split("\n")
        ids = [x.split()[0] for x in ids if x.strip()]
        if len(ids) != 1:
            raise ValueError(f"{sha[:10]} has {len(ids)} patch ids (an empty commit?): refused")
        msg = _git(root, "log", "-n1", "--format=%B", sha)
        out.append({"sha": sha, "patch_id": ids[0], "message_hash": hashlib.sha256(msg.encode()).hexdigest()})
    return out


def unreviewed(root, base: str, head: str, store) -> list[str]:
    """What stops a land: commits with no READY verdict for their exact patch-id and message. Empty = clear."""
    f = Path(store)
    verdicts = json.loads(f.read_text()) if f.is_file() else {}
    try:
        keys = commit_keys(root, base, head)
    except ValueError as e:
        return [str(e)]
    if not keys:
        return ["nothing to land: base..head is empty"]
    return [f"{k['sha'][:10]}: no READY verdict for this exact diff and message" for k in keys
            if verdicts.get(k["patch_id"], {}).get("verdict") != "READY"
            or verdicts[k["patch_id"]].get("message_hash") != k["message_hash"]]


def boundary(root, base: str, head: str, patterns: list[str], cap: int = 30) -> list[str]:
    """The public/private boundary: every ADDED line of the diff and every commit message matching a pattern from
    harness.toml [land].boundary. Empty = clear; at most `cap` hits are returned (more is itself a refusal reason)."""
    if not patterns:
        return []
    rx = [re.compile(p) for p in patterns]
    hits: list[str] = []
    cur = ""
    diff = _git(root, "log", "--format=%x00%H", "-p", "--no-ext-diff", "--no-textconv", f"{base}..{head}")
    for ln in diff.splitlines():
        if ln.startswith("\x00"):
            cur = ln[1:11]
        elif ln.startswith("+++ "):
            f = ln[6:] if ln.startswith("+++ b/") else ln[4:]
        elif ln.startswith("+") and any(r.search(ln) for r in rx):
            hits.append(f"{cur} {f}: {ln[:120]}")
    for sha in _git(root, "rev-list", f"{base}..{head}").split():
        msg = _git(root, "log", "-n1", "--format=%B", sha)
        hits += [f"{sha[:10]} message: {ln[:120]}" for ln in msg.splitlines() if any(r.search(ln) for r in rx)]
    return hits[:cap] + ([f"... and {len(hits) - cap} more"] if len(hits) > cap else [])
