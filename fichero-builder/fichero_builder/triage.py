"""`builder triage [--labels] [--specs] [--milestones] [--dry]`: the repo's GitHub metadata cleaned up deterministically, changed directly
(owner ruling 2026-11-01: no proposals file, no manual approval), every change one journal row (event `triage`) and one `gh`
call that can be read back (dev-workflows.tool.triage, Step 2.5). `--dry` reads, prints and journals rows marked dry, writes nothing."""
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
import tomllib
from pathlib import Path

from fichero_builder import journal

KEEP_PREFIXES = ("spec:", "step:", "type:")
KEEP = {"needs-your-decision", "needs-your-test", "needs-spec", "status:blocked"}
SPECS = Path("docs/contributor_manual/specs")


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
    """Every spec file: specs/<area>/<slug>.md (the top-level templates and plans are not specs)."""
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
    """harness.toml [triage.labels]: old label -> kept label; a label absent from the table maps to nothing."""
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    m = doc.get("triage", {}).get("labels", {})
    if not all(isinstance(v, str) for v in m.values()):
        raise Refused("harness.toml [triage.labels]: every value must be a label name or \"\"")
    return m


def kept(name: str) -> bool:
    return name in KEEP or name.startswith(KEEP_PREFIXES)


class Triage:
    def __init__(self, root, gh: str, dry: bool, say=print):
        self.root, self.gh, self.dry, self.say = Path(root), gh, dry, say
        self.counts = {"labels created": 0, "labels deleted": 0, "issues relabelled": 0, "issues moved": 0, "milestones created": 0, "milestones closed": 0, "spec issues filed": 0, "spec lines added": 0}

    def change(self, what: str, *gh_args, **row) -> None:
        """One change = one row and (unless dry) one gh call."""
        journal.append("triage", what=what, dry=self.dry, **row)
        if not self.dry:
            _gh(self.gh, *gh_args)

    def issues(self, *filters) -> list[dict]:
        rows = json.loads(_gh(self.gh, "issue", "list", *filters, "--limit", "5000", "--json", "number,title,state,labels,milestone") or "[]")
        for r in rows:
            r["labels"] = [lb["name"] if isinstance(lb, dict) else str(lb) for lb in r.get("labels", [])]
            r["state"] = str(r.get("state", "")).lower()  # gh says OPEN / CLOSED
            r["milestone"] = (r.get("milestone") or {}).get("title") if isinstance(r.get("milestone"), dict) else r.get("milestone")
        return rows

    def labels(self) -> None:
        """Rule 1: the kept families only; spec:<stem> follows the spec files; every other label is moved by the table, then deleted."""
        have = {r["name"] for r in json.loads(_gh(self.gh, "label", "list", "--json", "name", "--limit", "1000") or "[]")}
        want = {f"spec:{p.stem}" for p in spec_files(self.root)}
        for name in sorted(want - have):
            self.change("label-create", "label", "create", name, label=name)
            self.counts["labels created"] += 1
        table = mapping(self.root)
        for old in sorted(have):
            if kept(old) and not (old.startswith("spec:") and old not in want):
                continue
            new = table.get(old, "")
            self.say(f"{old} -> {new or '(nothing)'}")
            if new:
                for i in self.issues("--label", old, "--state", "all"):
                    if new not in i["labels"]:
                        self.change("relabel", "issue", "edit", str(i["number"]), "--add-label", new, issue=i["number"], label=new, was=old)
                        self.counts["issues relabelled"] += 1
            self.change("label-delete", "label", "delete", old, "--yes", label=old)
            self.counts["labels deleted"] += 1

    def specs(self) -> None:
        """Rule 2: an open issue with no spec: label gets the label of every spec that cites `#N`, else needs-spec."""
        texts = {f"spec:{p.stem}": p.read_text() for p in spec_files(self.root)}
        for i in self.issues("--state", "open"):
            if any(lb.startswith("spec:") for lb in i["labels"]):
                continue
            pat = re.compile(rf"#{i['number']}\b")
            found = sorted(lb for lb, t in texts.items() if pat.search(t)) or ["needs-spec"]
            for lb in found:
                if lb not in i["labels"]:
                    self.change("relabel", "issue", "edit", str(i["number"]), "--add-label", lb, issue=i["number"], label=lb, was="")
                    self.counts["issues relabelled"] += 1


    def milestones(self) -> None:
        """Rules 3 and 4: an issue follows its spec's `> Milestone:`; a spec with no line gets the milestone most of its cited
        issues carry; a spec-less bug goes to Next release; an empty milestone closes; a milestone no spec names gets one
        `spec: write <milestone> spec` issue (needs-spec)."""
        files = spec_files(self.root)
        issues = self.issues("--state", "all")
        by_num = {i["number"]: i for i in issues}
        ms = json.loads(_gh(self.gh, "api", f"{API}?state=open&per_page=100") or "[]")
        titles = {m["title"] for m in ms}

        def ensure(title: str) -> None:
            if title not in titles:
                self.change("milestone-create", "api", "-X", "POST", API, "-f", f"title={title}", milestone=title)
                self.counts["milestones created"] += 1
                titles.add(title)

        named: dict[str, str] = {}  # spec label -> milestone
        for p in files:
            text = p.read_text()
            title = spec_milestone(text)
            if not title:
                cited = [c for c in (by_num[int(n)].get("milestone") for n in re.findall(r"#(\d+)\b", text) if int(n) in by_num) if c]
                if not cited:
                    self.say(f"{p.name}: no `> Milestone:` line and no cited issue carries one; left alone")
                    continue
                title = Counter(cited).most_common(1)[0][0]
                journal.append("triage", what="spec-milestone-line", dry=self.dry, spec=p.as_posix(), milestone=title)
                self.counts["spec lines added"] += 1
                if not self.dry:
                    head, _, rest = text.partition("\n")
                    p.write_text(f"{head}\n\n> Milestone: {title}\n{rest.lstrip(chr(10))}")
            named[f"spec:{p.stem}"] = title
        for i in issues:
            if i["state"] != "open":
                continue
            cur = i.get("milestone")
            want = next((named[lb] for lb in i["labels"] if lb in named), "")
            if not want and not cur and "type:bug" in i["labels"]:
                want = "Next release"
            if want and want != cur:
                ensure(want)
                self.change("move", "issue", "edit", str(i["number"]), "--milestone", want, issue=i["number"], milestone=want, was=cur or "")
                self.counts["issues moved"] += 1
        spec_named = set(named.values())
        if not self.dry:  # the counts after the moves above, not before
            ms = json.loads(_gh(self.gh, "api", f"{API}?state=open&per_page=100") or "[]")
        for m in ms:
            if m["open_issues"] == 0:
                self.change("milestone-close", "api", "-X", "PATCH", f"{API}/{m['number']}", "-f", "state=closed", milestone=m["title"])
                self.counts["milestones closed"] += 1
            elif m["title"] not in spec_named and m["title"] != "Next release":
                title = f"spec: write {m['title']} spec"
                if not any(i["title"] == title and i["state"] == "open" for i in issues):
                    self.change("spec-issue", "issue", "create", "--milestone", m["title"], "--title", title, "--label", "needs-spec",
                                "--body", f"The milestone {m['title']} has open issues and no spec names it. Write the spec first (owner ruling 2026-11-01).",
                                milestone=m["title"], title=title)
                    self.counts["spec issues filed"] += 1


def main(a) -> int:
    t = Triage(a.root, a.gh, a.dry)
    try:
        if a.labels:
            t.labels()
        if a.specs:
            t.specs()
        if a.milestones:
            t.milestones()
    except (Refused, OSError, ValueError) as e:
        print(f"REFUSED: {e}")
        return 1
    print(("DRY: " if a.dry else "") + ", ".join(f"{k}: {v}" for k, v in t.counts.items()))
    return 0
