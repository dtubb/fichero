"""land gate (dev-workflows Step 0.1 item 6; review 3 B6): every commit of base..head needs a READY verdict
keyed by `git patch-id --verbatim` (indentation is behaviour in Python) plus its message, from a store the worker
user cannot write. A merge commit or a commit without exactly one id is refused. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


def _git(root, *args) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
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
        diff = subprocess.run(["git", "-C", str(root), "show", "--format=", "--no-ext-diff", "--no-textconv", sha],
                              capture_output=True, text=True).stdout
        ids = subprocess.run(["git", "patch-id", "--verbatim"], input=diff, capture_output=True, text=True).stdout.split("\n")
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
