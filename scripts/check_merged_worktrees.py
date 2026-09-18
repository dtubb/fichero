#!/usr/bin/env python3
"""Pins `git.cleanup-merged-worktrees` (spec: git-worktree-workflow): a merged lane's
worktree is removed, not left to rot.

READ-ONLY: this script never runs `git worktree remove`/`prune` or any other mutating
command. It only calls `git worktree list --porcelain`, `git rev-parse --show-toplevel`, and
`git merge-base --is-ancestor` (a read-only query). It PRINTS the remove command for a human
to run — it never runs it.

A worktree is "lingering" when its branch (or, for a detached HEAD, its commit) is already
an ancestor of `main` — the work landed, so the checkout serves no purpose and is rot. Two
worktrees are NEVER flagged regardless of merge state: the main checkout (the primary
worktree git always lists first) and the CURRENT worktree (wherever this script runs from —
you can't be lingering in the worktree you're actively using).

`scripts/merged_worktrees_allowlist.json` exempts a deliberately-kept worktree (path +
reason) — same shrink-only contract as every other allowlist in this repo: an entry whose
path no longer appears in `git worktree list` is itself a finding (stale, must be removed
from the allowlist, not silently trusted).

Run:
    python scripts/check_merged_worktrees.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ALLOWLIST_PATH = pathlib.Path("scripts/merged_worktrees_allowlist.json")


def _git_worktree_list_porcelain() -> str:
    proc = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        print(f"FAIL check_merged_worktrees: `git worktree list` exited {proc.returncode}: "
              f"{proc.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return proc.stdout


def _current_worktree_path() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        print(f"FAIL check_merged_worktrees: `git rev-parse --show-toplevel` exited "
              f"{proc.returncode}: {proc.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return proc.stdout.strip()


def _is_ancestor_of_main(ref: str) -> bool:
    """True iff `ref` (a branch name or a commit sha) has already landed on `main` — a
    read-only query, never a mutation."""
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ref, "main"],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode == 0


def parse_porcelain(text: str) -> list[dict]:
    """`git worktree list --porcelain` -> [{path, head, branch (None if detached), bare}].
    Entries are blank-line separated; each has `worktree <path>`, `HEAD <sha>`, and either
    `branch refs/heads/<name>` or the literal `detached`."""
    entries: list[dict] = []
    current: dict = {}
    for line in text.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current = {"path": line[len("worktree "):].strip(), "head": None,
                       "branch": None, "bare": False}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            ref = line[len("branch "):].strip()
            current["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        elif line == "detached":
            current["branch"] = None
        elif line == "bare":
            current["bare"] = True
    if current:
        entries.append(current)
    return entries


def _load_allowlist() -> list[dict]:
    if not ALLOWLIST_PATH.exists():
        return []
    try:
        return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL check_merged_worktrees: {ALLOWLIST_PATH} is malformed JSON: {exc}",
              file=sys.stderr)
        sys.exit(2)


def find_lingering(entries: list[dict], current_path: str) -> list[dict]:
    """Which non-main, non-current worktrees are already merged into `main`. `entries[0]`
    is always the main checkout (the primary worktree git lists first)."""
    lingering = []
    for entry in entries[1:]:
        if entry.get("bare"):
            continue
        if entry["path"] == current_path:
            continue
        ref = entry["branch"] or entry["head"]
        if ref and _is_ancestor_of_main(ref):
            lingering.append(entry)
    return lingering


def check() -> int:
    entries = parse_porcelain(_git_worktree_list_porcelain())
    if not entries:
        print("FAIL check_merged_worktrees: `git worktree list` returned nothing — "
              "blind, not green.", file=sys.stderr)
        return 2
    current_path = _current_worktree_path()
    lingering = find_lingering(entries, current_path)

    allowlist = _load_allowlist()
    allowlisted_paths = {e.get("path") for e in allowlist}
    live_paths = {e["path"] for e in entries}

    failures = []
    for entry in allowlist:
        path = entry.get("path")
        reason = (entry.get("reason") or "").strip()
        if path not in live_paths:
            failures.append(f"{ALLOWLIST_PATH}: allowlisted worktree '{path}' no longer "
                             f"exists — remove it from the allowlist.")
        elif not reason:
            failures.append(f"{ALLOWLIST_PATH}: allowlisted worktree '{path}' has no `reason`.")

    unallowlisted_lingering = [e for e in lingering if e["path"] not in allowlisted_paths]

    if unallowlisted_lingering:
        for entry in unallowlisted_lingering:
            ref = entry["branch"] or entry["head"]
            failures.append(
                f"{entry['path']} — branch/commit '{ref}' is already merged into main, "
                f"lingering. Remove with: git worktree remove {entry['path']}"
            )

    if failures:
        print("FAIL check_merged_worktrees:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(
        f"OK check_merged_worktrees: {len(entries) - 1} non-main worktree(s) checked, "
        f"{len(lingering)} merged-and-allowlisted, 0 lingering."
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/check_merged_worktrees.py", file=sys.stderr)
        return 2
    return check()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
