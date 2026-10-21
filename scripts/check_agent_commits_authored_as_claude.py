#!/usr/bin/env python3
"""A commit that carries an agent trailer must be authored as `Claude <noreply@anthropic.com>` (#5997, `git.agent-commits-authored-as-claude`).

AGENTS.md: the maintainer is credited by a `Directed-By:` trailer, not by owning the authorship. 37 commits from 2026-10-19 reached
integration authored as Daniel Tubb with an agent trailer. This fails a push RANGE where a commit has `Directed-By:` or
`Co-Authored-By: Claude ...` and an author that is not Claude, naming each sha and its author. It judges only the range it is given,
so history already on integration (left there by ruling) never fails it.

Run: python scripts/check_agent_commits_authored_as_claude.py [BASE..TIP]    (default origin/integration..HEAD)
Exit 0: every agent-trailer commit in the range is authored as Claude (or the range is empty). Exit 1: names the offenders.
Exit 2: git could not read the range (a missing ref, not a git repository): a range that cannot be read proves nothing.
Stdlib and git only."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RANGE = "origin/integration..HEAD"
CLAUDE = "Claude <noreply@anthropic.com>"
# `Directed-By:` at the start of a line, or a `Co-Authored-By:` naming Claude (not a human co-author)
AGENT_TRAILER = re.compile(r"^(?:Directed-By:|Co-Authored-By:\s*Claude\b)", re.IGNORECASE | re.MULTILINE)
_SEP, _END = "\x1f", "\x1e"


def commits(rng: str, cwd: Path = ROOT) -> list[tuple[str, str, str]]:
    """(sha, 'Name <email>', message) for every commit in the range; raises RuntimeError when git cannot read it."""
    done = subprocess.run(["git", "log", f"--format=%H{_SEP}%an <%ae>{_SEP}%B{_END}", rng],
                          cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git log {rng} failed: {done.stderr.strip() or done.stdout.strip()}")
    out = []
    for record in done.stdout.split(_END):
        if record.strip():
            sha, author, message = record.strip("\n").split(_SEP, 2)
            out.append((sha, author, message))
    return out


def offenders(rng: str, cwd: Path = ROOT) -> list[tuple[str, str, str]]:
    """The commits with an agent trailer whose author is not Claude: (sha, author, subject)."""
    return [(sha, author, message.strip().splitlines()[0][:100] if message.strip() else "")
            for sha, author, message in commits(rng, cwd)
            if AGENT_TRAILER.search(message) and author != CLAUDE]


def main(argv: list[str]) -> int:
    rng = argv[1] if len(argv) > 1 else DEFAULT_RANGE
    try:
        bad = offenders(rng)
    except RuntimeError as exc:
        print(f"FAIL check_agent_commits_authored_as_claude: {exc}")
        return 2
    if bad:
        print(f"FAIL: {len(bad)} commit(s) in {rng} carry an agent trailer but are not authored as {CLAUDE}:")
        for sha, author, subject in bad:
            print(f"  {sha[:12]}  {author}  {subject}")
        print("Re-author them (git rebase -r --exec 'git commit --amend --no-edit --reset-author' with user.name=Claude, "
              "user.email=noreply@anthropic.com) before the push; the maintainer stays credited by the Directed-By trailer.")
        return 1
    print(f"OK check_agent_commits_authored_as_claude: every agent-trailer commit in {rng} is authored as Claude")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
