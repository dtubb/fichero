#!/usr/bin/env python3
"""Spec citations resolve and spec status is current, for every spec bullet a batch TOUCHES; the rest is a debt count that only falls.

Why (review rounds 2026-11-02..04, presubmit lints 3 and 4): a cited test that did not exist, a wrong test path, a bullet still saying
"not yet written" beside a test that exists, and an [OK] with no test cost a whole ladder each. The specs held about 1,500 old misses
when this landed, so the whole tree cannot be judged; the bullets a batch changes can.

1. Touched bullets (a bullet with a line the batch adds, against `git merge-base HEAD origin/integration`; `FICHERO_SPEC_BASE`
   overrides): every `path.py` / `path.swift` cited resolves to a file (at the root or under a package dir), and every `::name`
   after it to a name in that file. A line tagged [GAP] or saying "not yet written" / "(to write)" whose cited test exists (the
   `::name`, else the file) is stale. An [OK] bullet that cites no existing test file is refused. ("Not built:" notes are fine.)
2. The whole tree: the counts of missing files and missing names are compared with `docs/contributor_manual/specs/_citation_debt.json`.
   More than the file says FAILS (a citation broke outside the batch's bullets, e.g. a test renamed); a file raised above its copy at
   the base FAILS; fewer only prints the number to lower the file to.

Run: python scripts/check_spec_citations.py [ROOT]
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

from _scan_files import scan_rglob

SPECS = "docs/contributor_manual/specs"
DEBT = f"{SPECS}/_citation_debt.json"
PACKAGES = ("", "fichero-server/", "fichero-builder/", "fichero-cli/", "fichero-mcp/", "pipeline/", "fichero/")
PATH = re.compile(r"(?<![\w/.<*-])((?:[\w.-]+/)+[\w.-]+\.(?:py|swift))((?:::\w+)*)(?![\w*])")
NAME = re.compile(r"(?<![\w.:/])::(\w+)")
BULLET = re.compile(r"^- `[a-z0-9][\w.-]+`")
STALE = re.compile(r"\[GAP\]|not yet written|\(to write\)")
NOT_YET = re.compile(r"\bNot (?:yet|built)\b:?\**.*?(?:\.(?=\s|$)|$)")  # to its full stop: a dot then a space or the end (ids hold dots, review 108)
OWN_VERB = re.compile(r"^- `[a-z0-9][\w.-]+`[^—]*—\s*`builder ([a-z][\w-]*)")  # the verb a bullet's opening clause is about
ID = re.compile(r"^- `([a-z0-9][\w.-]+)`")
OK_TAG = re.compile(r"^- `[a-z0-9][\w.-]+`\s+(?:—\s+)?\**\[OK\]")  # the status tag right after the id
QUOTED = re.compile(r"`[^`]*`|\"[^\"]*\"")  # quoted or backticked text names a status, it does not claim one


class Tree:
    def __init__(self, root: pathlib.Path):
        self.root, self._text = root, {}
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "*.py", "*.swift"], capture_output=True, text=True).stdout.split()
        self._tracked = sorted(set(listed))
        self._by_name: dict[str, list[str]] = {}
        for t in self._tracked:
            self._by_name.setdefault(t.rsplit("/", 1)[-1], []).append(t)

    def file(self, rel: str) -> pathlib.Path | None:
        """The file a citation names: at the root or under a package dir, else the tracked file whose path ends with it (specs cite
        package-relative paths such as `api/routes/x.py` and mid-tree Swift paths)."""
        for pkg in PACKAGES:
            p = self.root / (pkg + rel)
            if p.is_file():
                return p
        hits = [t for t in self._by_name.get(rel.rsplit("/", 1)[-1], []) if t.endswith("/" + rel)]
        return self.root / hits[0] if hits and (self.root / hits[0]).is_file() else None

    def has_name(self, path: pathlib.Path, name: str) -> bool:
        if path not in self._text:
            self._text[path] = path.read_text(encoding="utf-8", errors="replace")
        return re.search(rf"\b{re.escape(name)}\b", self._text[path]) is not None


def citations(line: str) -> list[tuple[str, list[str]]]:
    """[(path, [names])] in order; a bare `::name` belongs to the path before it on the line."""
    out: list[tuple[str, list[str]]] = []
    spans = []
    for m in PATH.finditer(line):
        out.append((m.group(1), [n for n in m.group(2).split("::") if n]))
        spans.append(m.span())
    for m in NAME.finditer(line):
        if any(a <= m.start() < b for a, b in spans):
            continue
        owner = [i for i, (a, _) in enumerate(spans) if a < m.start()]
        if owner:
            out[owner[-1]][1].append(m.group(1))
    return out


def misses(tree: Tree, line: str) -> list[str]:
    bad = []
    for path, names in citations(line):
        f = tree.file(path)
        if f is None:
            bad.append(f"`{path}` does not exist")
        else:
            bad += [f"`{path}::{n}` names nothing in that file" for n in names if not tree.has_name(f, n)]
    return bad


def is_test(path: str) -> bool:
    return "test" in path.lower()


def stale(tree: Tree, line: str) -> str | None:
    if not (m := STALE.search(QUOTED.sub("", line))):
        return None
    for path, names in citations(line):
        f = tree.file(path)
        if f and is_test(path) and (all(tree.has_name(f, n) for n in names) if names else True):
            return f"says {m.group()!r} but its test `{path}{''.join('::' + n for n in names)}` exists: update the status"
    return None


def bullets(lines: list[str]) -> list[tuple[int, int]]:
    """(start, end) line indexes of each bullet: the `- \\`id\\`` line and its indented continuation."""
    out, i = [], 0
    while i < len(lines):
        if BULLET.match(lines[i]):
            j = i + 1
            while j < len(lines) and lines[j].startswith("  ") and not BULLET.match(lines[j]):
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def added_lines(root: pathlib.Path) -> dict[str, set[int]]:
    """{spec path: 1-based line numbers the batch adds}; nothing when there is no base (the land branch itself)."""
    base = os.environ.get("FICHERO_SPEC_BASE") or subprocess.run(
        ["git", "-C", str(root), "merge-base", "HEAD", "origin/integration"], capture_output=True, text=True).stdout.strip()
    if not base:
        return {}
    diff = subprocess.run(["git", "-C", str(root), "diff", "--no-ext-diff", "-U0", base, "HEAD", "--", f"{SPECS}/*.md"],
                          capture_output=True, text=True).stdout
    out: dict[str, set[int]] = {}
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
        elif line.startswith("@@") and cur:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m is None:
                continue
            start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            out.setdefault(cur, set()).update(range(start, start + n))
    return out


def base_debt(root: pathlib.Path) -> dict | None:
    base = os.environ.get("FICHERO_SPEC_BASE") or subprocess.run(
        ["git", "-C", str(root), "merge-base", "HEAD", "origin/integration"], capture_output=True, text=True).stdout.strip()
    r = subprocess.run(["git", "-C", str(root), "show", f"{base}:{DEBT}"], capture_output=True, text=True) if base else None
    return json.loads(r.stdout) if r and r.returncode == 0 else None


def check(root: pathlib.Path) -> tuple[list[str], list[str]]:
    """(failures, notes)."""
    tree, fails, notes = Tree(root), [], []
    files = sorted(scan_rglob(root / SPECS, "*.md"))
    if not files:
        return [f"no spec files under {root / SPECS}"], []
    touched = added_lines(root)
    counts = {"missing_file": 0, "missing_name": 0}
    for f in files:
        rel = f.relative_to(root).as_posix()
        lines = f.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, 1):
            for m in misses(tree, line):
                counts["missing_file" if m.endswith("does not exist") else "missing_name"] += 1
        new = touched.get(rel, set())
        for a, b in bullets(lines) if new else []:
            if not any(a + 1 <= n <= b for n in new):
                continue
            for n in range(a, b):
                fails += [f"{rel}:{n + 1}: {m}" for m in misses(tree, lines[n])]
                if s := stale(tree, lines[n]):
                    fails.append(f"{rel}:{n + 1}: {s}")
            # 5 (manager 2026-11-05, review 105): the behaviour this bullet is, or the builder verb it opens with, is no longer
            # "Not yet" anywhere else in the same spec (its own bullet may say what is still left of it)
            names = [f"`{m.group(1)}`"] if (m := ID.match(lines[a])) else []
            names += [f"`builder {v.group(1)}" for v in [OWN_VERB.match(lines[a])] if v]
            for n2, other in enumerate(lines):
                if a <= n2 < b:
                    continue
                for sent in NOT_YET.findall(other):
                    if hit := next((x for x in names if x in sent), None):
                        fails.append(f"{rel}:{n2 + 1}: says {sent.strip()[:80]!r} about {hit.strip('`')}, which this batch's bullet at line {a + 1} builds: say what is built")
            body = "\n".join(lines[a:b])
            if OK_TAG.search(lines[a]) and not any(is_test(p) and tree.file(p) for p, _ in citations(body)):
                fails.append(f"{rel}:{a + 1}: tagged [OK] but cites no test file that exists")
    debt_file = root / DEBT
    debt = json.loads(debt_file.read_text()) if debt_file.is_file() else None
    if debt is None:
        fails.append(f"{DEBT} is missing: write {json.dumps(counts)}")
    else:
        for k, v in counts.items():
            if v > debt.get(k, 0):
                fails.append(f"{v} {k.replace('_', ' ')} citations across the specs, {DEBT} allows {debt.get(k, 0)}: a citation "
                             f"broke outside this batch's bullets (a test renamed or deleted?); fix it, never raise the file")
            elif v < debt.get(k, 0):
                notes.append(f"{k}: {v} now, {debt[k]} in {DEBT}: lower it to {v}")
        if (was := base_debt(root)) and any(debt.get(k, 0) > was.get(k, 0) for k in counts):
            fails.append(f"{DEBT} was raised above its value at the base ({was}): the debt only goes down")
    return fails, notes + [f"debt now: {json.dumps(counts)}"]


def main() -> int:
    fails, notes = check(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve())
    for x in fails:
        print(f"FAIL: {x}")
    for x in notes:
        print(x)
    print(f"check_spec_citations: {len(fails)} problem(s)" if fails else "check_spec_citations: OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
