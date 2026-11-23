"""`builder review start|check|approve <area>`: a review is a step kind (local.review.*, #6847).

A review session writes a report (headings in `prompts/review-common.md`) and spec changes on branch `review-<area>`.
This module reads the report, refuses a malformed one, and does what a program can do after the owner approves it:
file the issues, map the spec's `NEW` tags by id, number the Build order, add the milestone to build-order.md, comment
on the issues that gained evidence, turn the owner's questions into alerts, commit, and enqueue the steps once landed."""
from __future__ import annotations

import re
from pathlib import Path

SECTIONS = {  # key -> heading regex (a `##` heading, its number and case ignored)
    "exists": r"what exists",
    "measured": r"(?:what i )?measured|how it was measured",
    "fixes": r"ranked fixes",
    "issues": r"issues to file",
    "questions": r"(?:open )?questions(?: for the owner)?",
    "evidence": r"existing issues that gained evidence",
}
LABEL = {"exists": "What exists", "measured": "Measured", "fixes": "Ranked fixes", "issues": "Issues to file", "questions": "Open questions"}
REQUIRED = tuple(LABEL)
HEADING = re.compile(r"^##\s+(?:\d+[.)]?\s+)?(.*?)\s*$")
ITEM = re.compile(r"^(\s{0,1})(?:\d+[.)]|[-*])\s+(.*)$")
NEW_ID = re.compile(r"#?NEW-(S?\d+)\b")
BEHAVIOUR = re.compile(r"`([a-z0-9][\w-]*(?:\.[\w-]+)+)`")
STEP_REF = re.compile(r"\[(\d+\.\d+)\]")


def sections(text: str) -> dict[str, list[str]]:
    """{key: body lines} for each known `##` heading; the first heading of a key wins."""
    out: dict[str, list[str]] = {}
    key = None
    for ln in text.splitlines():
        m = HEADING.match(ln)
        if m:
            key = next((k for k, rx in SECTIONS.items() if re.match(rx + r"\b", m.group(1).strip().lower())), None)
            if key in out:
                key = None
            elif key:
                out[key] = []
        elif key:
            out[key].append(ln)
    return out


def items(body: list[str]) -> list[str]:
    """The top-level list items of a body, each with its indented continuation lines joined by a space."""
    out: list[str] = []
    for ln in body:
        m = ITEM.match(ln)
        if m:
            out.append(m.group(2).strip())
        elif ln.lstrip().startswith("|") and re.search(r"#\d+", ln):  # a table row naming an issue
            out.append(" ".join(c.strip() for c in ln.strip().strip("|").split("|")))
        elif out and ln.strip() and not ln.lstrip().startswith("|"):
            out[-1] += " " + ln.strip()
    return out


def parse(text: str) -> dict:
    """{'sections': set of keys present, 'fixes': [{n, text, new, old, step}], 'issues': [{key, title, behaviours, text}],
    'questions': [str], 'evidence': [(number, text)]}."""
    sec = sections(text)
    fixes = []
    for n, it in enumerate(items(sec.get("fixes", [])), 1):
        step = STEP_REF.search(it)
        fixes.append({"n": n, "text": it, "new": list(dict.fromkeys(NEW_ID.findall(it))),
                      "old": [int(x) for x in dict.fromkeys(re.findall(r"(?<![\w&])#(\d+)\b", it))],
                      "step": step.group(1) if step else ""})
    issues = []
    for it in items(sec.get("issues", [])):
        m = re.match(r"\W*#?NEW-(S?\d+)\b[\s:.)\-–—]*(.*)$", it)
        if m:
            title = re.split(r"(?<=[.])\s", m.group(2).strip())[0].strip()
            issues.append({"key": m.group(1), "title": re.sub(r"\s*\(`[^)]*\)\s*$", "", title)[:200], "behaviours": BEHAVIOUR.findall(it), "text": it})
    body = "\n".join(sec.get("questions", [])).strip()
    questions = [] if re.fullmatch(r"\W*none\W*", body, re.I) else items(sec.get("questions", []))
    evidence = [(int(m.group(1)), it) for it in items(sec.get("evidence", [])) if (m := re.match(r"\W*#(\d+)\b", it))]
    return {"sections": set(sec), "fixes": fixes, "issues": issues, "questions": questions, "evidence": evidence,
            "has_question_text": bool(body)}


def check(text: str) -> list[str]:
    """The faults of a report, each named by its heading or fix number; [] is a report the approve may read."""
    p = parse(text)
    bad = [f"missing the `## {LABEL[k]}` section" for k in REQUIRED if k not in p["sections"]]
    if "issues" in p["sections"] and not p["issues"]:
        bad.append("the Issues to file list has no `NEW-n title` item")
    if "questions" in p["sections"] and not p["questions"] and not re.search(r"\bnone\b", "\n".join(sections(text)["questions"]), re.I):
        bad.append("Open questions has no numbered question and does not say `none`")
    keys = [i["key"] for i in p["issues"]]
    for prefix in ("", "S"):
        nums = [int(k[len(prefix):]) for k in keys if k.startswith("S") == bool(prefix)]
        if nums != list(range(1, len(nums) + 1)):
            bad.append(f"the Issues list's NEW-{prefix}n run is {nums}: it must be 1..{len(nums)} with no gap or repeat")
    if "fixes" in p["sections"] and not p["fixes"]:
        bad.append("Ranked fixes has no numbered item")
    for f in p["fixes"]:
        if not f["new"] and not f["old"]:
            bad.append(f"ranked fix {f['n']} cites no issue (`NEW-n` or `#N`)")
        for k in f["new"]:
            if k not in keys:
                bad.append(f"ranked fix {f['n']} cites NEW-{k}, which the Issues list does not have")
    return bad


def worktree_of(repo_dir, area: str) -> Path:
    """The review worktree: wt-review-<area> under the checkout's harness.toml [jail].workroot."""
    import tomllib

    workroot = tomllib.loads((Path(repo_dir) / "harness.toml").read_text()).get("jail", {}).get("workroot")
    if not workroot:
        raise ValueError("harness.toml has no [jail].workroot")
    return Path(workroot) / f"wt-review-{area}"


def report_of(repo_dir, area: str, report=None) -> Path:
    return Path(report) if report else worktree_of(repo_dir, area) / f"review-{area}.md"


def main(a) -> int:
    if a.action == "check":
        f = report_of(a.repo_dir, a.area, a.report)
        try:
            bad = check(f.read_text())
        except OSError as e:
            print(f"REFUSED: no report to read: {e}")
            return 1
        for b in bad:
            print(f"REFUSED: {b}")
        print(f"report {f}: {'REFUSED, ' + str(len(bad)) + ' fault(s)' if bad else 'ok'}")
        return 1 if bad else 0
    print(f"REFUSED: review {a.action} is not built yet")
    return 1
