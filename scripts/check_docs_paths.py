#!/usr/bin/env python3
"""Docs path guardrail: every repo path a doc names must exist.

Rule: docs describe what is BUILT. A doc that names `fichero/fichero/Views/Agents/`
when that directory has zero files is not stale — it is wrong, and an agent will act
on it. See AGENTS.md ("Docs Placement").

In one day this caught: Views/{Agents,Integrations,Batch}/ (all nonexistent),
docs/qa_matrix.md, .mcp.json, fichero-api/, fichero-swiftui/, PLAN-GOVERNANCE.md,
and docs/architecture/typed_entity_storage.md.

Scope: backtick-quoted tokens in docs/**.md and the root doc files, whose FIRST path
segment is a real top-level entry in the repo. That anchor is what keeps the check
honest — it skips `api/routes/` (engine-relative), `~/Library/...`, URLs, and glob
patterns, none of which are repo paths.

Known-absent paths that are named on purpose (build artifacts, deleted things being
described as deleted) go in check_docs_paths_allowlist.json.

ponytail: one regex + Path.exists(). No markdown parser; a link checker already
covers `[]()` links. This covers the prose backticks nothing else reads.

Usage:
    scripts/check_docs_paths.py
    scripts/check_docs_paths.py --list
    scripts/check_docs_paths.py --write-allowlist   # ratchet after a review
    scripts/check_docs_paths.py --self-test
    scripts/check_docs_paths.py --help
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

from _check_floor import require_scan_floor
from pathlib import Path
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = Path(__file__).resolve().parent / "check_docs_paths_allowlist.json"
RULE_DOC = "AGENTS.md"

ROOT_DOCS = ["README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "USER.md"]

# A backtick token that looks like a repo path: has a slash, no spaces, no glob,
# no scheme, no shell metacharacters.
_TOKEN = re.compile(r"`([A-Za-z0-9_.-][A-Za-z0-9_./-]*/[A-Za-z0-9_./-]*)`")
# Rejected outright: globs, shell/env syntax, angle-bracket PLACEHOLDERS like
# `docs/<page>.md`, `~/Library/...`, URLs, relative `../`, and `::` selectors.
_REJECT = re.compile(r"[*?{}$<>|]|^~|^https?:|^\.\./|::")
# Fenced code blocks are examples (commands, snippets), not references to check.
_FENCE = re.compile(r"^```.*?^```", re.S | re.M)


def strip_fences(text: str) -> str:
    return _FENCE.sub("", text)


def top_level() -> set[str]:
    """The top-level names a repo path may start with — the SAME on every checkout.

    It used to be `ROOT.iterdir()`, so `build/` was a top only where something had been
    built: a doc citing `build/releases` was checked in the main checkout and silently
    skipped in every fresh worktree, which then reported the allowlist entry as stale.
    Tracked top-level names plus the plain top-level names `.gitignore` declares (`build/`,
    `agent-work/`) are a fact about the repository, not about this disk.
    """
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=False,
    )
    if listed.returncode != 0:
        return {p.name for p in ROOT.iterdir()}  # git unavailable: best effort
    tops = {line.split("/", 1)[0] for line in listed.stdout.splitlines() if line}
    gitignore = ROOT / ".gitignore"
    if gitignore.is_file():
        tops |= ignored_top_level_names(gitignore.read_text(errors="ignore"))
    return tops


def ignored_top_level_names(gitignore_text: str) -> set[str]:
    """Plain names from a root `.gitignore` — `build/` yes, `*.pyc` or `a/b/` no."""
    out = set()
    for raw in gitignore_text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        name = line.strip("/")
        if name and "/" not in name and not any(c in name for c in "*?["):
            out.add(name)
    return out


#: `docs/user_manual/` is written BY HAND by the maintainer and is deliberately not
#: guarded (ruled 2026-09-27). The AI-written manuals — `reference_manual` and
#: `contributor_manual` — are exactly what these checks are for: a machine writing about
#: code it can read should be held to what the code does. A human writing a user manual
#: is describing what the software is FOR, at a pace and in an order that is theirs, and a
#: guard that fails on a half-written chapter is telling the author to stop writing.
#:
#: It was also the only remaining reason two docs guards were red, so guarding it was
#: costing two real signals to enforce a rule nobody wanted.
HAND_WRITTEN_MANUAL = "user_manual"


def is_hand_written(path: Path, docs_root: Path) -> bool:
    """Whether this page belongs to the manual the maintainer writes by hand."""
    try:
        return path.relative_to(docs_root).parts[0] == HAND_WRITTEN_MANUAL
    except (ValueError, IndexError):
        return False


def doc_files() -> list[Path]:
    docs = ROOT / "docs"
    files = [p for p in sorted(scan_rglob(docs, "*.md")) if not is_hand_written(p, docs)]
    files += [ROOT / f for f in ROOT_DOCS if (ROOT / f).exists()]
    return files


def candidates(text: str, tops: set[str]) -> set[str]:
    out = set()
    for m in _TOKEN.finditer(text):
        tok = m.group(1)
        if _REJECT.search(tok):
            continue
        first = tok.split("/", 1)[0]
        if first in tops:
            out.add(tok.rstrip("/"))
    return out


def load_allowlist() -> tuple[set[str], dict[str, str]]:
    """The reason-less legacy list, and the reasoned map.

    Two shapes on purpose (#5098): `known_absent_paths` is a flat list nobody can audit
    — it says a path is excused and not why — and it is kept working so nothing breaks
    while entries move across. `absent_on_purpose` maps path (or a PREFIX ending in `/`)
    to the reason, and the reason is the whole value: the alternative is #5095's shape,
    where 551 of 569 paths shared one pasted sentence.
    """
    if not ALLOWLIST.exists():
        return set(), {}
    data = json.loads(ALLOWLIST.read_text())
    reasoned = data.get("absent_on_purpose", {})
    assert isinstance(reasoned, dict), "absent_on_purpose must map path -> reason"
    return set(data.get("known_absent_paths", [])), reasoned


def excused(path: str, legacy: set[str], reasoned: dict[str, str]) -> bool:
    """Whether this absent path is accounted for, by exact entry or by prefix.

    A prefix entry (one ending in `/`) covers a whole gitignored tree, so a doc citing
    a ninth working note does not need a ninth identical entry. Only the reasoned map
    may use prefixes: a blanket excuse is exactly the thing that has to say why.
    """
    if path in legacy or path in reasoned:
        return True
    return any(
        prefix.endswith("/") and (path + "/").startswith(prefix)
        for prefix in reasoned
    )


def is_untracked(path: str) -> bool:
    """On disk here, and in NOBODY ELSE'S checkout.

    `Path.exists()` answers "is it on this machine", and a doc is read by people who cloned
    the repository. A path that exists untracked passes on the one laptop that has it and
    fails everywhere else — which is worse than failing here, because the guard reports
    green while a fresh clone's documentation points at nothing.

    Found 2026-09-27: `docs/user_manual` is named by `AGENTS.md` and five specs, holds real
    documents on this machine, and has ZERO tracked files (#5101). The guard passed on it.
    Gitignored paths are handled separately by the allowlist, which is the right place for a
    deliberate absence — this is for a path somebody simply has not committed.
    """
    result = subprocess.run(
        ["git", "ls-files", "--", path],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return False  # git unavailable: fall back to existence rather than invent a failure
    return not result.stdout.strip()


def missing() -> dict[str, list[str]]:
    """path -> the docs that name it, for paths a READER OF THE REPOSITORY does not have.

    Not simply "does not exist": a path present but untracked is absent for everyone except
    this checkout, and treating it as present is how a guard reads green while the thing it
    guards is broken for every clone.
    """
    tops = top_level()
    named: dict[str, list[str]] = {}
    for f in doc_files():
        for tok in candidates(strip_fences(f.read_text(errors="ignore")), tops):
            # A path INSIDE the hand-written manual is not ours to check either: the
            # maintainer adds and renames those chapters as the writing goes.
            if tok.split("/")[:2] == ["docs", HAND_WRITTEN_MANUAL] or tok == f"docs/{HAND_WRITTEN_MANUAL}":
                continue
            named.setdefault(tok, []).append(str(f.relative_to(ROOT)))
    ignored = git_ignored(named)
    out: dict[str, list[str]] = {}
    for tok, where in named.items():
        # A GITIGNORED path is reported whether or not it exists here. Whether a build
        # output is on disk is a fact about this machine, not the repository: until
        # 2026-09-27 `fichero/fichero-api-client/.build` (named by AGENTS.md) passed in the
        # main checkout, where Xcode had built it, and failed in every fresh worktree. A
        # guard whose verdict depends on what was last built is not measuring the docs.
        # The allowlist's reasoned map is where a deliberate gitignored citation says why.
        if tok in ignored or not (ROOT / tok).exists() or is_untracked(tok):
            out[tok] = where
    return out


def git_ignored(paths) -> set[str]:
    """The subset of `paths` git ignores — one subprocess, not one per path.

    `check-ignore` matches patterns, so it answers for a path that does not exist, which
    is what makes the verdict the same on every checkout. Each path is asked twice, with
    and without a trailing `/`: a directory pattern like `.build/` only matches the
    slashed form when the directory is not on disk to tell git it is one.
    """
    paths = list(paths)
    if not paths:
        return set()
    query = [q for p in paths for q in (p, p + "/")]
    result = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "--stdin"],
        input="\n".join(query) + "\n", capture_output=True, text=True, check=False,
    )
    if result.returncode not in (0, 1):
        return set()  # git unavailable: fall back to existence rather than invent failures
    return {line.strip().rstrip("/") for line in result.stdout.splitlines() if line.strip()}


def is_git_ignored(path: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "-q", path],
        check=False,
    ).returncode == 0


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    # #4382: a guardrail must know when it has gone blind. No docs/ tree and
    # none of the root docs means the tree moved -- exit 2, never a silent 0.
    if not (ROOT / "docs").is_dir() and not any(
        (ROOT / name).exists() for name in ROOT_DOCS
    ):
        print(
            "check_docs_paths.py: BLIND -- neither docs/ nor any root doc "
            "exists under " + str(ROOT) + " (the tree moved; update this guardrail)",
            file=sys.stderr,
        )
        return 2

    if "--self-test" in argv:
        tops = {"docs", "scripts", "fichero"}
        t = "see `docs/real.md` and `scripts/x.py` and `api/routes/` and `~/Library/x`"
        assert candidates(t, tops) == {"docs/real.md", "scripts/x.py"}, candidates(t, tops)
        assert candidates("`scripts/check_*.py`", tops) == set()  # glob rejected
        assert candidates("`https://a/b`", tops) == set()  # url rejected
        assert candidates("`../docs/x.md`", tops) == set()  # relative rejected
        assert candidates("`docs/<page>.md`", tops) == set()  # placeholder rejected
        assert candidates("`~/Library/App/x`", tops) == set()  # home path rejected
        assert candidates("`api/routes/`", tops) == set()  # namespace, not a repo path
        assert candidates("`docs/**/*.md`", tops) == set()  # glob rejected
        assert strip_fences("a\n```\n`docs/nope.md`\n```\nb") .strip() == "a\n\nb".strip()
        # Prefix excuses cover a tree; an unreasoned path still needs its own entry.
        assert excused("agent-work/x/y.md", set(), {"agent-work/": "why"})
        assert not excused("agents/x.md", set(), {"agent-work/": "why"})
        assert excused("build/x", {"build/x"}, {})
        assert not excused("build/x", set(), {})
        # A prefix in the legacy list must NOT excuse a tree: a blanket excuse with no
        # reason is the shape this guard exists to refuse.
        assert not excused("agent-work/x/y.md", {"agent-work/"}, {})
        print("check_docs_paths self-test passed")
        return 0

    absent = missing()
    legacy, reasoned = load_allowlist()
    allowed = {p for p in absent if excused(p, legacy, reasoned)}

    if "--write-allowlist" in argv:
        ALLOWLIST.write_text(
            json.dumps(
                {
                    "_doc": (
                        "Repo paths named in docs that do not exist, on purpose "
                        "(build artifacts, or things described as deleted). Every "
                        f"other absent path is a bug. See {RULE_DOC}."
                    ),
                    # The reasoned map is PRESERVED: a ratchet that dropped the reasons
                    # would turn every decision back into a placeholder.
                    "absent_on_purpose": reasoned,
                    "known_absent_paths": sorted(
                        p for p in absent if not excused(p, set(), reasoned)
                    ),
                },
                indent=2,
            )
            + "\n"
        )
        print(f"wrote {ALLOWLIST.relative_to(ROOT)} ({len(absent)} entries)")
        return 0

    new = {p: v for p, v in absent.items() if p not in allowed}
    # A stale entry is one nothing names any more. Prefix entries are skipped: a tree
    # that is gitignored by design is not "back" just because no doc cites it this week.
    # Exact gitignored entries are NOT exempt any more: `missing()` now reports a named
    # gitignored path on every checkout, so one absent from `absent` is one no doc names.
    stale = sorted(
        (legacy | {k for k in reasoned if not k.endswith("/")}) - set(absent)
    )

    if "--list" in argv:
        print(f"absent paths named in docs ({len(absent)}):\n")
        for p, where in sorted(absent.items()):
            tag = "[NEW]" if p in new else "[known]"
            print(f"  {tag} {p}\n      named in: {', '.join(where)}")
        return 0

    print("docs path guardrail")
    # #4487 scan floor: 122 docs on 2026-08-02.
    require_scan_floor(len(doc_files()), 61, "docs pages (122 on 2026-08-02)")
    print(f"  docs scanned: {len(doc_files())}")
    print(f"  absent paths named: {len(absent)} "
          f"({len(allowed & set(absent))} allowlisted, {len(new)} unaccounted)")

    if new or stale:
        print(f"\nFAIL docs name paths that do not exist. Rule: {RULE_DOC}")
        for p, where in sorted(new.items()):
            print(f"  MISSING {p}")
            print(f"    named in: {', '.join(where)}")
            print("    -> fix the path, delete the claim, or allowlist it.")
        for p in stale:
            print(f"  stale allowlist entry (path exists again): {p}")
        return 1

    print("\nPASS every repo path named in docs exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
