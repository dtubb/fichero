"""The feeder (pipeline.feeder-picks-the-milestone, pipeline.brief-lint): pure functions over issue dicts. Which
milestone, in what order, and which issues are fit to hand a coder. No model, no gh calls (core.next_issues reads)."""
from __future__ import annotations

import re

BEHAVIOUR_ID = re.compile(r"`([a-z][a-z0-9-]*\.[a-z0-9.-]+)`")
APPROVED = re.compile(r"\*\*Status:\s*APPROVED")
TEST_PATH = re.compile(r"[\w./-]*test[\w./-]*\.(?:py|swift)\b", re.I)


def approved_ids(spec_texts) -> set[str]:
    """Behaviour ids named in a spec whose header (first 20 lines) says **Status: APPROVED."""
    out: set[str] = set()
    for text in spec_texts:
        if any(APPROVED.search(ln) for ln in text.splitlines()[:20]):
            out |= set(BEHAVIOUR_ID.findall(text))
    return out


def lint(issue: dict, labels: dict, approved: set[str]) -> list[str]:
    """What the issue lacks to be dispatched; empty = fit. A bug needs no spec id, only what it needs to be tested."""
    body, miss = issue.get("body") or "", []
    if labels["bug"] not in issue.get("labels", []):
        ids = set(BEHAVIOUR_ID.findall(body))
        if not ids:
            miss.append("a spec behaviour id (or the bug label)")
        elif not ids & approved:
            miss.append("an APPROVED spec (its behaviour ids are in no approved spec)")
    if not re.search(r"accept|expected|should", body, re.I):
        miss.append("an acceptance line")
    if not TEST_PATH.search(body):
        miss.append("a test path")
    return miss


def step_no(issue: dict) -> int:
    """Build-order position from the `stage:<spec>-<n>` label (steps), else 0."""
    for lab in issue.get("labels", []):
        m = re.fullmatch(r"stage:.*?-(\d+)", lab)
        if m:
            return int(m.group(1))
    return 0


def order(issues: list[dict], labels: dict) -> list[dict]:
    """Urgent bugs, bugs, then steps in build order, then the priority label (priority:N, lower first), then number."""
    def prio(i):
        return min([int(x.split(":")[1]) for x in i.get("labels", []) if re.fullmatch(r"priority:\d+", x)] or [99])

    def key(i):
        bug = labels["bug"] in i.get("labels", [])
        return (not (bug and labels["urgent"] in i.get("labels", [])), not bug, step_no(i), prio(i), i["number"])
    return sorted(issues, key=key)


def blocked(issue: dict, open_numbers: set[int]) -> bool:
    """A `Depends on: #N` line naming an issue that is still open."""
    return any(int(n) in open_numbers for m in re.findall(r"depends on:?([^\n]*)", issue.get("body") or "", re.I)
               for n in re.findall(r"#(\d+)", m))


def pick(issues: list[dict], labels: dict, allowed: list[str], approved: set[str], taken: set[int] = frozenset()) -> dict:
    """{ready: [issue...] in order, write_up: {number: [missing]}, triage: [number]} for one milestone's open issues."""
    open_numbers = {i["number"] for i in issues}
    out = {"ready": [], "write_up": {}, "triage": []}
    for i in order(issues, labels):
        if i["number"] in taken or labels["claimed"] in i.get("labels", []) or blocked(i, open_numbers - {i["number"]}):
            continue
        if i.get("author") not in allowed or labels["from_user"] in i.get("labels", []):
            out["triage"].append(i["number"])
        elif miss := lint(i, labels, approved):
            out["write_up"][i["number"]] = miss
        else:
            out["ready"].append(i)
    return out


def milestone_order(milestones: list[dict]) -> list[str]:
    """Open milestone titles, earliest due first, undated ones after, then by title."""
    return [m["title"] for m in sorted(milestones, key=lambda m: (m.get("due_on") is None, m.get("due_on") or "", m["title"]))]


WRITEUP_LINE = re.compile(r"^\s*(ID|ACCEPTANCE|TEST)\s*:\s*(.+?)\s*$", re.M)


def parse_writeup(text: str) -> dict:
    """The three pieces a write-up worker answers with, one `ID:` / `ACCEPTANCE:` / `TEST:` line each; {} when none parse.
    The id must look like a behaviour id (`area.name`)."""
    got = {k.lower(): v.strip("` ") for k, v in WRITEUP_LINE.findall(text)}
    if "id" in got and not BEHAVIOUR_ID.fullmatch(f"`{got['id']}`"):
        del got["id"]
    return got


def apply_writeup(issue: dict, parts: dict) -> dict:
    """The issue with the missing pieces added to its body (never replacing what it already says)."""
    body, add = issue.get("body") or "", []
    if "id" in parts and not BEHAVIOUR_ID.search(body):
        add.append(f"Spec `{parts['id']}`.")
    if "acceptance" in parts and not re.search(r"accept|expected|should", body, re.I):
        add.append(f"Acceptance: {parts['acceptance']}")
    if "test" in parts and not TEST_PATH.search(body):
        add.append(f"Test: {parts['test']}")
    return dict(issue, body=body + ("\n\n" + "\n".join(add) if add else ""))


FILES = re.compile(r"Files?:\s*([\w./-]+)")


def cluster(issues: list[dict], specs: dict[str, str], size: int = 4) -> dict:
    """The cluster feeder (owner, 2026-10-31): the fit issues grouped by SPEC first, then in the spec's build order,
    with the milestone and the first file named refining the order inside a spec; a spec's run is cut into clusters of
    `size`. The link is, in this order: the `(#N)` in the spec's build-order headings, a behaviour id the spec holds,
    a spec file name in the issue. {clusters: [{spec, issues: [numbers]}], no_spec: [numbers]}. Pure: `specs` is
    {file name: text}; no model, no gh."""
    pos, ids, names = {}, {}, set(specs)
    for name, text in sorted(specs.items()):
        for i, n in enumerate(re.findall(r"\(#(\d+)\)", text)):
            pos.setdefault(int(n), (name, i))
        for bid in BEHAVIOUR_ID.findall(text):
            ids.setdefault(bid, name)

    def link(i):
        body = i.get("body") or ""
        if i["number"] in pos:
            return pos[i["number"]]
        spec = next((ids[b] for b in BEHAVIOUR_ID.findall(body) if b in ids), None) or next((n for n in sorted(names) if n in body), None)
        return (spec, 10**6) if spec else None

    by_spec: dict[str, list] = {}
    for i in issues:
        if (l := link(i)):
            f = FILES.search(i.get("body") or "")
            by_spec.setdefault(l[0], []).append((l[1], i.get("milestone") or "", f.group(1) if f else "", i["number"]))
    out = {"clusters": [], "no_spec": [i["number"] for i in issues if not link(i)]}
    for spec in sorted(by_spec):
        nums = [n for *_, n in sorted(by_spec[spec])]
        out["clusters"] += [{"spec": spec, "issues": nums[k:k + size]} for k in range(0, len(nums), size)]
    return out
