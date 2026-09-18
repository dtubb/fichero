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

Deliberately NOT wired into scripts/verify_all.sh: `check` is network-dependent (one `gh`
call) and verify_all's discovery loop auto-runs anything named `check_*.py`, which must
stay offline-safe. The manager runs this by hand as a dispatch step, not as a gate.

Run examples:
    python scripts/spec_pipeline.py status
    python scripts/spec_pipeline.py check
    python scripts/spec_pipeline.py check --offline
    python scripts/spec_pipeline.py queue --limit 15
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
GH_REPO = "dtubb/fichero"

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
# tags), so these small regexes are our own, commented rather than imported:
# - TAG_RE_ALL also matches [OK] and [PROPOSED] (that script never needs to see those).
# - MILESTONE_RE / STATUS_RE mirror check_spec_milestones.py's one-liners; not worth an
#   import for two regexes.
TAG_RE_ALL = re.compile(r"\*{0,2}\[(OK|BROKEN|GAP(?:/BROKEN)?|PARTIAL|MISSING|PROPOSED)[^\]]*\]\*{0,2}")
ISSUE_RE = re.compile(r"#(\d+)")
MILESTONE_RE = re.compile(r"Milestone:\s*(\S+)")
STATUS_RE = re.compile(r"Status:\s*(DRAFT|APPROVED)")
# Backticked identifiers ending in "Tests" (a Swift/pytest suite name) or a "test_*.py" file.
TEST_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*Tests)`|`(test_[A-Za-z0-9_]+\.py)`")
# 7-12 hex chars, at least one a-f letter (otherwise it's just a run of digits: an issue
# number, a date, a line count — not a sha).
SHA_RE = re.compile(r"\b[0-9a-f]{7,12}\b")


@dataclass
class Behavior:
    id: str
    spec_path: str  # repo-relative, e.g. "docs/contributor_manual/specs/ui/panes-workspaces.md"
    line: int
    tag: str
    spec_status: str | None
    spec_milestone: str | None
    issues: list[int] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    shas: list[str] = field(default_factory=list)
    text: str = ""


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
            issues = sorted({int(n) for n in ISSUE_RE.findall(block)})
            tests = sorted({t for pair in TEST_RE.findall(block) for t in pair if t})
            shas = sorted({s for s in SHA_RE.findall(block) if any(c in "abcdef" for c in s)})
            behaviors.append(
                Behavior(behavior_id, rel, start_line, tag, status, milestone, issues, tests, shas, block)
            )
    return behaviors


# --- GitHub data: one batched fetch per run ---------------------------------------------

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
            ["gh", "issue", "list", "--repo", GH_REPO, "--state", "all", "--limit", "1000",
             "--json", "number,state,milestone,labels,title,assignees"],
            capture_output=True, text=True, timeout=30,
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
    # Cached to a temp file for the run (debugging aid — each subcommand invocation is its
    # own process and fetches once, so this is not read back within the same run).
    try:
        fd, path = tempfile.mkstemp(prefix="spec_pipeline_issues_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass
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

_IDENT_RE = re.compile(r"\b(?:func|def|struct|class)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _build_test_index() -> set[str]:
    """Every test filename stem/name and every func/def/struct/class identifier under
    TEST_ROOTS — used to resolve a cited test name (rule d)."""
    index: set[str] = set()
    for root in TEST_ROOTS:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.suffix not in (".swift", ".py"):
                continue
            index.add(f.stem)
            index.add(f.name)  # covers a literal "test_*.py" citation
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            index.update(_IDENT_RE.findall(text))
    return index


# --- check: the state machine -------------------------------------------------------------

def _orphan_issue_findings(behaviors: list[Behavior], issues: list[dict]) -> list[str]:
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
        out.append(
            f"{milestone_to_spec[mtitle]}: OPEN issue #{issue['number']} "
            f"\"{issue.get('title', '')}\" on milestone '{mtitle}' is cited by no behavior — "
            f"orphan issue. Cite it from a behavior or move it off the milestone (rule f)."
        )
    return out


def _milestone_orphan_findings(behaviors: list[Behavior], issues: list[dict]) -> list[str]:
    """Rule (g): a GH milestone shaped like a spec anchor with no spec; a spec milestone
    that never shows up on GitHub. Mirrors check_spec_milestones.py's existence check,
    but from the milestone side too (this script's whole point)."""
    known_milestones = {b.spec_milestone for b in behaviors if b.spec_milestone}
    spec_stems = {pathlib.Path(b.spec_path).stem for b in behaviors}
    out = []
    seen_titles: set[str] = set()
    for issue in issues:
        mtitle = _issue_milestone_title(issue)
        if not mtitle or mtitle in seen_titles:
            continue
        seen_titles.add(mtitle)
        if mtitle.lower() in WORKSTREAM_BUCKETS:
            continue
        if mtitle in known_milestones or mtitle in spec_stems:
            continue
        out.append(
            f"GitHub milestone '{mtitle}' has issues but no spec declares "
            f"`Milestone: {mtitle}` — write the spec, or rename/close the milestone if it's "
            f"a workstream bucket (rule g)."
        )
    for spec_path in sorted({b.spec_path for b in behaviors}):
        m = next((b.spec_milestone for b in behaviors if b.spec_path == spec_path and b.spec_milestone), None)
        if m and m not in seen_titles:
            out.append(
                f"{spec_path}: declares `Milestone: {m}` but no GitHub issue carries that "
                f"milestone yet — create the milestone and file its issues (rule g)."
            )
    return out


def cmd_check(offline: bool, strict: bool) -> int:
    """The state machine: prints every illegal state (a)-(g) as file:line + id + fix."""
    behaviors = load_behaviors()
    failures: list[str] = []
    infos: list[str] = []

    # Rule (a): broken/gap/partial/missing with no cited issue — offline-safe, delegates to
    # check_spec_broken_has_issue.py's rule via the shared parser.
    for b in behaviors:
        if b.tag in BROKEN_LIKE_TAGS and not b.issues:
            failures.append(
                f"{b.spec_path}:{b.line}: `{b.id}` [{b.tag}] cites no issue — file one and "
                f"cite `#N` (or `→ #N increment K`) (rule a)."
            )

    issues = get_issues(offline)
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
                        failures.append(
                            f"{b.spec_path}:{b.line}: `{b.id}` [{b.tag}] cites #{n} which is "
                            f"CLOSED — retag `[OK]` with a pinning test, or reopen the issue "
                            f"if the tag is right (rule b)."
                        )
            if b.spec_milestone:
                for n in b.issues:
                    issue = idx.get(n)
                    if not issue:
                        continue
                    mtitle = _issue_milestone_title(issue)
                    if mtitle and mtitle != b.spec_milestone:
                        failures.append(
                            f"{b.spec_path}:{b.line}: `{b.id}` cites #{n} on milestone "
                            f"'{mtitle}' but the spec declares `Milestone: {b.spec_milestone}` "
                            f"— move the issue to '{b.spec_milestone}' or fix the citation "
                            f"(rule c)."
                        )
            if b.tag == "OK":
                for n in b.issues:
                    issue = idx.get(n)
                    if issue and issue.get("state") == "OPEN":
                        failures.append(
                            f"{b.spec_path}:{b.line}: `{b.id}` [OK] cites #{n} which is still "
                            f"OPEN — retag `[PARTIAL]`/`[GAP]` until it lands, or close the "
                            f"issue (rule e)."
                        )
        orphan_issue_msgs = _orphan_issue_findings(behaviors, issues)
        if strict:
            failures.extend(orphan_issue_msgs)
        else:
            infos.extend(orphan_issue_msgs)
        failures.extend(_milestone_orphan_findings(behaviors, issues))

    # Rule (d): [OK] with no test, or a cited test that doesn't exist.
    test_index = _build_test_index()
    for b in behaviors:
        if b.tag != "OK":
            continue
        if not b.tests:
            failures.append(
                f"{b.spec_path}:{b.line}: `{b.id}` [OK] cites no test — add a pinning test "
                f"and cite its name (rule d)."
            )
            continue
        for t in b.tests:
            if t not in test_index:
                failures.append(
                    f"{b.spec_path}:{b.line}: `{b.id}` [OK] cites test `{t}` which does not "
                    f"exist anywhere under {TEST_ROOTS[0]} or {TEST_ROOTS[1]} — fix the "
                    f"citation or ship the test (rule d)."
                )

    for f in failures:
        print(f"FAIL {f}")
    for i in infos:
        print(f"INFO {i}")

    verdict = "FAIL" if failures else "OK"
    print(
        f"{verdict} spec_pipeline check: {len(behaviors)} tagged behaviors across "
        f"{len({b.spec_path for b in behaviors})} specs, {len(failures)} illegal state(s), "
        f"{len(infos)} info line(s)."
    )
    return 1 if failures else 0


# --- status ---------------------------------------------------------------------------

TAG_COLUMNS = ["OK", "BROKEN", "GAP/BROKEN", "PARTIAL", "GAP", "MISSING", "PROPOSED"]


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


def cmd_queue(milestone_filter: str | None, limit: int | None, as_json: bool, offline: bool) -> int:
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

    p_queue = sub.add_parser("queue")
    p_queue.add_argument("--milestone")
    p_queue.add_argument("--limit", type=int, default=None)
    p_queue.add_argument("--json", action="store_true")
    p_queue.add_argument("--offline", action="store_true")

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
        return cmd_check(args.offline, args.strict)
    if args.command == "queue":
        return cmd_queue(args.milestone, args.limit, args.json, args.offline)
    if args.command == "brief":
        return cmd_brief(args.behavior_id, args.offline)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
