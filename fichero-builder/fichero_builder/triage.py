"""`builder triage [--labels] [--specs] [--milestones] [--assignees] [--order] [--dry]`: the repo's GitHub metadata cleaned up
deterministically, changed directly (owner ruling 2026-11-01: no proposals file, no manual approval), every change one journal
row (event `triage`) and one `gh` call that can be read back (dev-workflows.tool.triage, Step 2.5; the rules are the
issues-and-labels spec's). `--dry` reads, prints and journals rows marked dry, writes nothing.

The milestone is the spec: an issue sits in the milestone of the spec that cites it; a `spec:*` label is a temporary hint
(the labels table maps an old area label onto one) that goes once the issue sits in its spec's milestone. The label set is
closed: step:N.M, type:bug|feature|task, priority:P0-P3, phase:R0-R6 (kept until the recipe phases are in a build order),
needs-spec, needs-your-decision, needs-your-test, status:blocked. `docs/contributor_manual/specs/build-order.md` is the
owner's: `--order` reads it and proposes lines for milestones it lacks, never writes it."""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from collections import Counter
import tomllib
from pathlib import Path

from fichero_builder import journal

KEPT = re.compile(r"^(step:\d+\.\d+|type:(bug|feature|task)|priority:P[0-3]|phase:R[0-6]|needs-spec|needs-your-decision|needs-your-test|status:blocked)$")
OWNER_LABELS = ("needs-your-decision", "needs-your-test")
SPECS = Path("docs/contributor_manual/specs")
BUILD_ORDER = SPECS / "build-order.md"
OPS_BUCKETS = ("Bugs - ", "Lint - ", "Performance - ")       # worked by bug and priority, never as a lane: no spec is owed
GRAB_BAGS = ("Next release", "cand 16")                     # triage files their issues into spec milestones; they empty out


class Refused(Exception):
    pass


def _gh(gh: str, *args) -> str:
    try:
        r = subprocess.run([gh, *args], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise Refused(f"gh {' '.join(args[:2])} timed out") from None
    if r.returncode:
        raise Refused(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[-300:]}")
    return r.stdout


def spec_files(root) -> list[Path]:
    """Every spec file: specs/<area>/<slug>.md (the top-level templates, plans and the build order are not specs)."""
    return sorted(p for p in (Path(root) / SPECS).glob("*/*.md") if not p.name.startswith("_"))


MILESTONE_LINE = re.compile(r"^> Milestone: (.+?)\s*$", re.M)
API = "repos/{owner}/{repo}/milestones"


def spec_milestone(text: str) -> str:
    """The title on the `> Milestone:` line, cut at the first sentence end or `;` (some lines carry prose after the title);
    '' when there is no line or what is left is not a plain title (a backtick, a bracket)."""
    m = MILESTONE_LINE.search(text)
    if not m:
        return ""
    title = re.split(r"\. |; ", m.group(1), 1)[0].strip().rstrip(".")
    return "" if re.search(r"[`()\[\]]", title) else title


def mapping(root) -> dict[str, str]:
    """harness.toml [triage.labels]: old label -> kept label (or a spec:<stem> hint); a label absent from the table maps to nothing."""
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    m = doc.get("triage", {}).get("labels", {})
    if not all(isinstance(v, str) for v in m.values()):
        raise Refused("harness.toml [triage.labels]: every value must be a label name or \"\"")
    return m


def kept(name: str) -> bool:
    return bool(KEPT.match(name))


def is_ops(title: str) -> bool:
    return title.startswith(OPS_BUCKETS) or title in GRAB_BAGS


ORDER_LINE = re.compile(r"^\d+\.\s+`([^`]+)`(?:.*?\bSpec:\s*(\S+))?", re.M)


def build_order(root) -> tuple[list[tuple[str, str]], set[str]]:
    """([(milestone, spec path or '')] under `## In order`, {parked milestones}); Refused when the file is missing."""
    p = Path(root) / BUILD_ORDER
    if not p.is_file():
        raise Refused(f"no build-order file at {BUILD_ORDER}")
    text = p.read_text()
    ordered = text.split("## In order", 1)[1].split("\n## ", 1)[0] if "## In order" in text else ""
    parked = text.split("## Parked", 1)[1] if "## Parked" in text else ""
    return [(m.group(1), m.group(2) or "") for m in ORDER_LINE.finditer(ordered)], set(re.findall(r"`([^`]+)`", parked))


def matches(title: str, names: set[str]) -> bool:
    """A build-order line names a milestone exactly or by pattern (`UX - *`, fnmatch)."""
    return any(fnmatch.fnmatchcase(title, n) for n in names)


def listed(root) -> set[str]:
    """Every milestone the file names anywhere below `## In order`: ordered, under `## Then`, or parked."""
    text = (Path(root) / BUILD_ORDER).read_text()
    return set(re.findall(r"`([^`]+)`", text.split("## In order", 1)[-1]))


def first_open(root, gh: str = "gh") -> tuple[str, Path]:
    """The first milestone under `## In order` that still has open issues, with its spec file (rule 5: `builder milestone`
    and the queue take it when no milestone is named)."""
    for title, spec in build_order(root)[0]:
        if json.loads(_gh(gh, "issue", "list", "--milestone", title, "--state", "open", "--limit", "1", "--json", "number") or "[]"):
            return title, Path(root) / SPECS / spec
    raise Refused("every ordered milestone in the build-order file is finished")


class Triage:
    def __init__(self, root, gh: str, dry: bool, say=print):
        self.root, self.gh, self.dry, self.say = Path(root), gh, dry, say
        self.counts = {"labels created": 0, "labels unknown": 0, "issues relabelled": 0, "issues moved": 0, "milestones created": 0, "milestones closed": 0,
                       "spec issues filed": 0, "spec lines added": 0, "assignees changed": 0, "milestones unordered": 0}

    def change(self, what: str, *gh_args, **row) -> None:
        """One change = one row and (unless dry) one gh call."""
        journal.append("triage", what=what, dry=self.dry, **row)
        if not self.dry:
            _gh(self.gh, *gh_args)

    def issues(self, *filters) -> list[dict]:
        rows = json.loads(_gh(self.gh, "issue", "list", *filters, "--limit", "5000", "--json", "number,title,state,labels,milestone,assignees") or "[]")
        for r in rows:
            r["labels"] = [lb["name"] if isinstance(lb, dict) else str(lb) for lb in r.get("labels", [])]
            r["assignees"] = [a["login"] if isinstance(a, dict) else str(a) for a in r.get("assignees") or []]
            r["state"] = str(r.get("state", "")).lower()  # gh says OPEN / CLOSED
            r["milestone"] = (r.get("milestone") or {}).get("title") if isinstance(r.get("milestone"), dict) else r.get("milestone")
        return rows

    def relabel(self, i: dict, add: str = "", remove: str = "", was: str = "") -> None:
        flag, lb = ("--add-label", add) if add else ("--remove-label", remove)
        self.change("relabel", "issue", "edit", str(i["number"]), flag, lb, issue=i["number"], label=lb, was=was, removed=bool(remove))
        self.counts["issues relabelled"] += 1

    def citations(self) -> dict[Path, set[int]]:
        return {p: {int(n) for n in re.findall(r"#(\d+)\b", p.read_text())} for p in spec_files(self.root)}

    def labels(self) -> None:
        """Rule 1: the closed set only. A label outside it (a spec:* label with a file is a hint --milestones consumes, so it stays
        quiet) is reported, one row each, and its issues get what the table maps it to; it is never deleted, because the spec
        says triage refuses an unknown label and a delete on the public repo is not undone."""
        have = {r["name"] for r in json.loads(_gh(self.gh, "label", "list", "--json", "name", "--limit", "1000") or "[]")}
        stems = {f"spec:{p.stem}" for p in spec_files(self.root)}
        table = mapping(self.root)
        for old in sorted(have):
            if kept(old) or old in stems:
                continue
            new = table.get(old, "")
            if new.startswith("spec:") and new not in have:  # triage makes no spec label; the citing spec still places the issue
                self.say(f"{old} -> {new} is absent: no hint applied")
                new = ""
            self.say(f"unknown label {old} -> {new or '(nothing)'}")
            journal.append("triage", what="label-unknown", dry=self.dry, label=old, maps_to=new)
            self.counts["labels unknown"] += 1
            if new and new not in have:
                self.change("label-create", "label", "create", new, label=new)
                have.add(new)
                self.counts["labels created"] += 1
            if new:
                for i in self.issues("--label", old, "--state", "all"):
                    if new not in i["labels"]:
                        self.relabel(i, add=new, was=old)

    def specs(self) -> None:
        """Rule 2: needs-spec only on an open issue inside a spec's milestone that no spec cites; an issue a spec cites loses it;
        ops buckets, grab-bags and issues with no milestone are left alone."""
        cited = set().union(*self.citations().values())
        spec_ms = {spec_milestone(p.read_text()) for p in spec_files(self.root)} - {""}
        for i in self.issues("--state", "open"):
            if i["number"] in cited and "needs-spec" in i["labels"]:
                self.relabel(i, remove="needs-spec")
            elif i["number"] not in cited and i.get("milestone") in spec_ms and "needs-spec" not in i["labels"]:
                self.relabel(i, add="needs-spec")

    def milestones(self) -> None:
        """Rules 3 and 4: an open issue goes to the milestone of the spec that cites it (it stays in its current milestone
        when that milestone's spec is among the citing ones; else the first citing spec by path), else of the spec a spec:* hint label
        names; the hint goes once the issue sits there; a spec with no `> Milestone:` line gets the milestone most of its
        cited issues carry; a spec-less bug with no milestone goes to Next release; an empty milestone closes; a milestone
        no spec names (not an ops bucket, a grab-bag or one parked in the build-order file, by name or pattern) gets one
        `spec: write <milestone> spec` issue (needs-spec)."""
        issues = self.issues("--state", "all")
        by_num = {i["number"]: i for i in issues}
        every = json.loads(_gh(self.gh, "api", f"{API}?state=all&per_page=100", "--paginate") or "[]")
        ms = [m for m in every if m.get("state") != "closed"]
        titles = {m["title"] for m in ms}
        closed = {m["title"]: m["number"] for m in every if m.get("state") == "closed"}

        def ensure(title: str) -> None:
            if title in closed:  # GitHub refuses a second milestone of one title, open or closed
                self.change("milestone-reopen", "api", "-X", "PATCH", f"{API}/{closed.pop(title)}", "-f", "state=open", milestone=title)
                titles.add(title)
            elif title not in titles:
                self.change("milestone-create", "api", "-X", "POST", API, "-f", f"title={title}", milestone=title)
                self.counts["milestones created"] += 1
                titles.add(title)

        named: dict[str, str] = {}  # spec label -> milestone
        cites: dict[int, list[str]] = {}  # issue -> the milestones of the specs that cite it, in path order
        for p, nums in self.citations().items():
            text = p.read_text()
            title = spec_milestone(text)
            if not title:
                carried = [c for c in (by_num[n].get("milestone") for n in sorted(nums) if n in by_num) if c]
                if not carried:
                    self.say(f"{p.name}: no `> Milestone:` line and no cited issue carries one; left alone")
                    continue
                title = Counter(carried).most_common(1)[0][0]
                journal.append("triage", what="spec-milestone-line", dry=self.dry, spec=p.as_posix(), milestone=title)
                self.counts["spec lines added"] += 1
                if not self.dry:
                    head, _, rest = text.partition("\n")
                    p.write_text(f"{head}\n\n> Milestone: {title}\n{rest.lstrip(chr(10))}")
            named[f"spec:{p.stem}"] = title
            for n in nums:
                cites.setdefault(n, []).append(title)
        for i in issues:
            if i["state"] != "open":
                continue
            cur = i.get("milestone")
            citing = cites.get(i["number"], [])  # its current milestone's spec cites it: it stays; else the first citing spec
            want = (cur if cur in citing else citing[0]) if citing else next((named[lb] for lb in i["labels"] if lb in named), "")
            if not want and not cur and "type:bug" in i["labels"]:
                want = "Next release"
            if want and want != cur:
                ensure(want)
                self.change("move", "issue", "edit", str(i["number"]), "--milestone", want, issue=i["number"], milestone=want, was=cur or "")
                self.counts["issues moved"] += 1
                cur = want
            for lb in i["labels"]:  # the hint has served (or the citing spec overrules it): the milestone says it now
                if lb.startswith("spec:") and (named.get(lb) == cur or cur in cites.get(i["number"], [])):
                    self.relabel(i, remove=lb)
                    i["labels"] = [x for x in i["labels"] if x != lb]
        spec_named = set(named.values())
        try:
            parked = build_order(self.root)[1]  # a parked milestone is the owner's to leave: no spec is owed
        except Refused:
            parked = set()
        if not self.dry:  # the counts after the moves above, not before
            ms = json.loads(_gh(self.gh, "api", f"{API}?state=open&per_page=100", "--paginate") or "[]")
        for m in ms:
            if m["open_issues"] == 0 and m["title"] not in spec_named:  # a spec's milestone stays, empty or not
                self.change("milestone-close", "api", "-X", "PATCH", f"{API}/{m['number']}", "-f", "state=closed", milestone=m["title"])
                self.counts["milestones closed"] += 1
            elif m["title"] not in spec_named and not is_ops(m["title"]) and not matches(m["title"], parked):
                title = f"spec: write {m['title']} spec"
                if not any(i["title"] == title and i["state"] == "open" for i in issues):
                    self.change("spec-issue", "issue", "create", "--milestone", m["title"], "--title", title, "--label", "needs-spec",
                                "--body", f"The milestone {m['title']} has open issues and no spec names it. Write the spec first (owner ruling 2026-11-01).",
                                milestone=m["title"], title=title)
                    self.counts["spec issues filed"] += 1

    def assignees(self) -> None:
        """Rule 6: the gh login is assigned on needs-your-decision / needs-your-test and nowhere else; every other assignee goes."""
        me = _gh(self.gh, "api", "user", "--jq", ".login").strip()
        for i in self.issues("--state", "open"):
            want = {me} if any(lb in OWNER_LABELS for lb in i["labels"]) else set()
            for login in sorted(set(i["assignees"]) - want):
                self.change("assignee", "issue", "edit", str(i["number"]), "--remove-assignee", login, issue=i["number"], login=login, set=False)
                self.counts["assignees changed"] += 1
            for login in sorted(want - set(i["assignees"])):
                self.change("assignee", "issue", "edit", str(i["number"]), "--add-assignee", login, issue=i["number"], login=login, set=True)
                self.counts["assignees changed"] += 1

    def order(self) -> None:
        """Rule 5: the build-order file is read; an open milestone with open issues it neither orders nor parks is printed as a
        proposed line (and one row); the file is never written."""
        try:
            build_order(self.root)  # says so when the file is missing
            placed = listed(self.root)
        except Refused as e:
            self.say(str(e))
            placed = set()
        specs = {spec_milestone(p.read_text()): p.relative_to(self.root / SPECS).as_posix() for p in spec_files(self.root)}
        missing = [m for m in json.loads(_gh(self.gh, "api", f"{API}?state=open&per_page=100", "--paginate") or "[]") if m["open_issues"] and not matches(m["title"], placed)]
        if missing:
            self.say(f"proposed for {BUILD_ORDER} (under `## Then`; the owner orders them):")
        for m in sorted(missing, key=lambda m: m["title"]):
            spec = specs.get(m["title"], "")
            self.say(f"+ `{m['title']}` — {m['open_issues']} open. Spec: {spec or '(none: an ops bucket, or a spec to write)'}")
            journal.append("triage", what="order-missing", dry=self.dry, milestone=m["title"], spec=spec, open=m["open_issues"])
            self.counts["milestones unordered"] += 1


def main(a) -> int:
    t = Triage(a.root, a.gh, a.dry)
    try:
        if a.labels:
            t.labels()
        if a.specs:
            t.specs()
        if a.milestones:
            t.milestones()
        if a.assignees:
            t.assignees()
        if a.order:
            t.order()
    except (Refused, OSError, ValueError) as e:
        print(f"REFUSED: {e}")
        return 1
    print(("DRY: " if a.dry else "") + ", ".join(f"{k}: {v}" for k, v in t.counts.items()))
    return 0
