#!/usr/bin/env python3
"""Manager/integrator check for finished worker work not merged to main.

This is intentionally not part of scripts/verify_all.sh --fast. Dirty or active
worktree state should not fail a per-commit code-quality gate; managers and
integrators run this on demand before assuming worker output has landed.

Usage:
    scripts/check_unmerged_work.py
    scripts/check_unmerged_work.py --list
    scripts/check_unmerged_work.py --help
"""
from __future__ import annotations

import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_REF = "origin/main"
# Resolved once per run by _comparison_ref(); ~600 lane branches otherwise
# means ~600 merge-base subprocesses.
_COMPARISON_REF: str | None = None
WORKTREE_ROOTS = (
    Path.home() / "code" / "fichero-worktrees",
    ROOT / ".claude" / "worktrees",
)
WORKER_BRANCH_PATTERNS = (
    "fe/*",
    "be/*",
    "tooling/*",
    "codex/*",
    "worktree-agent-*",
)


@dataclass(frozen=True)
class Finding:
    kind: str
    name: str
    path: Path | None
    commits: tuple[str, ...]


def _git(args: list[str], cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _ensure_base_ref() -> str | None:
    result = _git(["rev-parse", "--verify", "--quiet", BASE_REF], check=False)
    if result.returncode == 0:
        return None
    return f"Missing comparison ref {BASE_REF}. Run `git fetch origin main` and retry."


def _comparison_ref() -> str:
    """What counts as "already landed".

    ``origin/main`` alone is too strict for this workflow: day-to-day work
    accumulates on the long-lived integration branch and reaches main only
    at release. Measuring against main therefore reports every
    integration-only commit as unmerged — the check's job is "is this work
    LOST", and work sitting on the integration branch is not lost.

    So when HEAD already contains ``origin/main`` (i.e. HEAD is main or a
    branch built on it), compare against HEAD, which is a superset. Only
    when HEAD has diverged from main do we fall back to main itself.
    """
    global _COMPARISON_REF
    if _COMPARISON_REF is None:
        contains = _git(["merge-base", "--is-ancestor", BASE_REF, "HEAD"], check=False)
        _COMPARISON_REF = "HEAD" if contains.returncode == 0 else BASE_REF
    return _COMPARISON_REF


def _ahead_commits(ref: str, cwd: Path = ROOT) -> tuple[str, ...]:
    """Commits on ``ref`` whose CONTENT is not already in ``BASE_REF``.

    Uses ``git cherry`` (patch-id equivalence), not ``log BASE..ref``
    (SHA ancestry). This repo squash-merges and rebases, so ancestry
    reports work as unmerged when the change is already applied: a spot
    check of three flagged commits found all three present in HEAD
    (e.g. the `import FicheroAPIClient` fix, and PlistBuddy entitlement
    parsing). A guardrail that is permanently and wrongly red trains
    everyone to ignore it, which is worse than not having it.

    ``git cherry`` prefixes each commit with ``+`` (no equivalent
    upstream) or ``-`` (equivalent patch already upstream); only ``+``
    lines are genuinely unmerged.

    Residual limitation, stated rather than hidden: patch-ids match
    1:1 rewrites (cherry-pick, rebase, single-commit squash) but NOT a
    many-commits-into-one squash, where no individual patch-id equals
    the combined diff. Those can still appear as false positives and
    need a content check by hand.
    """
    # `-v` carries the subject inline, so this stays ONE git call per ref;
    # resolving subjects with a `log -1` per commit made the whole sweep
    # time out across the several hundred lane branches.
    result = _git(["cherry", "-v", _comparison_ref(), ref], cwd=cwd, check=False)
    if result.returncode != 0:
        return ()
    unmerged: list[str] = []
    for line in result.stdout.splitlines():
        if not line.startswith("+"):
            continue
        entry = line[1:].strip()
        if not entry:
            continue
        sha, _, subject = entry.partition(" ")
        unmerged.append(f"{sha[:9]} {subject}".strip())
    return tuple(unmerged)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _parse_worktrees() -> list[dict[str, str]]:
    result = _git(["worktree", "list", "--porcelain"])
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        entries.append(current)
    return entries


def _worktree_findings() -> list[Finding]:
    findings: list[Finding] = []
    for entry in _parse_worktrees():
        path_text = entry.get("worktree")
        if not path_text:
            continue
        path = Path(path_text)
        if not any(_is_under(path, root) for root in WORKTREE_ROOTS):
            continue
        commits = _ahead_commits("HEAD", cwd=path)
        if not commits:
            continue
        branch_ref = entry.get("branch", "")
        branch = branch_ref.removeprefix("refs/heads/") if branch_ref else "<detached>"
        findings.append(Finding("worktree", branch, path, commits))
    return findings


def _is_worker_branch(branch: str) -> bool:
    return any(fnmatch.fnmatchcase(branch, pattern) for pattern in WORKER_BRANCH_PATTERNS)


def _local_branch_findings() -> list[Finding]:
    result = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads"])
    findings: list[Finding] = []
    for branch in sorted(line.strip() for line in result.stdout.splitlines() if line.strip()):
        if not _is_worker_branch(branch):
            continue
        commits = _ahead_commits(branch)
        if commits:
            findings.append(Finding("branch", branch, None, commits))
    return findings


def _print_finding(finding: Finding, list_all: bool) -> None:
    location = f" at {finding.path}" if finding.path else ""
    print(f"- {finding.kind}: {finding.name}{location}")
    print(f"  commits not in {_comparison_ref()}: {len(finding.commits)}")
    limit = len(finding.commits) if list_all else min(5, len(finding.commits))
    for commit in finding.commits[:limit]:
        print(f"    {commit}")
    remaining = len(finding.commits) - limit
    if remaining > 0:
        print(f"    ... {remaining} more")


def main(argv: list[str]) -> int:
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    unknown = [arg for arg in argv if arg != "--list"]
    if unknown:
        print(f"Unknown argument: {unknown[0]}", file=sys.stderr)
        print("Usage: scripts/check_unmerged_work.py [--list|--help]", file=sys.stderr)
        return 2

    list_all = "--list" in argv
    missing_base = _ensure_base_ref()
    if missing_base:
        print(f"Unmerged worker work check: ERROR\n  {missing_base}")
        return 2

    worktrees = _worktree_findings()
    branches = _local_branch_findings()
    findings = worktrees + branches

    print("Unmerged worker work check")
    print(f"Base: {_comparison_ref()} (content comparison, squash-aware)")
    print("Worktree roots:")
    for root in WORKTREE_ROOTS:
        print(f"  {root}")
    print(f"Worker branch patterns: {', '.join(WORKER_BRANCH_PATTERNS)}")

    if not findings:
        print("\nPASS: no worker work found ahead of main.")
        return 0

    print(f"\nFAIL: {len(findings)} unmerged worker work item(s) found.\n")
    for finding in findings:
        _print_finding(finding, list_all=list_all)

    print("\nManager/integrator action: merge, close, or intentionally archive these branches/worktrees.")
    return 0 if list_all else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
