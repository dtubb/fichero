#!/usr/bin/env python3
"""The spec -> issue -> test hand-off, checked instead of remembered.

The rule (creative director, 2026-09-18): today the pipeline
  agent-work note -> spec -> milestone + issues -> issue hygiene -> issue to worker ->
  review -> test pinned to spec -> retag
happens because someone remembers each hand-off. This script makes it a state machine: it
reads every spec behavior, cross-checks it against GitHub issues and the test tree, prints
the illegal states, and emits the deterministic work queue a manager can dispatch from
without re-deriving it by hand each time.

Subcommands: status, check, queue, brief <behavior-id>, agent-work. See each `cmd_*`
docstring below, or `docs/contributor_manual/specs/harness/spec-pipeline.md` for the full
state table.

Deliberately NOT wired into scripts/verify_all.sh: `check` is network-dependent (two `gh`
calls) and verify_all's discovery loop auto-runs anything named `check_*.py`, which must
stay offline-safe. The manager runs this by hand as a dispatch step, not as a gate.

Baseline ratchet: `check` fails only on illegal states NOT YET in
scripts/spec_pipeline_baseline.json (today's known debt), and also fails when a baselined
entry no longer occurs (fixed but not removed) — same shrink-only contract as
check_spec_broken_has_issue.py's grandfather list. Run `check --update-baseline` to accept
the current state as the new baseline (only do this right after fixing something, never to
paper over new debt).

Run examples:
    python scripts/spec_pipeline.py status
    python scripts/spec_pipeline.py check
    python scripts/spec_pipeline.py check --offline
    python scripts/spec_pipeline.py check --update-baseline
    python scripts/spec_pipeline.py queue --limit 15
    python scripts/spec_pipeline.py queue --kind retag
    python scripts/spec_pipeline.py brief panes.split.asymmetric
    python scripts/spec_pipeline.py agent-work
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")
TEST_ROOTS = [pathlib.Path("fichero/Tests"), pathlib.Path("fichero-server/tests")]
AGENT_WORK_DIR = pathlib.Path("agent-work")
BASELINE_PATH = pathlib.Path("scripts/spec_pipeline_baseline.json")
# Legacy milestones that are real non-spec program/workstream buckets (release, hygiene,
# lint sweeps, platform-craft) rather than a surface waiting on a spec — see
# agent-work/spec-pipeline/legacy-milestones-triage.md for how this was populated. Same
# shrink-only contract as check_spec_broken_has_issue.py's GRANDFATHERED_FILES: an entry
# whose milestone is gone, or now has a real spec, or carries no reason, is itself a rule-g
# finding rather than being silently trusted.
NON_SPEC_MILESTONES_PATH = pathlib.Path("scripts/spec_pipeline_non_spec_milestones.json")
GH_REPO = "dtubb/fichero"
# `gh issue list --limit N` silently returns at most N issues — no truncation signal of its
# own. With ~4100 issues in this repo, a low limit was invisible data loss: rules c/e/f/g
# only ever saw the newest ~1000 and reported green on the rest by simply never looking
# (2026-09-18 bug). GH_ISSUE_FETCH_LIMIT must stay comfortably above the repo's total open+
# closed issue count; `_check_not_truncated` fails loud (exit 2) if the fetch ever returns
# exactly this many, rather than silently trusting a possibly-truncated page.
GH_ISSUE_FETCH_LIMIT = 10_000
GH_ISSUE_FETCH_TIMEOUT = 120  # a full 10k-issue fetch measured ~23s; generous margin

# Seed order (creative director, 2026-09-18): surfaces before workstream buckets, in this
# order; anything not listed sorts alphabetically after it. Edit this list, not the code
# that reads it, when priorities change.
MILESTONE_PRIORITY: list[str] = [
    "modes-to-panes",
    "panes-workspaces",
    "workflows",
    "research",
    "automation",
    "kg-tables",
    "kg-entity-inspector",
    "kg-readable-representation",
    "ui-test-harness",
    "ui-testing-strategy",
]

# Workstream buckets are lanes, not designs (AGENTS.md, "No orphans, both directions") — a
# GitHub milestone with this title never needs a spec.
WORKSTREAM_BUCKETS = {
    "bugs", "docs", "documentation", "performance", "ratchets", "hygiene",
    "testing", "chores", "infra", "ci",
}

BROKEN_LIKE_TAGS = {"BROKEN", "GAP/BROKEN", "GAP", "PARTIAL", "MISSING"}

# --- Rule (h): [CONVENTION] governance ---------------------------------------------------
#
# CONVENTION states a norm ("how we work"), not a claim about code — exempt from rule (d)'s
# test-citation requirement the same way an [OK] with a real test is exempt from rule (a)'s
# issue requirement. But an unguarded escape hatch from "cite a test" is worse than no tag at
# all, so every [CONVENTION] behavior is itself tracked as a rule-(h) finding (a ledger entry,
# same shrink-only baseline as every other rule — the CURRENT count becomes the ceiling; a
# NEW convention fails `check` until someone deliberately re-baselines), and two shapes of
# misuse are their own distinct findings on top of that ledger entry:
#   - used outside docs/contributor_manual/specs/harness/ (a process spec) — CONVENTION is
#     for how the team/agents WORK, not an excuse to skip testing a product behavior;
#   - carries no reason clause explaining why no test can pin it — a bare tag with nothing
#     to challenge is unreviewable.
# A substring, not a prefix: SPECS_DIR is repo-relative in production but tests monkeypatch
# it to an absolute tmp path, so a startswith() check on the full spec_path would only work
# in production. "/specs/harness/" is stable in both.
CONVENTION_ALLOWED_DIR = "/specs/harness/"
# A cheap, deliberately loose recognizer for "this behavior explains why it can't be
# tested" — not a grader of the reasoning's quality, just a presence check so a bare
# `[CONVENTION]` with no explanation at all is caught.
CONVENTION_REASON_RE = re.compile(
    r"no test|not a code path|no code path|not testable|human[/ -]agent discipline|"
    r"manual discipline|nothing .*(?:prove|disprove|observe)|true by definition",
    re.IGNORECASE,
)

# Rules whose findings are the kind a docs lane clears in bulk (find/cite a test, or
# reopen/close an issue) rather than code work — `queue --kind retag` filters to these.
RETAG_RULES = {"b", "d", "e"}

# --- Reuse check_spec_broken_has_issue.py's behavior-line parser (creative-director
# instruction, 2026-09-18: import it rather than copying since it's importable). Loaded by
# file path, same pattern its own test suite uses
# (fichero-server/tests/unit/scripts/test_check_spec_broken_has_issue.py).
_BROKEN_ISSUE_SCRIPT = pathlib.Path(__file__).resolve().parent / "check_spec_broken_has_issue.py"
_broken_spec = importlib.util.spec_from_file_location(
    "check_spec_broken_has_issue", _BROKEN_ISSUE_SCRIPT
)
assert _broken_spec and _broken_spec.loader
_broken = importlib.util.module_from_spec(_broken_spec)
sys.modules[_broken_spec.name] = _broken
_broken_spec.loader.exec_module(_broken)  # type: ignore[attr-defined]

_iter_behavior_blocks = _broken._iter_behavior_blocks
BEHAVIOR_ID_RE = _broken.BEHAVIOR_ID_RE

# Everything below is NOT in check_spec_broken_has_issue.py (it only needs BROKEN-family
# tags and doesn't care whether a citation is an arrow-superseded one), so these small
# regexes are our own, commented rather than imported:
# - TAG_RE_ALL also matches [OK] and [PROPOSED] (that script never needs to see those).
# - MILESTONE_RE / STATUS_RE mirror check_spec_milestones.py's one-liners; not worth an
#   import for two regexes.
TAG_RE_ALL = re.compile(r"\*{0,2}\[(OK|BROKEN|GAP(?:/BROKEN)?|PARTIAL|MISSING|PROPOSED|CONVENTION)[^\]]*\]\*{0,2}")
# An issue citation, with an optional leading arrow: "#1234" or "→ #1234" (a superseding
# pointer to another tracked epic increment — legitimately cross-milestone, see rule c).
ISSUE_CITATION_RE = re.compile(r"(→\s*)?#(\d+)")
MILESTONE_RE = re.compile(r"Milestone:\s*(\S+)")
STATUS_RE = re.compile(r"Status:\s*(DRAFT|APPROVED)")
# 7-12 hex chars, at least one a-f letter (otherwise it's just a run of digits: an issue
# number, a date, a line count — not a sha).
SHA_RE = re.compile(r"\b[0-9a-f]{7,12}\b")

# --- Test citations (rule d): four shapes, each backtick-delimited -----------------------
#
# Specs overwhelmingly cite tests MORE precisely than a bare class name — `FooTests.method`,
# several `methodName`s under one `FooTests`, or a pytest node id — and that precision is
# worth keeping (creative-director instruction, 2026-09-18): a cited METHOD that doesn't
# exist in its class is itself a real finding, not just a formatting mismatch. So rule (d)
# resolves, not just pattern-matches:
#   1. `FooTests` / `TestFoo`               — bare class (Swift XCTest/Testing, or pytest)
#   2. `FooTests.method` / `TestFoo.method` — class + method; BOTH must exist, together
#   3. `path/FooTests.swift`                — a path ending in Tests.swift that exists
#   4. `test_x.py`, `test_x.py::Cls::meth`, `test_x.py::meth` — pytest file / node id
#
# A "test class" is any identifier ending in "Tests" or starting with "Test" — narrow
# enough that ordinary source symbols cited in the same prose (`WorkflowSavePolicy`,
# `ClaimStore.patch`) never match rung 2's dotted form.
_TEST_CLASS_NAME = r"(?:[A-Za-z_][A-Za-z0-9_]*Tests|Test[A-Za-z0-9_]*)"
CITATION_CLASS_METHOD_RE = re.compile(rf"`({_TEST_CLASS_NAME})\.([A-Za-z_][A-Za-z0-9_]*)`")
CITATION_CLASS_RE = re.compile(rf"`({_TEST_CLASS_NAME})`")
CITATION_SWIFT_PATH_RE = re.compile(r"`([\w./+-]+Tests\.swift)`")
CITATION_PYTEST_NODE_RE = re.compile(
    r"`([\w./+-]*test_[A-Za-z0-9_]+\.py)(?:::([A-Za-z_][A-Za-z0-9_]*))?(?:::([A-Za-z_][A-Za-z0-9_]*))?`"
)


@dataclass(frozen=True)
class TestCitation:
    raw: str  # the whole backtick-delimited citation, for display
    kind: str  # "class", "class_method", "path", "pytest_node"
    cls: str | None = None
    method: str | None = None
    file: str | None = None


def _parse_test_citations(block: str) -> list[TestCitation]:
    """Every test citation in a behavior block, across all four recognized shapes."""
    citations: list[TestCitation] = []
    method_spans: set[tuple[int, int]] = set()
    for m in CITATION_CLASS_METHOD_RE.finditer(block):
        # A citation ending in `.swift`/`.py` is a PATH (shape 3), never a
        # Class.method (shape 2) — `` `BatchServiceTests.swift` `` looks like
        # class=BatchServiceTests, method=swift to this regex alone, but
        # "swift" here is a file extension, not a method name. Shape 3's own
        # regex (CITATION_SWIFT_PATH_RE) already resolves this citation
        # correctly further down; without this guard BOTH fire, and the
        # bogus class_method half fails resolution even though the file
        # genuinely exists.
        if m.group(2) in ("swift", "py"):
            continue
        citations.append(TestCitation(m.group(0), "class_method", cls=m.group(1), method=m.group(2)))
        method_spans.add(m.span())
    for m in CITATION_CLASS_RE.finditer(block):
        if m.span() in method_spans:
            continue  # already captured as the class half of a class.method citation
        citations.append(TestCitation(m.group(0), "class", cls=m.group(1)))
    for m in CITATION_SWIFT_PATH_RE.finditer(block):
        citations.append(TestCitation(m.group(0), "path", file=m.group(1)))
    for m in CITATION_PYTEST_NODE_RE.finditer(block):
        file_, a, b = m.group(1), m.group(2), m.group(3)
        if b:
            citations.append(TestCitation(m.group(0), "pytest_node", file=file_, cls=a, method=b))
        elif a:
            # "file.py::Something" — a class (pytest convention: starts uppercase / "Test")
            # or a bare test function (lowercase, e.g. "test_foo").
            if a[:1].isupper():
                citations.append(TestCitation(m.group(0), "pytest_node", file=file_, cls=a))
            else:
                citations.append(TestCitation(m.group(0), "pytest_node", file=file_, method=a))
        else:
            citations.append(TestCitation(m.group(0), "path", file=file_))
    return citations


def _citation_display_name(c: TestCitation) -> str:
    return c.cls or c.file or c.raw


def _citation_key(c: TestCitation) -> str:
    """A baseline-stable identity for a citation — the semantic name, not the raw
    backtick-quoted text (which would churn the baseline key on every reformatting)."""
    base = c.cls or c.file or c.raw
    return f"{base}.{c.method}" if c.method else base


@dataclass
class Behavior:
    id: str
    spec_path: str  # repo-relative, e.g. "docs/contributor_manual/specs/ui/panes-workspaces.md"
    line: int
    tag: str
    spec_status: str | None
    spec_milestone: str | None
    issues: list[int] = field(default_factory=list)  # every cited issue, arrow or plain
    plain_issues: list[int] = field(default_factory=list)  # cited WITHOUT a "→" prefix
    tests: list[str] = field(default_factory=list)
    shas: list[str] = field(default_factory=list)
    text: str = ""


@dataclass(frozen=True)
class Finding:
    """One illegal state. `(rule, spec, key)` is the baseline identity — stable across
    reruns even though `message` may reword or pick up a fresher issue title."""
    rule: str
    key: str
    spec: str
    message: str


def _is_scaffold(p: pathlib.Path) -> bool:
    return p.name.startswith("_")


def _spec_files() -> list[pathlib.Path]:
    if not SPECS_DIR.exists():
        return []
    return [p for p in sorted(SPECS_DIR.rglob("*.md")) if not _is_scaffold(p)]


def _spec_header(spec: pathlib.Path) -> tuple[str | None, str | None]:
    head = spec.read_text(encoding="utf-8")[:1200]
    status_m = STATUS_RE.search(head)
    milestone_m = MILESTONE_RE.search(head)
    return (status_m.group(1) if status_m else None, milestone_m.group(1) if milestone_m else None)


def load_behaviors() -> list[Behavior]:
    """Every tagged behavior line across every spec, with its cited issues/tests/shas."""
    behaviors: list[Behavior] = []
    for spec in _spec_files():
        status, milestone = _spec_header(spec)
        lines = spec.read_text(encoding="utf-8").splitlines()
        rel = str(spec).replace("\\", "/")
        for start_line, behavior_id, block in _iter_behavior_blocks(lines):
            tag_m = TAG_RE_ALL.search(block)
            if not tag_m:
                continue  # untagged bullet — not a behavior the pipeline tracks
            tag = tag_m.group(1)
            issue_citations = ISSUE_CITATION_RE.findall(block)  # [(arrow_or_empty, digits), ...]
            issues = sorted({int(n) for _, n in issue_citations})
            plain_issues = sorted({int(n) for arrow, n in issue_citations if not arrow})
            tests = sorted({_citation_display_name(c) for c in _parse_test_citations(block)})
            shas = sorted({s for s in SHA_RE.findall(block) if any(c in "abcdef" for c in s)})
            behaviors.append(
                Behavior(behavior_id, rel, start_line, tag, status, milestone,
                         issues, plain_issues, tests, shas, block)
            )
    return behaviors


# --- GitHub data: batched fetches, cached to a temp file per run ------------------------

def _cache_tempfile(data: object, prefix: str) -> None:
    """Debugging aid only — each subcommand invocation is its own process and fetches
    once, so nothing reads this back within the same run."""
    try:
        fd, _path = tempfile.mkstemp(prefix=prefix, suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def _check_not_truncated(data: list, limit: int, source: str) -> None:
    """A fetch that returns exactly `limit` results proves nothing about whether more exist
    behind it — treat that as truncated, not as "here's everything." Same
    never-green-by-absence register as a missing `gh`: print and exit 2 rather than silently
    trusting a possibly-partial page."""
    if len(data) >= limit:
        print(
            f"FAIL spec_pipeline: {source} returned {len(data)} results, equal to the fetch "
            f"limit ({limit}) — truncated, blind to whatever comes after it, not green. "
            f"Raise the limit."
        )
        raise SystemExit(2)


def get_issues(offline: bool) -> list[dict] | None:
    """All issues (state=all) for GH_REPO, or None when running --offline.

    Exits 2 (never returns) if `gh` is unavailable or fails while online is required —
    "never green-by-absence": a check that silently skipped its GitHub-dependent rules must
    not report success. Tests inject a fixture via the SPEC_PIPELINE_FAKE_ISSUES env var
    (a path to a JSON file) instead of hitting the network, or monkeypatch this function
    directly.
    """
    if offline:
        return None
    fake = os.environ.get("SPEC_PIPELINE_FAKE_ISSUES")
    if fake:
        return json.loads(pathlib.Path(fake).read_text(encoding="utf-8"))
    if shutil.which("gh") is None:
        print("FAIL spec_pipeline: `gh` not found and --offline not passed (blind, not green).")
        raise SystemExit(2)
    try:
        proc = subprocess.run(
            ["gh", "issue", "list", "--repo", GH_REPO, "--state", "all",
             "--limit", str(GH_ISSUE_FETCH_LIMIT),
             "--json", "number,state,milestone,labels,title,assignees"],
            capture_output=True, text=True, timeout=GH_ISSUE_FETCH_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"FAIL spec_pipeline: `gh issue list` failed: {exc}")
        raise SystemExit(2)
    if proc.returncode != 0:
        print(f"FAIL spec_pipeline: `gh issue list` exited {proc.returncode}: {proc.stderr.strip()}")
        raise SystemExit(2)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"FAIL spec_pipeline: `gh issue list` returned invalid JSON: {exc}")
        raise SystemExit(2)
    _check_not_truncated(data, GH_ISSUE_FETCH_LIMIT, "`gh issue list`")
    _cache_tempfile(data, "spec_pipeline_issues_")
    return data


def get_milestones(offline: bool) -> list[dict] | None:
    """Every milestone (open + closed) for GH_REPO, or None when --offline.

    A second, small batched call — `gh issue list` alone is blind to a milestone with zero
    issues, which is exactly the empty-milestone case rule (g) needs to see. Same
    never-green-by-absence contract as `get_issues`: exits 2 rather than reporting success
    on a failed/missing `gh`. Tests inject via SPEC_PIPELINE_FAKE_MILESTONES or by
    monkeypatching this function directly.

    Audited for `get_issues`'s truncation trap (2026-09-18): `per_page=100` here is a PAGE
    size, not a result cap — `--paginate` follows every `Link` header until GitHub says
    there is no next page, so this call cannot silently stop early the way a bare `--limit`
    can. No `_check_not_truncated` needed.
    """
    if offline:
        return None
    fake = os.environ.get("SPEC_PIPELINE_FAKE_MILESTONES")
    if fake:
        return json.loads(pathlib.Path(fake).read_text(encoding="utf-8"))
    if shutil.which("gh") is None:
        print("FAIL spec_pipeline: `gh` not found and --offline not passed (blind, not green).")
        raise SystemExit(2)
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{GH_REPO}/milestones?state=all&per_page=100", "--paginate"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"FAIL spec_pipeline: `gh api .../milestones` failed: {exc}")
        raise SystemExit(2)
    if proc.returncode != 0:
        print(f"FAIL spec_pipeline: `gh api .../milestones` exited {proc.returncode}: {proc.stderr.strip()}")
        raise SystemExit(2)
    # --paginate on a raw `gh api` call concatenates one JSON array per page, back to back
    # (not comma-joined) — decode them one at a time rather than assuming a single array.
    data: list[dict] = []
    text = proc.stdout.strip()
    try:
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(text):
            obj, end = decoder.raw_decode(text, idx)
            data.extend(obj)
            idx = end
            while idx < len(text) and text[idx].isspace():
                idx += 1
    except json.JSONDecodeError as exc:
        print(f"FAIL spec_pipeline: `gh api .../milestones` returned invalid JSON: {exc}")
        raise SystemExit(2)
    _cache_tempfile(data, "spec_pipeline_milestones_")
    return data


def _issue_index(issues: list[dict]) -> dict[int, dict]:
    return {i["number"]: i for i in issues}


def _issue_milestone_title(issue: dict) -> str | None:
    m = issue.get("milestone")
    return m.get("title") if m else None


def _is_unclaimed(issue: dict) -> bool:
    if issue.get("assignees"):
        return False
    labels = {label.get("name", "") for label in issue.get("labels", [])}
    return "status:in-progress" not in labels


# --- Test-tree index (rule d) -------------------------------------------------------------
#
# Resolves each of the four citation shapes above against the real test tree: a class name
# must exist; a class.method pair must BOTH exist, the method inside that class specifically
# (not just anywhere); a path/pytest-file must exist by basename; a pytest node id resolves
# its class and/or method the same way. "Best-effort" line-scanning, not a real parser — it
# tracks Swift brace depth and Python indentation to bound each class's body, which is
# accurate for this codebase's actual formatting without pulling in a Swift/Python AST lib.

_SWIFT_CLASS_RE = re.compile(r"\b(?:class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)")
_SWIFT_FUNC_RE = re.compile(r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)")
_PY_CLASS_RE = re.compile(r"^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)")
_PY_DEF_RE = re.compile(r"^(\s*)def\s+([A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class TestIndex:
    known_names: set[str] = field(default_factory=set)  # any class OR file stem/name seen
    class_methods: dict[str, set[str]] = field(default_factory=dict)  # class -> its methods
    file_basenames: set[str] = field(default_factory=set)  # every *.swift/*.py filename
    py_top_level_funcs: dict[str, set[str]] = field(default_factory=dict)  # filename -> defs


def _index_swift_classes(text: str, idx: TestIndex) -> None:
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        m = _SWIFT_CLASS_RE.search(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        idx.known_names.add(name)
        depth = lines[i].count("{") - lines[i].count("}")
        methods: set[str] = set()
        j = i + 1
        while j < n and depth > 0:
            depth += lines[j].count("{") - lines[j].count("}")
            fm = _SWIFT_FUNC_RE.search(lines[j])
            if fm:
                methods.add(fm.group(1))
            j += 1
        idx.class_methods.setdefault(name, set()).update(methods)
        i = j if j > i else i + 1


def _index_python_classes_and_funcs(text: str, filename: str, idx: TestIndex) -> None:
    lines = text.splitlines()
    n = len(lines)
    top_level: set[str] = set()
    i = 0
    while i < n:
        cm = _PY_CLASS_RE.match(lines[i])
        if cm:
            indent = len(cm.group(1))
            name = cm.group(2)
            idx.known_names.add(name)
            methods: set[str] = set()
            j = i + 1
            while j < n:
                line = lines[j]
                if not line.strip():
                    j += 1
                    continue
                if len(line) - len(line.lstrip()) <= indent:
                    break
                dm = _PY_DEF_RE.match(line)
                if dm:
                    methods.add(dm.group(2))
                j += 1
            idx.class_methods.setdefault(name, set()).update(methods)
            i = j if j > i else i + 1
            continue
        dm = _PY_DEF_RE.match(lines[i])
        if dm and len(dm.group(1)) == 0:
            top_level.add(dm.group(2))
        i += 1
    idx.py_top_level_funcs.setdefault(filename, set()).update(top_level)


def _build_test_index() -> TestIndex:
    idx = TestIndex()
    for root in TEST_ROOTS:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.suffix not in (".swift", ".py"):
                continue
            idx.file_basenames.add(f.name)
            idx.known_names.add(f.stem)
            idx.known_names.add(f.name)
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if f.suffix == ".swift":
                _index_swift_classes(text, idx)
            else:
                _index_python_classes_and_funcs(text, f.name, idx)
    return idx


def _resolve_test_citation(c: TestCitation, idx: TestIndex) -> str | None:
    """None if the citation resolves against the test tree; otherwise the problem."""
    if c.kind == "class":
        if c.cls not in idx.known_names and c.cls not in idx.class_methods:
            return f"test class `{c.cls}` not found"
        return None
    if c.kind == "class_method":
        methods = idx.class_methods.get(c.cls)
        if methods is None:
            return f"test class `{c.cls}` not found"
        if c.method not in methods:
            return f"`{c.cls}` has no method `{c.method}`"
        return None
    if c.kind == "path":
        if pathlib.Path(c.file).name not in idx.file_basenames:
            return f"test file `{c.file}` not found"
        return None
    if c.kind == "pytest_node":
        base = pathlib.Path(c.file).name
        if base not in idx.file_basenames:
            return f"test file `{c.file}` not found"
        if c.cls:
            methods = idx.class_methods.get(c.cls)
            if methods is None and c.cls not in idx.known_names:
                return f"test class `{c.cls}` not found"
            if c.method and methods is not None and c.method not in methods:
                return f"`{c.cls}` has no method `{c.method}`"
            return None
        if c.method:
            all_methods = {m for ms in idx.class_methods.values() for m in ms}
            top_level = idx.py_top_level_funcs.get(base, set())
            if c.method not in top_level and c.method not in all_methods:
                return f"`{c.file}` has no test `{c.method}`"
            return None
        return None
    return None


# --- check: the state machine -------------------------------------------------------------

def _orphan_issue_findings(behaviors: list[Behavior], issues: list[dict]) -> list[Finding]:
    """Rule (f): an OPEN issue on a spec's milestone that no behavior cites."""
    milestone_to_spec: dict[str, str] = {}
    for b in behaviors:
        if b.spec_milestone:
            milestone_to_spec.setdefault(b.spec_milestone, b.spec_path)
    cited = {n for b in behaviors for n in b.issues}
    out = []
    for issue in issues:
        if issue.get("state") != "OPEN":
            continue
        mtitle = _issue_milestone_title(issue)
        if not mtitle or mtitle not in milestone_to_spec:
            continue
        if issue["number"] in cited:
            continue
        spec = milestone_to_spec[mtitle]
        out.append(Finding(
            "f", f"{mtitle}:{issue['number']}", spec,
            f"{spec}: OPEN issue #{issue['number']} \"{issue.get('title', '')}\" on "
            f"milestone '{mtitle}' is cited by no behavior — orphan issue. Cite it from a "
            f"behavior or move it off the milestone (rule f)."
        ))
    return out


def _load_non_spec_milestones() -> list[dict]:
    if not NON_SPEC_MILESTONES_PATH.exists():
        return []
    return json.loads(NON_SPEC_MILESTONES_PATH.read_text(encoding="utf-8"))


def _milestone_orphan_findings(behaviors: list[Behavior], milestones: list[dict]) -> list[Finding]:
    """Rule (g): a GH milestone shaped like a spec anchor with no spec; a spec milestone
    that never shows up on GitHub. Mirrors check_spec_milestones.py's existence check,
    but from the milestone side too (this script's whole point). Uses the dedicated
    milestone listing (not just milestones seen on issues), so an empty milestone is
    visible too.

    Scope (creative-director cross-check, 2026-09-18): a milestone that is CLOSED with zero
    open issues is dead, not debt — GitHub already keeps it out of everyone's way, so it is
    NOT a finding. A closed milestone that still holds open issues, or an open milestone
    with zero open issues, both ARE findings (the first needs its issues moved/reopened, the
    second is a candidate to just close). `scripts/spec_pipeline_non_spec_milestones.json`
    is a shrink-only allowlist (same contract as `check_spec_broken_has_issue.py`'s
    `GRANDFATHERED_FILES`) for real non-spec program/workstream buckets — an allowlisted
    milestone is exempt, but a STALE entry (the milestone is gone, or now has a real spec,
    or carries no `reason`) is itself a rule-(g) finding, so the allowlist can't quietly rot.
    """
    known_milestones = {b.spec_milestone for b in behaviors if b.spec_milestone}
    spec_stems = {pathlib.Path(b.spec_path).stem for b in behaviors}
    live_by_number = {m["number"]: m for m in milestones if "number" in m}
    live_titles = {m.get("title") for m in milestones if m.get("title")}
    out: list[Finding] = []

    allowlist = _load_non_spec_milestones()
    allowlisted_numbers: set[int] = set()
    for entry in allowlist:
        number = entry.get("number")
        title = entry.get("title", "?")
        reason = (entry.get("reason") or "").strip()
        if not reason:
            out.append(Finding(
                "g", f"allowlist-no-reason:{number}", "-",
                f"{NON_SPEC_MILESTONES_PATH}: entry for milestone #{number} '{title}' has "
                f"no `reason` — every allowlist entry needs one (rule g)."
            ))
            continue
        live = live_by_number.get(number)
        if live is None:
            out.append(Finding(
                "g", f"allowlist-stale:{number}", "-",
                f"{NON_SPEC_MILESTONES_PATH}: milestone #{number} '{title}' no longer exists "
                f"on GitHub — remove it from the allowlist (rule g)."
            ))
            continue
        if live.get("title") in known_milestones or live.get("title") in spec_stems:
            out.append(Finding(
                "g", f"allowlist-now-specced:{number}", "-",
                f"{NON_SPEC_MILESTONES_PATH}: milestone #{number} '{title}' now has a spec "
                f"declaring it — remove it from the allowlist (rule g)."
            ))
            continue
        allowlisted_numbers.add(number)

    for m in milestones:
        title = m.get("title")
        if not title:
            continue
        if title.lower() in WORKSTREAM_BUCKETS:
            continue
        if title in known_milestones or title in spec_stems:
            continue
        if m.get("number") in allowlisted_numbers:
            continue
        state = m.get("state")
        open_count = m.get("open_issues", 0)
        if state == "closed" and open_count == 0:
            continue  # dead — GitHub already keeps it out of the way, not a finding
        if state == "closed" and open_count > 0:
            out.append(Finding(
                "g", title, "-",
                f"GitHub milestone '{title}' is CLOSED but holds {open_count} open issue(s) "
                f"and has no spec — reopen it or move its issues off (rule g)."
            ))
            continue
        if open_count == 0:
            out.append(Finding(
                "g", title, "-",
                f"GitHub milestone '{title}' is OPEN with zero open issues and no spec — "
                f"consider closing it (rule g)."
            ))
            continue
        out.append(Finding(
            "g", title, "-",
            f"GitHub milestone '{title}' has no spec declaring `Milestone: {title}` — "
            f"write the spec, or rename/close the milestone if it's a workstream bucket "
            f"(rule g)."
        ))
    for spec_path in sorted({b.spec_path for b in behaviors}):
        m = next((b.spec_milestone for b in behaviors if b.spec_path == spec_path and b.spec_milestone), None)
        if m and m not in live_titles:
            out.append(Finding(
                "g", m, spec_path,
                f"{spec_path}: declares `Milestone: {m}` but no GitHub milestone of that "
                f"name exists yet — create it (rule g)."
            ))
    return out


def _collect_findings(offline: bool, strict: bool) -> tuple[list[Finding], list[str], int, int]:
    """Every illegal state (a)-(g), plus INFO lines. Returns (failures, infos,
    behavior_count, spec_count)."""
    behaviors = load_behaviors()
    failures: list[Finding] = []
    infos: list[str] = []

    # Rule (a): broken/gap/partial/missing with no cited issue — offline-safe, delegates to
    # check_spec_broken_has_issue.py's rule via the shared parser.
    for b in behaviors:
        if b.tag in BROKEN_LIKE_TAGS and not b.issues:
            failures.append(Finding(
                "a", b.id, b.spec_path,
                f"{b.spec_path}:{b.line}: `{b.id}` [{b.tag}] cites no issue — file one and "
                f"cite `#N` (or `→ #N increment K`) (rule a)."
            ))

    issues = get_issues(offline)
    milestones = get_milestones(offline) if issues is not None else None
    if issues is None:
        infos.append(
            "OFFLINE: blind to rules (b) closed-issue-still-broken, (c) milestone mismatch, "
            "(e) OK-cites-open-issue, (f) orphan open issues, (g) GitHub milestone existence."
        )
    else:
        idx = _issue_index(issues)
        for b in behaviors:
            if b.tag in BROKEN_LIKE_TAGS:
                for n in b.issues:
                    issue = idx.get(n)
                    if issue and issue.get("state") == "CLOSED":
                        failures.append(Finding(
                            "b", f"{b.id}:{n}", b.spec_path,
                            f"{b.spec_path}:{b.line}: `{b.id}` [{b.tag}] cites #{n} which is "
                            f"CLOSED — retag `[OK]` with a pinning test, or reopen the issue "
                            f"if the tag is right (rule b)."
                        ))
            if b.spec_milestone:
                # Rule (c) only binds a PLAIN "#N" citation to the spec's own milestone. An
                # arrow citation ("→ #4705 increment 6") is a deliberate pointer to another
                # tracked epic and is legitimately cross-milestone.
                for n in b.plain_issues:
                    issue = idx.get(n)
                    if not issue:
                        continue
                    mtitle = _issue_milestone_title(issue)
                    if mtitle and mtitle != b.spec_milestone:
                        failures.append(Finding(
                            "c", f"{b.id}:{n}", b.spec_path,
                            f"{b.spec_path}:{b.line}: `{b.id}` cites #{n} on milestone "
                            f"'{mtitle}' but the spec declares `Milestone: {b.spec_milestone}` "
                            f"— move the issue to '{b.spec_milestone}' or fix the citation "
                            f"(rule c)."
                        ))
            if b.tag == "OK":
                for n in b.issues:
                    issue = idx.get(n)
                    if issue and issue.get("state") == "OPEN":
                        failures.append(Finding(
                            "e", f"{b.id}:{n}", b.spec_path,
                            f"{b.spec_path}:{b.line}: `{b.id}` [OK] cites #{n} which is still "
                            f"OPEN — retag `[PARTIAL]`/`[GAP]` until it lands, or close the "
                            f"issue (rule e)."
                        ))
        orphan_findings = _orphan_issue_findings(behaviors, issues)
        if strict:
            failures.extend(orphan_findings)
        else:
            infos.extend(f.message for f in orphan_findings)
        failures.extend(_milestone_orphan_findings(behaviors, milestones or []))

    # Rule (h): every [CONVENTION] behavior is a tracked ledger entry (shrink-only ceiling —
    # ONLY entry NOT gated on a check for correctness: it fires even for a compliant one, so
    # the count itself is what needs a deliberate --update-baseline to grow), plus two
    # narrower findings for misuse.
    for b in behaviors:
        if b.tag != "CONVENTION":
            continue
        failures.append(Finding(
            "h", f"convention:{b.id}", b.spec_path,
            f"{b.spec_path}:{b.line}: `{b.id}` [CONVENTION] — registered (rule h ledger; "
            f"the count is a shrink-only ceiling, re-baseline deliberately to add one)."
        ))
        if CONVENTION_ALLOWED_DIR not in b.spec_path:
            failures.append(Finding(
                "h", f"convention-outside-harness:{b.id}", b.spec_path,
                f"{b.spec_path}:{b.line}: `{b.id}` [CONVENTION] used outside a "
                f"specs/harness/ process spec — CONVENTION is for process/harness specs, not "
                f"an escape hatch from testing a product behavior (rule h)."
            ))
        if not CONVENTION_REASON_RE.search(b.text):
            failures.append(Finding(
                "h", f"convention-no-reason:{b.id}", b.spec_path,
                f"{b.spec_path}:{b.line}: `{b.id}` [CONVENTION] carries no reason clause "
                f"explaining why no test can pin it (rule h)."
            ))

    # Rule (d): [OK] with no test cited at all, or a cited test/method that does not exist.
    test_index = _build_test_index()
    for b in behaviors:
        if b.tag != "OK":
            continue
        citations = _parse_test_citations(b.text)
        if not citations:
            failures.append(Finding(
                "d", b.id, b.spec_path,
                f"{b.spec_path}:{b.line}: `{b.id}` [OK] cites no test — add a pinning test "
                f"and cite its name (rule d)."
            ))
            continue
        for c in citations:
            problem = _resolve_test_citation(c, test_index)
            if problem:
                failures.append(Finding(
                    "d", f"{b.id}:{_citation_key(c)}", b.spec_path,
                    f"{b.spec_path}:{b.line}: `{b.id}` [OK] cites {c.raw} — {problem} — fix "
                    f"the citation or ship the test (rule d)."
                ))

    return failures, infos, len(behaviors), len({b.spec_path for b in behaviors})


def _load_baseline() -> list[dict]:
    if not BASELINE_PATH.exists():
        return []
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baseline(failures: list[Finding]) -> None:
    # Deterministic ordering -> stable diffs: sorted by (rule, spec, key), never insertion
    # order. Re-running --update-baseline with no code/tree change is a no-op diff.
    entries = sorted({(f.rule, f.spec, f.key) for f in failures})
    data = [{"rule": r, "spec": s, "key": k} for r, s, k in entries]
    BASELINE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def cmd_check(offline: bool, strict: bool, update_baseline: bool) -> int:
    """The state machine: fails only on illegal states not yet in the baseline (today's
    known debt), and on a baselined entry that no longer occurs (fixed but not removed —
    the baseline can only shrink, same contract as check_spec_broken_has_issue.py's
    grandfather list)."""
    failures, infos, n_behaviors, n_specs = _collect_findings(offline, strict)

    if update_baseline:
        _write_baseline(failures)
        for i in infos:
            print(f"INFO {i}")
        print(
            f"OK spec_pipeline check --update-baseline: wrote {len(failures)} illegal "
            f"state(s) to {BASELINE_PATH}."
        )
        return 0

    baseline = _load_baseline()
    baseline_set = {(e["rule"], e["spec"], e["key"]) for e in baseline}
    current_set = {(f.rule, f.spec, f.key) for f in failures}

    new_findings = [f for f in failures if (f.rule, f.spec, f.key) not in baseline_set]
    fixed_but_listed = sorted(baseline_set - current_set)

    for f in new_findings:
        print(f"FAIL NEW {f.message}")
    for rule, spec, key in fixed_but_listed:
        print(
            f"FAIL {spec}: baselined illegal state rule ({rule}) `{key}` no longer occurs "
            f"— fixed but not removed from {BASELINE_PATH}."
        )
    for i in infos:
        print(f"INFO {i}")

    if new_findings or fixed_but_listed:
        print(
            f"FAIL spec_pipeline check: {n_behaviors} tagged behaviors across {n_specs} "
            f"specs, {len(new_findings)} NEW illegal state(s), {len(fixed_but_listed)} "
            f"stale baseline entrie(s), {len(baseline_set & current_set)} pre-existing "
            f"baselined, {len(infos)} info line(s)."
        )
        return 1

    by_rule: dict[str, int] = {}
    for f in failures:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
    by_rule_str = ", ".join(f"{r}={c}" for r, c in sorted(by_rule.items())) or "none"
    print(
        f"OK spec_pipeline check: {n_behaviors} tagged behaviors across {n_specs} specs, "
        f"{len(failures)} baselined illegal state(s) remain (by rule: {by_rule_str}), "
        f"{len(infos)} info line(s)."
    )
    return 0


# --- status ---------------------------------------------------------------------------

TAG_COLUMNS = ["OK", "BROKEN", "GAP/BROKEN", "PARTIAL", "GAP", "MISSING", "PROPOSED", "CONVENTION"]


def cmd_status() -> int:
    """Table per spec: counts by tag. Always exits 0 — this is a report, not a gate."""
    behaviors = load_behaviors()
    by_spec: dict[str, dict[str, int]] = {}
    for b in behaviors:
        by_spec.setdefault(b.spec_path, {})[b.tag] = by_spec.setdefault(b.spec_path, {}).get(b.tag, 0) + 1

    header = f"{'SPEC':<62} " + " ".join(f"{t:>11}" for t in TAG_COLUMNS) + "  TOTAL"
    print(header)
    total_all = 0
    for spec_path in sorted(by_spec):
        counts = by_spec[spec_path]
        row_total = sum(counts.values())
        total_all += row_total
        row = f"{spec_path:<62} " + " ".join(f"{counts.get(t, 0):>11}" for t in TAG_COLUMNS)
        print(f"{row}  {row_total}")
    print(f"OK spec_pipeline status: {len(by_spec)} specs, {total_all} tagged behaviors.")
    return 0


# --- queue ------------------------------------------------------------------------------

def _milestone_rank(name: str | None) -> tuple[int, str]:
    if name in MILESTONE_PRIORITY:
        return (MILESTONE_PRIORITY.index(name), "")
    return (len(MILESTONE_PRIORITY), name or "~")


def _tag_rank(tag: str) -> int:
    if tag in ("BROKEN", "GAP/BROKEN"):
        return 0
    if tag == "PARTIAL":
        return 1
    if tag in ("GAP", "MISSING"):
        return 2
    return 9


_FILE_MENTION_RE = re.compile(r"`([\w./+-]+\.\w+)`")


def _cmd_queue_code(milestone_filter: str | None, limit: int | None, as_json: bool, offline: bool) -> int:
    """Every dispatchable behavior: broken/gap/partial/missing, with an OPEN, UNCLAIMED
    cited issue, in deterministic (milestone priority, tag severity, spec order) order."""
    behaviors = load_behaviors()
    issues = get_issues(offline)
    idx = _issue_index(issues) if issues is not None else {}
    if issues is None:
        print(
            "INFO spec_pipeline queue: OFFLINE — issue open/claimed state is unknown; this "
            "queue lists behaviors that at least cite an issue, unfiltered by its state.",
            file=sys.stderr,
        )

    candidates: list[tuple[Behavior, dict | None]] = []
    for b in behaviors:
        if b.tag not in BROKEN_LIKE_TAGS:
            continue
        if milestone_filter and b.spec_milestone != milestone_filter:
            continue
        if not b.issues:
            continue  # rule (a) violation — `check` reports it; queue can't dispatch it
        issue = None
        for n in sorted(b.issues):
            if issues is None:
                issue = {"number": n, "title": ""}
                break
            cand = idx.get(n)
            if cand is not None:
                issue = cand
                break
        if issue is None:
            continue  # cited issue not found in the fetch (typo/deleted)
        if issues is not None:
            if issue.get("state") != "OPEN":
                continue
            if not _is_unclaimed(issue):
                continue
        candidates.append((b, issue))

    candidates.sort(key=lambda pair: (_milestone_rank(pair[0].spec_milestone), _tag_rank(pair[0].tag), pair[0].spec_path, pair[0].line))
    if limit is not None:
        candidates = candidates[:limit]

    items = []
    for b, issue in candidates:
        files = sorted({m for m in _FILE_MENTION_RE.findall(b.text) if (REPO_ROOT / m).exists()})
        items.append({
            "id": b.id,
            "spec": f"{b.spec_path}:{b.line}",
            "tag": b.tag,
            "milestone": b.spec_milestone,
            "issue": issue.get("number") if issue else None,
            "issue_title": issue.get("title") if issue else None,
            "text": b.text,
            "test": b.tests[0] if b.tests else "TEST NAME NEEDED",
            "files": files,
        })

    if as_json:
        print(json.dumps(items, indent=2))
        return 0

    for it in items:
        print(f"[{it['tag']}] `{it['id']}`  {it['spec']}  #{it['issue']}: {it['issue_title']}")
        print(f"    test: {it['test']}")
        if it["files"]:
            print(f"    files: {', '.join(it['files'])}")
        print(f"    {it['text'].splitlines()[0]}")
    print(f"OK spec_pipeline queue: {len(items)} dispatchable behavior(s).")
    return 0


def _cmd_queue_retag(limit: int | None, as_json: bool, offline: bool) -> int:
    """The DOC-fixable queue: rule (b)/(d)/(e) findings, grouped by spec — a docs lane finds
    the pinning test to cite, or reopens/closes the mistagged issue, in bulk. Distinct from
    the code-work queue (`--kind code`, the default)."""
    failures, _infos, _n_behaviors, _n_specs = _collect_findings(offline, strict=False)
    debt = sorted((f for f in failures if f.rule in RETAG_RULES), key=lambda f: (f.spec, f.rule, f.key))
    if limit is not None:
        debt = debt[:limit]

    if as_json:
        print(json.dumps([{"rule": f.rule, "spec": f.spec, "key": f.key, "message": f.message} for f in debt], indent=2))
        return 0

    grouped: dict[str, list[Finding]] = {}
    for f in debt:
        grouped.setdefault(f.spec, []).append(f)
    for spec in sorted(grouped):
        print(f"{spec}:")
        for f in grouped[spec]:
            print(f"  [{f.rule}] {f.message}")
    print(f"OK spec_pipeline queue --kind retag: {len(debt)} doc-fixable item(s) across {len(grouped)} spec(s).")
    return 0


def cmd_queue(milestone_filter: str | None, limit: int | None, as_json: bool, offline: bool, kind: str = "code") -> int:
    if kind == "retag":
        return _cmd_queue_retag(limit, as_json, offline)
    return _cmd_queue_code(milestone_filter, limit, as_json, offline)


# --- brief ------------------------------------------------------------------------------

BRIEF_TEMPLATE = """WORKER BRIEF — {behavior_id}

Repo: {repo_root} (git worktree — work only there).

Standing rules:
  - No xcodebuild, no gate, no commit unless this brief says otherwise.
  - Never bare `git stash` — the stash stack is shared across worktrees.
  - A new call shape needs BOTH `swiftc -parse` and `-typecheck` proof, not parse alone.
  - Swift Testing's #expect/Issue.record message is `Comment?` — one literal string, never
    `+`-concatenated or a String variable.
  - Static helpers are `Self.`-qualified.
  - Python: run `PYTHONPATH=$PWD/fichero-server/src .venv/bin/python ...` from the repo root.

Behavior: `{behavior_id}` [{tag}]
Spec: {spec}

{text}

Issue: #{issue} — {issue_title}

Ship a pinning test: {test}

When the test is green, retag the spec line `[OK]` and cite the test name (the manager adds
the landing commit sha).

Claim the issue before starting:
  gh issue edit {issue} --add-label status:in-progress
"""


def cmd_brief(behavior_id: str, offline: bool) -> int:
    behaviors = load_behaviors()
    match = next((b for b in behaviors if b.id == behavior_id), None)
    if match is None:
        print(f"FAIL spec_pipeline brief: no behavior `{behavior_id}` found under {SPECS_DIR}")
        return 1
    issues = get_issues(offline)
    issue_number = match.issues[0] if match.issues else None
    issue_title = ""
    if issues is not None and issue_number is not None:
        issue_title = _issue_index(issues).get(issue_number, {}).get("title", "")
    test_name = match.tests[0] if match.tests else "TEST NAME NEEDED — name it before dispatch"
    print(BRIEF_TEMPLATE.format(
        behavior_id=match.id,
        repo_root=REPO_ROOT,
        tag=match.tag,
        spec=f"{match.spec_path}:{match.line}",
        text=match.text,
        issue=issue_number if issue_number is not None else "NONE — file one first",
        issue_title=issue_title,
        test=test_name,
    ))
    return 0


# --- agent-work ---------------------------------------------------------------------------

def cmd_agent_work() -> int:
    """Inventory of agent-work/**/*.md: FOLDED (a spec references its path/name), HISTORICAL
    (front-matter/first-line marker), else UNTRIAGED. INFO only — never fails."""
    if not AGENT_WORK_DIR.exists():
        print(f"INFO spec_pipeline agent-work: no {AGENT_WORK_DIR} directory found.")
        return 0
    files = sorted(AGENT_WORK_DIR.rglob("*.md"))
    spec_text = "\n".join(
        spec.read_text(encoding="utf-8", errors="ignore") for spec in _spec_files()
    )
    folded, historical, untriaged = [], [], []
    for f in files:
        rel = str(f).replace("\\", "/")
        head = f.read_text(encoding="utf-8", errors="ignore")[:400]
        if re.match(r"^\s*(?:Status:\s*)?HISTORICAL\b", head, re.M):
            historical.append(rel)
        elif rel in spec_text or f.name in spec_text:
            folded.append(rel)
        else:
            untriaged.append(rel)
    print(
        f"OK spec_pipeline agent-work: {len(files)} files — {len(folded)} FOLDED, "
        f"{len(historical)} HISTORICAL, {len(untriaged)} UNTRIAGED."
    )
    if untriaged:
        print("UNTRIAGED:")
        for u in untriaged:
            print(f"  - {u}")
    return 0


# --- CLI ------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spec_pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    p_check = sub.add_parser("check")
    p_check.add_argument("--offline", action="store_true")
    p_check.add_argument("--strict", action="store_true", help="promote orphan-issue INFO to a failure")
    p_check.add_argument("--update-baseline", action="store_true", help="accept the current state as the new baseline")

    p_queue = sub.add_parser("queue")
    p_queue.add_argument("--milestone")
    p_queue.add_argument("--limit", type=int, default=None)
    p_queue.add_argument("--json", action="store_true")
    p_queue.add_argument("--offline", action="store_true")
    p_queue.add_argument("--kind", choices=["code", "retag"], default="code",
                          help="code = dispatchable code work (default); retag = doc-fixable rule b/d/e items, grouped by spec")

    p_brief = sub.add_parser("brief")
    p_brief.add_argument("behavior_id")
    p_brief.add_argument("--offline", action="store_true")

    sub.add_parser("agent-work")

    args = parser.parse_args(argv)

    if args.command == "status":
        return cmd_status()

    if args.command == "agent-work":
        return cmd_agent_work()

    if not SPECS_DIR.exists():
        print(f"FAIL spec_pipeline {args.command}: specs directory missing: {SPECS_DIR} (blind, not green)")
        return 2

    if args.command == "check":
        return cmd_check(args.offline, args.strict, args.update_baseline)
    if args.command == "queue":
        return cmd_queue(args.milestone, args.limit, args.json, args.offline, args.kind)
    if args.command == "brief":
        return cmd_brief(args.behavior_id, args.offline)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
