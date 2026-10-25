"""The one seam to GitHub: reads through `gh` with a short cache, and ONE write function that is dry-run by
default (pipeline.issues-and-milestones-kept-current). Nothing else in the runner calls `gh`."""
from __future__ import annotations

import json
import subprocess
import time

from pipeline import journal

CACHE_TTL = 180  # seconds; refreshed on each transition by cache_clear()
_cache: dict[tuple, tuple[float, object]] = {}


def sh(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kw)


def read(*args: str) -> object:
    key = args
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    r = sh(["gh", *args])
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args)}: {r.stderr.strip()}")
    data = json.loads(r.stdout) if r.stdout.strip().startswith(("{", "[")) else r.stdout
    _cache[key] = (time.time(), data)
    return data


def cache_clear() -> None:
    _cache.clear()


def write(*args: str, dry_run: bool = True) -> str:
    """Every GitHub write in the runner goes through here, journaled; dry_run (the default) writes nothing."""
    journal.append("gh_write", args=list(args), dry_run=dry_run)
    if dry_run:
        return f"DRY RUN: gh {' '.join(args)}"
    r = sh(["gh", *args])
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


ISSUE_FIELDS = "number,title,body,labels,milestone,author,state,url"


def issue(number: int) -> dict:
    d = read("issue", "view", str(number), "--json", ISSUE_FIELDS)
    return _slim(d)


def _slim(d: dict) -> dict:
    d = dict(d)
    d["labels"] = sorted(lab["name"] for lab in d.get("labels") or [])
    d["milestone"] = (d.get("milestone") or {}).get("title")
    d["author"] = (d.get("author") or {}).get("login")
    return d
