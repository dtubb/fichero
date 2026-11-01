"""`builder triage [--labels] [--specs] [--dry]`: the repo's GitHub metadata cleaned up deterministically, changed directly
(owner ruling 2026-11-01: no proposals file, no manual approval), every change one journal row (event `triage`) and one `gh`
call that can be read back (dev-workflows.tool.triage, Step 2.5). `--dry` reads, prints and journals rows marked dry, writes nothing."""
from __future__ import annotations

import json
import re
import subprocess
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
        self.counts = {"labels created": 0, "labels deleted": 0, "issues relabelled": 0}

    def change(self, what: str, *gh_args, **row) -> None:
        """One change = one row and (unless dry) one gh call."""
        journal.append("triage", what=what, dry=self.dry, **row)
        if not self.dry:
            _gh(self.gh, *gh_args)

    def issues(self, *filters) -> list[dict]:
        rows = json.loads(_gh(self.gh, "issue", "list", *filters, "--limit", "1000", "--json", "number,title,state,labels") or "[]")
        for r in rows:
            r["labels"] = [lb["name"] if isinstance(lb, dict) else str(lb) for lb in r.get("labels", [])]
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


def main(a) -> int:
    t = Triage(a.root, a.gh, a.dry)
    try:
        if a.labels:
            t.labels()
        if a.specs:
            t.specs()
    except (Refused, OSError, ValueError) as e:
        print(f"REFUSED: {e}")
        return 1
    print(("DRY: " if a.dry else "") + ", ".join(f"{k}: {v}" for k, v in t.counts.items()))
    return 0
