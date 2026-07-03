#!/usr/bin/env python3
"""Choose the next manager delegation batch from ROADMAP.md and GitHub issues.

The selector is intentionally deterministic: it walks roadmap tiers in document
order, skips claimed/in-progress work, then returns either one large issue or a
3-10 issue same-milestone batch. It does not claim or edit issues.

Usage:
    scripts/choose_next.py
    scripts/choose_next.py --json
    scripts/choose_next.py --issues-json /tmp/issues.json
    scripts/choose_next.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROADMAP = ROOT / "docs" / "ROADMAP.md"
BLOCKING_LABELS = {"status:in-progress"}
SECONDARY_SKIP_LABELS = {"status:blocked", "needs-human-test", "needs:human"}
BIG_MARKERS = (
    "epic",
    "keystone",
    "cross-cutting",
    "cross cutting",
    "migration",
    "new store",
    "store registry",
    "action layer",
    "remote",
    "self-hosting",
    "architecture",
)
MINI_MARKERS = (
    "docs",
    "doc",
    "guardrail",
    "verify",
    "script",
    "tooling",
    "lint",
    "parity",
    "hygiene",
    "matrix",
)


@dataclass(frozen=True)
class RoadmapTier:
    key: str
    title: str
    milestones: tuple[str, ...]
    issue_numbers: tuple[int, ...]


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    milestone: str
    state: str = "OPEN"
    body: str = ""
    url: str = ""

    @property
    def is_ready(self) -> bool:
        if self.state.upper() != "OPEN":
            return False
        if self.assignees:
            return False
        return not (set(self.labels) & BLOCKING_LABELS)

    @property
    def is_secondary_skip(self) -> bool:
        return bool(set(self.labels) & SECONDARY_SKIP_LABELS)

    @property
    def is_big(self) -> bool:
        text = " ".join((self.title, *self.labels)).lower()
        return any(marker in text for marker in BIG_MARKERS)

    @property
    def is_small(self) -> bool:
        return not self.is_big

    @property
    def priority_rank(self) -> int:
        labels = set(self.labels)
        if "priority:P0" in labels or "priority:p0" in labels:
            return 0
        if "priority:P1" in labels or "priority:p1" in labels:
            return 1
        if "priority:P2" in labels or "priority:p2" in labels:
            return 2
        if "priority:P3" in labels or "priority:p3" in labels:
            return 3
        return 4


def _dedupe_keep_order(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        cleaned = item.strip().strip(".")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return tuple(ordered)


def _dedupe_numbers(items: Iterable[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    ordered: list[int] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)


def _extract_milestones(block: str) -> tuple[str, ...]:
    names: list[str] = []
    for line in block.splitlines():
        lowered = line.lower()
        if "milestone:" in lowered or "milestones:" in lowered:
            names.extend(re.findall(r"\*\*([^*]+)\*\*", line))
        elif "domain milestones" in lowered:
            names.extend(re.findall(r"\*\*([^*]+)\*\*", line))
    return _dedupe_keep_order(names)


def parse_roadmap(path: Path = DEFAULT_ROADMAP) -> list[RoadmapTier]:
    text = path.read_text(encoding="utf-8")
    legacy_tiers = _parse_legacy_tiers(text)
    if legacy_tiers:
        return legacy_tiers
    current_work_order = _parse_current_work_order(text)
    if current_work_order:
        return current_work_order
    return _parse_phase_work_order(text)


def _parse_legacy_tiers(text: str) -> list[RoadmapTier]:
    heading_re = re.compile(r"^## Tier (?P<key>\d+b?)\s+[—-]\s+(?P<title>.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(text))
    tiers: list[RoadmapTier] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        tiers.append(
            RoadmapTier(
                key=match.group("key"),
                title=match.group("title").strip(),
                milestones=_extract_milestones(block),
                issue_numbers=_dedupe_numbers(int(num) for num in re.findall(r"#(\d+)", block)),
            )
        )
    return tiers


def _parse_current_work_order(text: str) -> list[RoadmapTier]:
    """Parse the current ROADMAP refined-order format.

    The roadmap was changed from ``## Tier N`` headings to a numbered,
    authoritative work-order block. Keep this deliberately conservative:
    the ordered issue references in each numbered section are enough for
    manager selection, while milestone-wide expansion remains available in
    the legacy/phase formats.
    """

    marker = "### ▶▶ REFINED ORDER"
    marker_index = text.find(marker)
    if marker_index == -1:
        return []

    start = text.find("**1.", marker_index)
    if start == -1:
        return []
    end_marker = "\n### Cross-cutting"
    end = text.find(end_marker, start)
    block = text[start:] if end == -1 else text[start:end]

    heading_re = re.compile(r"^\*\*(?P<key>\d+)\.\s+(?P<title>[^*]+?)\*\*", re.MULTILINE)
    matches = list(heading_re.finditer(block))
    tiers: list[RoadmapTier] = []
    for index, match in enumerate(matches):
        section_start = match.end()
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        section = block[section_start:section_end]
        tiers.append(
            RoadmapTier(
                key=match.group("key"),
                title=match.group("title").strip().rstrip(":"),
                milestones=(),
                issue_numbers=_dedupe_numbers(int(num) for num in re.findall(r"#(\d+)", section)),
            )
        )
    return tiers


def _parse_phase_work_order(text: str) -> list[RoadmapTier]:
    heading_re = re.compile(r"^### Phase (?P<key>\d+)\s+[—-]\s+(?P<title>.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(text))
    tiers: list[RoadmapTier] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        tiers.append(
            RoadmapTier(
                key=match.group("key"),
                title=match.group("title").strip(),
                milestones=_extract_milestones(block),
                issue_numbers=_dedupe_numbers(int(num) for num in re.findall(r"#(\d+)", block)),
            )
        )
    return tiers


def _run_gh(args: list[str]) -> Any:
    result = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _labels(raw: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(item.get("name", "") for item in raw if item.get("name"))


def _assignees(raw: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(item.get("login", "") for item in raw if item.get("login"))


def issue_from_payload(payload: dict[str, Any]) -> Issue:
    milestone = payload.get("milestone") or {}
    milestone_title = milestone.get("title") if isinstance(milestone, dict) else milestone
    return Issue(
        number=int(payload["number"]),
        title=payload.get("title", ""),
        labels=_labels(payload.get("labels", [])),
        assignees=_assignees(payload.get("assignees", [])),
        milestone=milestone_title or "No milestone",
        state=payload.get("state", "OPEN"),
        body=payload.get("body", "") or "",
        url=payload.get("url", ""),
    )


def fetch_milestone_issues(milestone: str, limit: int) -> list[Issue]:
    payload = _run_gh(
        [
            "issue",
            "list",
            "--milestone",
            milestone,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title,labels,assignees,milestone,state,body,url",
        ]
    )
    return [issue_from_payload(item) for item in payload]


def fetch_issue(number: int) -> Issue | None:
    try:
        payload = _run_gh(
            [
                "issue",
                "view",
                str(number),
                "--json",
                "number,title,labels,assignees,milestone,state,body,url",
            ]
        )
    except subprocess.CalledProcessError:
        return None
    return issue_from_payload(payload)


def load_fixture(path: Path) -> list[Issue]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("issues", [])
    return [issue_from_payload(item) for item in payload]


def _issue_sort_key(issue: Issue) -> tuple[int, int]:
    return (issue.priority_rank, issue.number)


def _model_for(issues: list[Issue]) -> str:
    text = " ".join(issue.title + " " + " ".join(issue.labels) for issue in issues).lower()
    if any(marker in text for marker in ("swiftui", "client:swiftui", "frontend", "ui", "view")):
        return "Sonnet (frontend/default)"
    if any(issue.is_big for issue in issues):
        return "codex 5.5 or Opus (keystone/high-blast-radius)"
    return "codex 5.4-mini (backend/tooling/default)"


def _objective(issues: list[Issue]) -> str:
    if len(issues) == 1:
        return issues[0].title
    labels = " ".join(label for issue in issues for label in issue.labels).lower()
    if any(marker in labels for marker in MINI_MARKERS):
        return "Clear same-milestone DX/guardrail/tooling issues while reusing context."
    return "Complete a same-milestone batch while reusing worker context."


def select_batch(tiers: list[RoadmapTier], all_issues: list[Issue]) -> dict[str, Any]:
    by_number = {issue.number: issue for issue in all_issues}
    by_milestone: dict[str, list[Issue]] = defaultdict(list)
    for issue in all_issues:
        by_milestone[issue.milestone].append(issue)

    for tier in tiers:
        candidates: list[Issue] = []
        for number in tier.issue_numbers:
            issue = by_number.get(number)
            if issue is not None:
                candidates.append(issue)
        for milestone in tier.milestones:
            candidates.extend(sorted(by_milestone.get(milestone, []), key=_issue_sort_key))
        candidate_order = {issue.number: index for index, issue in enumerate(_dedupe_issues(candidates))}

        def tier_sort_key(issue: Issue) -> tuple[int, int, int]:
            return (candidate_order.get(issue.number, 10_000), issue.priority_rank, issue.number)

        ready = [issue for issue in _dedupe_issues(candidates) if issue.is_ready and not issue.is_secondary_skip]
        skipped_ready = [issue for issue in _dedupe_issues(candidates) if issue.is_ready and issue.is_secondary_skip]
        if not ready and skipped_ready:
            ready = skipped_ready
        if not ready:
            continue

        # Milestone order within a tier is authoritative: tier.milestones is written in
        # ascending due-date order, so the earliest-due milestone with ready work wins.
        # We must NOT jump to a big/keystone issue in a LATER milestone while an earlier
        # milestone still has ready work (#2913). Big-vs-batch is decided WITHIN the
        # first ready milestone only.
        grouped: dict[str, list[Issue]] = defaultdict(list)
        for issue in ready:
            grouped[issue.milestone].append(issue)
        milestone_order = _dedupe_keep_order([*tier.milestones, *[issue.milestone for issue in ready]])

        selected: list[Issue] = []
        mode = ""
        for milestone in milestone_order:
            group = sorted(grouped.get(milestone, []), key=tier_sort_key)
            if not group:
                continue
            bigs = [issue for issue in group if issue.is_big]
            if bigs:
                selected = [bigs[0]]
                mode = "one-big"
            elif len(group) >= 3:
                selected = group[:10]
                mode = "small-batch"
            else:
                selected = group
                mode = "small-batch" if len(group) > 1 else "one-ready-fallback"
            break
        if not selected:
            continue

        return {
            "tier": {"key": tier.key, "title": tier.title},
            "milestone": selected[0].milestone,
            "mode": mode,
            "model": _model_for(selected),
            "objective": _objective(selected),
            "issues": [_issue_dict(issue) for issue in selected],
        }

    return {"tier": None, "milestone": None, "mode": "none", "model": None, "objective": "No ready unclaimed issue found.", "issues": []}


def _dedupe_issues(issues: Iterable[Issue]) -> list[Issue]:
    seen: set[int] = set()
    ordered: list[Issue] = []
    for issue in issues:
        if issue.number not in seen:
            seen.add(issue.number)
            ordered.append(issue)
    return ordered


def _issue_dict(issue: Issue) -> dict[str, Any]:
    return {
        "number": issue.number,
        "title": issue.title,
        "milestone": issue.milestone,
        "labels": list(issue.labels),
        "url": issue.url,
    }


def load_issues(tiers: list[RoadmapTier], *, fixture: Path | None, limit: int) -> list[Issue]:
    if fixture is not None:
        return load_fixture(fixture)

    issues: list[Issue] = []
    seen_numbers: set[int] = set()
    for tier in tiers:
        for milestone in tier.milestones:
            for issue in fetch_milestone_issues(milestone, limit):
                if issue.number not in seen_numbers:
                    seen_numbers.add(issue.number)
                    issues.append(issue)
        for number in tier.issue_numbers:
            if number in seen_numbers:
                continue
            issue = fetch_issue(number)
            if issue is not None:
                seen_numbers.add(number)
                issues.append(issue)
    return issues


def render_text(selection: dict[str, Any]) -> str:
    if not selection["issues"]:
        return "CHOOSE NEXT\nNo ready unclaimed issue found."

    tier = selection["tier"]
    lines = [
        "CHOOSE NEXT",
        f"Tier: {tier['key']} - {tier['title']}",
        f"Milestone: {selection['milestone']}",
        f"Mode: {selection['mode']}",
        f"Model: {selection['model']}",
        f"Objective: {selection['objective']}",
        "Issues:",
    ]
    for issue in selection["issues"]:
        lines.append(f"- #{issue['number']} {issue['title']}")
    return "\n".join(lines)


def run_self_test() -> int:
    tiers = [
        RoadmapTier("0", "Gates & Verify", ("Developer Experience",), (1921,)),
        RoadmapTier("1", "Infrastructure", ("Infrastructure",), ()),
    ]
    issues = [
        Issue(1920, "endpoint usage guardrail", ("backend",), (), "Developer Experience"),
        Issue(1921, "CLI frontend OpenAPI parity guardrail", ("backend", "status:in-progress"), (), "Developer Experience"),
        Issue(1922, "feature flag hygiene", ("backend",), ("dtubb",), "Developer Experience"),
        Issue(1923, "version date consistency", ("backend",), (), "Developer Experience"),
        Issue(1924, "choose next selector", ("backend",), (), "Developer Experience"),
        Issue(74, "Remote & self-hosting", ("type:feature",), (), "Infrastructure"),
    ]
    selection = select_batch(tiers, issues)
    selected_numbers = [issue["number"] for issue in selection["issues"]]
    assert selection["tier"]["key"] == "0", selection
    assert selection["mode"] == "small-batch", selection
    assert selected_numbers == [1920, 1923, 1924], selection
    assert 1921 not in selected_numbers, selection
    assert 1922 not in selected_numbers, selection

    big_selection = select_batch(tiers, [issues[1], issues[5]])
    assert big_selection["tier"]["key"] == "1", big_selection
    assert big_selection["mode"] == "one-big", big_selection
    assert [issue["number"] for issue in big_selection["issues"]] == [74], big_selection

    # Regression #2913: within a tier, the earliest-due milestone with ready work wins.
    # A big/keystone issue in a LATER milestone must NOT jump ahead of an earlier
    # milestone's ready batch (was: choose_next returned Developer Experience's keystone
    # #2888 instead of Dev & Build Harness's ready batch).
    spine_tier = [RoadmapTier("1", "Foundation", ("Dev & Build Harness", "Developer Experience"), ())]
    spine_issues = [
        Issue(2860, "dev builds should not prompt move to Applications", ("client:swiftui",), (), "Dev & Build Harness"),
        Issue(2870, "nightly build + changelog", ("backend",), (), "Dev & Build Harness"),
        Issue(2871, "verify_all incremental", ("backend",), (), "Dev & Build Harness"),
        Issue(2888, "CLI keystone: route through the audited action registry", ("backend",), (), "Developer Experience"),
    ]
    assert spine_issues[3].is_big, "fixture invalid: #2888 must be big (keystone marker)"
    spine_sel = select_batch(spine_tier, spine_issues)
    assert spine_sel["milestone"] == "Dev & Build Harness", spine_sel
    assert spine_sel["mode"] == "small-batch", spine_sel
    spine_nums = {issue["number"] for issue in spine_sel["issues"]}
    assert spine_nums == {2860, 2870, 2871}, spine_sel
    assert 2888 not in spine_nums, spine_sel

    # Regression #2913: the real spine must list Dev & Build Harness (#109, due 07-05)
    # before Developer Experience (#64, due 07-09) in Tier 1.
    if DEFAULT_ROADMAP.exists():
        t1 = next((t for t in parse_roadmap(DEFAULT_ROADMAP) if t.key == "1"), None)
        assert t1 is not None, "no Tier 1 in real ROADMAP"
        assert "Dev & Build Harness" in t1.milestones and "Developer Experience" in t1.milestones, t1
        assert t1.milestones.index("Dev & Build Harness") < t1.milestones.index("Developer Experience"), t1

    current_roadmap = """
### ▶▶ REFINED ORDER (2026-06-11 PM design session) — authoritative over the 4 phases below
**1. INFRASTRUCTURE (doing NOW — finish before Mac):**
- Remaining backend: **#2045** SSE hardening · **#2026** Tailscale.

**2. MAC-ASSED APP (#2030) — the big UI reform:**
- **#2081 — Library node model (FOUNDATION, do early):**

### Cross-cutting GUARANTEE — Privacy
"""
    parsed = parse_roadmap_from_text_for_test(current_roadmap)
    assert [tier.key for tier in parsed] == ["1", "2"], parsed
    assert parsed[0].title == "INFRASTRUCTURE (doing NOW — finish before Mac)", parsed[0]
    assert parsed[0].issue_numbers == (2045, 2026), parsed[0]
    assert parsed[1].issue_numbers == (2081,), parsed[1]
    print("choose_next self-test passed")
    return 0


def parse_roadmap_from_text_for_test(text: str) -> list[RoadmapTier]:
    legacy_tiers = _parse_legacy_tiers(text)
    if legacy_tiers:
        return legacy_tiers
    current_work_order = _parse_current_work_order(text)
    if current_work_order:
        return current_work_order
    return _parse_phase_work_order(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roadmap", type=Path, default=DEFAULT_ROADMAP)
    parser.add_argument("--issues-json", type=Path, help="Use fixture issues instead of gh.")
    parser.add_argument("--limit", type=int, default=100, help="Open issues to fetch per roadmap milestone.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable selection JSON.")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic selector self-tests.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    tiers = parse_roadmap(args.roadmap)
    if not tiers:
        print(f"choose_next: no roadmap tiers found in {args.roadmap}", file=sys.stderr)
        return 1

    try:
        issues = load_issues(tiers, fixture=args.issues_json, limit=args.limit)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"choose_next: failed to load GitHub issues: {exc}", file=sys.stderr)
        return 1

    selection = select_batch(tiers, issues)
    if args.json:
        print(json.dumps(selection, indent=2, sort_keys=True))
    else:
        print(render_text(selection))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
