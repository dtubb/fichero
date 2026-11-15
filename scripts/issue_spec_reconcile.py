#!/usr/bin/env python3
"""Reconcile open GitHub issues against the spec and the commit log, deterministically.

Ownership: a spec behaviour bullet owns an issue only through the (#N) right after its own
first-line status tag, e.g.  - `id` — **[OK]** (#10) text   or   (#10, #11; …).
A '#N' anywhere else (prose, '-> #N' further down) owns nothing; an untagged bullet owns nothing.

Commit evidence: a commit on the ref whose subject or body says 'Fixes #N' or 'Closes #N'
(not 'Part of #N') is fix evidence for N.

Decision per open issue N:
  CLOSE-A       owning bullets all [OK]; the tests they name exist on the ref.
  CLOSE-B       no owning bullet non-OK, no owning bullet names a missing test, and a fix
                commit says Fixes/Closes #N (also when N has no owning bullet at all).
  KEEP          an owning bullet is not [OK] (milestone set to that spec's `> Milestone:`),
                or an [OK] owning bullet names no test and there is no fix commit.
  MISSING-TEST  owning bullets all [OK] but name a test not defined on the ref. Never closed.
  NO-SPEC       no owning bullet and no fix commit.

Dry run is the default and writes a TSV. `--apply --tsv PATH` applies the CLOSE comments and
closes and the KEEP milestone edits from that reviewed TSV.

Run:
    scripts/issue_spec_reconcile.py --tsv agent-work/status/briefs/issue-reconcile.tsv
    scripts/issue_spec_reconcile.py --apply --tsv agent-work/status/briefs/issue-reconcile.tsv
    scripts/issue_spec_reconcile.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

REPO = "dtubb/fichero"
SPEC_ROOT = "docs/contributor_manual/specs"
DEFAULT_REF = "origin/integration"

BEHAVIOR_START_RE = re.compile(r"^(\s*)-\s+`([a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+)`")
TAG_RE = re.compile(r"\*\*\[([A-Z][A-Z/]*)[^\]]*\]\*\*")
OWNER_AFTER_TAG_RE = re.compile(r"\s*\(([^)]*)\)")
ISSUE_CITE_RE = re.compile(r"#(\d+)\b")
FIX_RE = re.compile(r"\b(?:Fixes|Closes)\s+#(\d+)\b", re.IGNORECASE)
PY_TEST_FILE_RE = re.compile(r"[\w./-]+/test_[\w]+\.py")
TEST_NAME_RE = re.compile(r"\btest_[A-Za-z0-9_]+\b")
MILESTONE_RE = re.compile(r"^>\s*Milestone:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class Bullet:
    spec: str
    milestone: str | None
    behavior_id: str
    tag: str  # OK, PARTIAL, GAP, ... or UNTAGGED
    owned: set[int]  # issues this bullet owns (the (#N) after its own tag only)
    tests: set[str]  # test names and test file paths named anywhere in the bullet


@dataclass
class Row:
    number: int
    cls: str
    spec_ids: list[str] = field(default_factory=list)
    milestone: str = ""
    missing_tests: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    note: str = ""


def parse_bullets(spec: str, text: str) -> list[Bullet]:
    """Every behaviour bullet in one spec file. Ownership comes only from the first line."""
    m = MILESTONE_RE.search(text)
    milestone = m.group(1).strip() if m else None
    out: list[Bullet] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        start = BEHAVIOR_START_RE.match(lines[i])
        if not start:
            i += 1
            continue
        indent = len(start.group(1))
        body = [lines[i]]
        j = i + 1
        while j < len(lines) and lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) > indent:
            body.append(lines[j])
            j += 1
        blob = "\n".join(body)
        tag_m = TAG_RE.search(lines[i])
        owned: set[int] = set()
        if tag_m:
            after = OWNER_AFTER_TAG_RE.match(lines[i], tag_m.end())
            if after:
                owned = {int(n) for n in ISSUE_CITE_RE.findall(after.group(1))}
        tests = set(TEST_NAME_RE.findall(blob)) | set(PY_TEST_FILE_RE.findall(blob))
        out.append(Bullet(spec, milestone, start.group(2), tag_m.group(1) if tag_m else "UNTAGGED",
                          owned, tests))
        i = j
    return out


def fix_commits(log: str) -> dict[int, list[str]]:
    """issue -> short shas of commits saying Fixes/Closes #N. `log` is records of `sha US subject US body RS`."""
    fixes: dict[int, list[str]] = {}
    for rec in log.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) < 3 or not parts[0].strip():
            continue
        sha, subject, body = parts[0].strip(), parts[1], parts[2]
        for n in sorted({int(x) for x in FIX_RE.findall(subject + "\n" + body)}):
            fixes.setdefault(n, []).append(sha[:9])
    return fixes


def classify(number: int, bullets: list[Bullet], missing_on_ref: set[str], commits: list[str]) -> Row:
    """The decision for one open issue. Pure: the ref and the commit log are read by the caller."""
    owning = [b for b in bullets if number in b.owned]
    spec_ids = [f"{b.behavior_id} [{b.tag}] ({b.spec})" for b in owning]
    if not owning:
        if commits:
            return Row(number, "CLOSE-B", commits=commits, note="fix commit; no owning spec line")
        return Row(number, "NO-SPEC", note="no owning spec line and no fix commit")
    non_ok = [b for b in owning if b.tag != "OK"]
    if non_ok:
        ms = next((b.milestone for b in non_ok if b.milestone), "")
        return Row(number, "KEEP", spec_ids, ms, commits=commits,
                   note=f"{len(non_ok)} owning line(s) not OK")
    named = set().union(*(b.tests for b in owning))
    missing = sorted(t for t in named if t in missing_on_ref)
    if missing:
        return Row(number, "MISSING-TEST", spec_ids, missing_tests=missing, commits=commits,
                   note="an OK line names a test not on the ref")
    if named:
        return Row(number, "CLOSE-A", spec_ids, commits=commits, note=f"{len(named)} test name(s) found")
    if commits:
        return Row(number, "CLOSE-B", spec_ids, commits=commits, note="OK line names no test; fix commit")
    ms = next((b.milestone for b in owning if b.milestone), "")
    return Row(number, "KEEP", spec_ids, ms, note="every owning line is OK but names no test; no fix commit")


# ---- git / gh I/O (not exercised by the self-test) -------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def load_specs(ref: str) -> list[tuple[str, str]]:
    out = []
    for p in _git("ls-tree", "-r", "--name-only", ref, "--", SPEC_ROOT).split():
        if p.endswith(".md") and not p.endswith(("_TEMPLATE.md", "_MILESTONE_TEMPLATE.md")):
            out.append((p, _git("show", f"{ref}:{p}")))
    return out


def load_fixes(ref: str) -> dict[int, list[str]]:
    return fix_commits(_git("log", ref, "--format=%H%x1f%s%x1f%b%x1e"))


def test_missing_on_ref(ref: str, names: set[str]) -> set[str]:
    tree = _git("ls-tree", "-r", "--name-only", ref).split("\n")
    missing = set()
    for name in sorted(names):
        if name.endswith(".py"):
            ok = name in tree or any(p.endswith("/" + name) for p in tree)
        else:
            pat = rf"(def|func) {re.escape(name)}\b"
            ok = subprocess.run(["git", "grep", "-q", "-E", pat, ref, "--", ":!docs"],
                                capture_output=True, text=True).returncode == 0
        if not ok:
            missing.add(name)
    return missing


def open_issues() -> list[int]:
    out = subprocess.run(["gh", "issue", "list", "-R", REPO, "--state", "open", "--limit", "5000",
                          "--json", "number", "-q", ".[].number"], capture_output=True, text=True, check=True)
    return [int(x) for x in out.stdout.split()]


def write_tsv(path: str, rows: list[Row]) -> None:
    with open(path, "w") as f:
        f.write("number\tclass\tmilestone\tspec_ids\tmissing_tests\tcommits\tnote\n")
        for r in rows:
            f.write("\t".join([str(r.number), r.cls, r.milestone, "; ".join(r.spec_ids),
                               ", ".join(r.missing_tests), ", ".join(r.commits), r.note]) + "\n")


def read_tsv(path: str) -> list[Row]:
    rows = []
    with open(path) as f:
        next(f)
        for line in f:
            n, cls, ms, specs, miss, commits, note = line.rstrip("\n").split("\t")
            rows.append(Row(int(n), cls, [s for s in specs.split("; ") if s], ms,
                            [t for t in miss.split(", ") if t], [c for c in commits.split(", ") if c], note))
    return rows


def apply_rows(rows: list[Row]) -> dict[str, int]:
    counts = {"closed": 0, "kept-milestone": 0, "errors": 0}
    milestones = set(subprocess.run(
        ["gh", "api", f"repos/{REPO}/milestones", "--paginate", "-q", ".[].title"],
        capture_output=True, text=True, check=True).stdout.splitlines())
    for r in rows:
        if r.cls in ("CLOSE-A", "CLOSE-B"):
            lines = [f"- {s}" for s in r.spec_ids] or ["- (no owning spec line)"]
            head = "Closed by the deterministic spec/commit reconcile (2026-10-26).\n"
            commit_note = f"Fix commit(s) on origin/integration: {', '.join(r.commits)}.\n" if r.commits else ""
            tail = "\nTests named by those lines exist on origin/integration." if r.cls == "CLOSE-A" else ""
            body = head + commit_note + "Owning spec lines (all [OK]):\n" + "\n".join(lines) + tail
            c = subprocess.run(["gh", "issue", "comment", str(r.number), "-R", REPO, "-F", "-"],
                               input=body, capture_output=True, text=True)
            k = subprocess.run(["gh", "issue", "close", str(r.number), "-R", REPO],
                               capture_output=True, text=True)
            counts["closed" if c.returncode == 0 and k.returncode == 0 else "errors"] += 1
        elif r.cls == "KEEP" and r.milestone:
            if r.milestone not in milestones:
                counts["errors"] += 1
                continue
            e = subprocess.run(["gh", "issue", "edit", str(r.number), "-R", REPO, "--milestone", r.milestone],
                               capture_output=True, text=True)
            counts["kept-milestone" if e.returncode == 0 else "errors"] += 1
    return counts


# ---- link audit (report only; the safe milestone moves are applied by --link-apply) -----------

MANUAL_RE = re.compile(r"^>\s*Manual:\s*(.+?)\s*$", re.MULTILINE)
DOC_PATH_RE = re.compile(r"(docs/[\w./-]+\.md)")
BEHAVIOR_ID_RE = re.compile(r"`([a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+)`")


def spec_milestones(text: str) -> list[str]:
    """Milestone names from the header: drop '(...)' notes, split on ';', 'TBD' means none."""
    m = MILESTONE_RE.search(text)
    if not m:
        return []
    names = [part.strip() for part in re.sub(r"\s*\([^)]*\)", "", m.group(1)).split(";")]
    return [n for n in names if n and not n.upper().startswith("TBD")]


def manual_state(text: str, tree: set[str]) -> str:
    """OK (named page exists), MISSING-PAGE (named page absent), TBD (header says TBD), NONE (no header)."""
    m = MANUAL_RE.search(text)
    if not m:
        return "NONE"
    path = DOC_PATH_RE.search(m.group(1))
    if path:
        return "OK" if path.group(1) in tree else "MISSING-PAGE"
    return "TBD" if m.group(1).upper().startswith("TBD") else "PROSE"


def issue_data() -> dict[int, dict]:
    out = subprocess.run(["gh", "issue", "list", "-R", REPO, "--state", "open", "--limit", "5000",
                          "--json", "number,title,body,milestone"], capture_output=True, text=True, check=True)
    return {i["number"]: i for i in json.loads(out.stdout)}


def milestone_data() -> dict[str, dict]:
    out = subprocess.run(["gh", "api", f"repos/{REPO}/milestones?state=all", "--paginate", "-q", ".[]"],
                         capture_output=True, text=True, check=True)
    ms = [json.loads(line) for line in out.stdout.splitlines() if line.strip()]
    ms.sort(key=lambda m: m["state"] == "open")  # open last, so an open milestone wins a case-insensitive clash
    return {m["title"].lower(): m for m in ms}


def link_audit(ref: str) -> dict:
    specs = load_specs(ref)
    tree = set(_git("ls-tree", "-r", "--name-only", ref).split("\n"))
    issues = issue_data()
    mss = milestone_data()
    bullets = [b for path, text in specs for b in parse_bullets(path, text)]
    ids_by_issue: dict[int, list[Bullet]] = {}
    for b in bullets:
        for n in b.owned:
            ids_by_issue.setdefault(n, []).append(b)
    cited_any = {int(n) for _, t in specs for n in ISSUE_CITE_RE.findall(t)}
    known_ids = {b.behavior_id for b in bullets}
    res: dict = {}
    # 1. open issues citing no spec behaviour id (owned, cited in a spec, or naming a behaviour id)
    c1 = []
    for n, i in issues.items():
        named = known_ids & set(BEHAVIOR_ID_RE.findall((i["title"] or "") + "\n" + (i["body"] or "")))
        if n not in ids_by_issue and n not in cited_any and not named:
            c1.append(n)
    res["1-no-spec-link"] = sorted(c1)
    # 2. GAP/PARTIAL/BROKEN bullets with no open issue
    c2 = []
    for b in bullets:
        if b.tag in ("GAP", "PARTIAL", "BROKEN") and not (b.owned & set(issues)):
            hits = sorted(n for n, i in issues.items()
                          if b.behavior_id in ((i["title"] or "") + (i["body"] or "")))
            c2.append({"spec": b.spec, "id": b.behavior_id, "tag": b.tag, "owned": sorted(b.owned),
                       "proposal": hits, "evidence": f"open issue body names `{b.behavior_id}`" if hits else ""})
    res["2-nonok-no-open-issue"] = c2
    # 3. issue milestone != the milestone of the spec that owns it
    c3 = []
    for n, bs in ids_by_issue.items():
        if n not in issues:
            continue
        want = {m for b in bs for m in spec_milestones(next(t for p, t in specs if p == b.spec))}
        have = (issues[n]["milestone"] or {}).get("title", "")
        if not want or have in want:
            continue
        exact = [mss[w.lower()]["title"] for w in want if w.lower() in mss]
        safe = len(want) == 1 and len(exact) == 1 and not have
        c3.append({"number": n, "have": have, "want": sorted(want), "exists": bool(exact),
                   "safe": safe, "evidence": "; ".join(f"{b.behavior_id} ({b.spec})" for b in bs[:2])})
    res["3-milestone-mismatch"] = sorted(c3, key=lambda r: r["number"])
    # 4. specs with no milestone / unknown milestone / empty milestone
    c4 = []
    for path, text in specs:
        if path.rsplit("/", 1)[-1].startswith(("OPEN-", "SPEC-")) or not re.search(BEHAVIOR_START_RE.pattern, text, re.M):
            continue
        names = spec_milestones(text)
        if not names:
            c4.append({"spec": path, "problem": "no milestone header or TBD"})
            continue
        for n in names:
            m = mss.get(n.lower())
            if not m:
                c4.append({"spec": path, "problem": f"milestone '{n}' does not exist on GitHub"})
            elif m["open_issues"] + m["closed_issues"] == 0:
                c4.append({"spec": path, "problem": f"milestone '{n}' is empty"})
    res["4-spec-milestone"] = c4
    # 5. manual page missing (per spec; issues inherit through their owning bullets)
    c5 = []
    bad = {}
    for path, text in specs:
        if path.rsplit("/", 1)[-1].startswith(("OPEN-", "SPEC-")) or not re.search(BEHAVIOR_START_RE.pattern, text, re.M):
            continue
        st = manual_state(text, tree)
        if st != "OK":
            bad[path] = st
            c5.append({"spec": path, "manual": st})
    res["5-manual-page"] = c5
    res["5-issues-affected"] = sorted(n for n, bs in ids_by_issue.items() if n in issues
                                      and any(b.spec in bad for b in bs))
    return res


def link_apply(ref: str) -> dict[str, int]:
    """Only the safe moves: an open issue with NO milestone, owned by specs naming one existing milestone."""
    mss = milestone_data()
    counts = {"moved": 0, "errors": 0}
    for r in link_audit(ref)["3-milestone-mismatch"]:
        if not r["safe"]:
            continue
        num = mss[r["want"][0].lower()]["number"]
        e = subprocess.run(["gh", "api", "-X", "PATCH", f"repos/{REPO}/issues/{r['number']}", "-F", f"milestone={num}"],
                           capture_output=True, text=True)
        counts["moved" if e.returncode == 0 else "errors"] += 1
    return counts


RELEASE_SLOTS = re.compile(r"^(Next release|cand \d+|Later \(post-release\))$")


def link_apply_ruled(ref: str, log_path: str, dry: bool) -> dict[str, int]:
    """Owner's link-audit ruling: milestones, missing spec milestones, needs-spec label, behaviour comments.
    Every change is appended to `log_path` (issue, old, new). Never closes, never edits spec text."""
    import time
    audit = link_audit(ref)
    specs = dict(load_specs(ref))
    mss = milestone_data()
    log: list[dict] = []
    counts = {"milestone": 0, "skipped-release-slot": 0, "milestone-created": 0, "label": 0, "comment": 0, "errors": 0}

    def gh(*a: str, **kw) -> bool:
        if dry:
            return True
        time.sleep(0.4)
        return subprocess.run(["gh", *a], capture_output=True, text=True, **kw).returncode == 0

    # (4) milestones for specs that have none; named by the spec stem
    for r in audit["4-spec-milestone"]:
        stem = r["spec"].rsplit("/", 1)[-1][:-3]
        if "no milestone header" in r["problem"] and stem.lower() not in mss:
            ok = gh("api", f"repos/{REPO}/milestones", "-f", f"title={stem}", "-f", f"description=Spec: {r['spec']}")
            counts["milestone-created" if ok else "errors"] += 1
            log.append({"change": "milestone-create", "issue": None, "old": None, "new": stem})
    if not dry:
        mss = milestone_data()
    # (3) one owning spec, one milestone, differs from the issue's current one
    owners: dict[int, set[str]] = {}
    for path, text in specs.items():
        for b in parse_bullets(path, text):
            for n in b.owned:
                owners.setdefault(n, set()).add(path)
    cur = {n: (i["milestone"] or {}).get("title", "") for n, i in issue_data().items()}
    moves = []
    for n, paths in sorted(owners.items()):
        if n not in cur or len(paths) != 1:
            continue
        want = spec_milestones(specs[next(iter(paths))])
        if len(want) != 1 or want[0].lower() not in mss:
            continue
        m = mss[want[0].lower()]
        if m["state"] != "open" or cur[n] == m["title"]:
            continue
        if RELEASE_SLOTS.match(cur[n]):
            counts["skipped-release-slot"] += 1
            continue
        # sample check 2026-10-26 was 6/10: only leave a closed milestone; moves between live ones wait for the manager
        live = mss.get(cur[n].lower(), {})  # exact title too: "Workflows" (closed) clashes with "workflows" (open)
        if cur[n] and live.get("state") == "open" and live.get("title") == cur[n]:
            counts["held-live-milestone"] = counts.get("held-live-milestone", 0) + 1
            continue
        moves.append((n, cur[n], m["title"], m["number"]))
    for n, old, new, num in moves:
        ok = gh("api", "-X", "PATCH", f"repos/{REPO}/issues/{n}", "-F", f"milestone={num}")
        counts["milestone" if ok else "errors"] += 1
        log.append({"change": "milestone", "issue": n, "old": old, "new": new})
    # (1) label needs-spec
    gh("label", "create", "needs-spec", "-R", REPO, "--color", "fbca04",
       "--description", "Cites no spec behaviour: add a behaviour line or link one")
    for n in audit["1-no-spec-link"]:
        ok = gh("issue", "edit", str(n), "-R", REPO, "--add-label", "needs-spec")
        counts["label" if ok else "errors"] += 1
        log.append({"change": "label", "issue": n, "old": None, "new": "needs-spec"})
    # (2) comment the behaviour id on the proposed issue
    per_issue: dict[int, list[str]] = {}
    for r in audit["2-nonok-no-open-issue"]:
        for n in r["proposal"]:
            per_issue.setdefault(n, []).append(f"- `{r['id']}` [{r['tag']}] in {r['spec']}")
    for n, lines in sorted(per_issue.items()):
        body = ("Link audit 2026-10-26: this issue names a spec behaviour that is not OK and has no owning issue:\n"
                + "\n".join(lines) + "\nIf this issue owns it, cite it as (#%d) right after the tag in the spec line." % n)
        ok = gh("issue", "comment", str(n), "-R", REPO, "-F", "-", input=body) if not dry else True
        counts["comment" if ok else "errors"] += 1
        log.append({"change": "comment", "issue": n, "old": None, "new": "; ".join(l[2:] for l in lines)})
    with open(log_path, "w") as f:
        json.dump({"dry": dry, "counts": counts, "changes": log}, f, indent=1)
    return counts


# ---- self-test --------------------------------------------------------------------------------

def self_test() -> int:
    spec = """# Title
> Milestone: source-model

- `a.ok-one` — **[OK]** (#10) pinned by `test_alpha_works`
- `a.ok-two` — **[OK]** (#11) pinned by `test_beta_works` and `test_gamma_works`
  continuation line with prose citing #10 and -> #12
- `a.gap` — **[GAP]** (#12) not built
- `a.ok-prose-cite` — **[OK]** (#13) pinned by `test_alpha_works`; see also #12 in prose
- `a.ok-no-test` — **[OK]** (#14) says it works
- `a.ok-missing` — **[OK]** (#15) pinned by `test_present_here` and `test_absent_everywhere`
- `a.untagged` the text has no tag (#16)
- `a.partial-prose` — **[PARTIAL]** text, the cite comes later (#17) in prose

not a bullet (#18)
"""
    b = parse_bullets("s.md", spec)
    assert len(b) == 8, len(b)
    assert b[0].owned == {10} and b[0].tests == {"test_alpha_works"}
    assert b[1].owned == {11} and 10 not in b[1].owned and 12 not in b[1].owned
    assert b[2].owned == {12} and b[2].tag == "GAP"
    assert b[3].owned == {13} and 12 not in b[3].owned          # prose cite is not ownership
    assert b[6].tag == "UNTAGGED" and b[6].owned == set()       # untagged owns nothing
    assert b[7].owned == set() and b[7].tag == "PARTIAL"   # (#N) must follow the tag
    assert all(x.milestone == "source-model" for x in b)
    missing = {"test_absent_everywhere"}

    assert classify(10, b, missing, []).cls == "CLOSE-A"
    assert classify(11, b, missing, []).cls == "CLOSE-A"
    r = classify(12, b, missing, [])
    assert r.cls == "KEEP" and r.milestone == "source-model"
    assert classify(13, b, missing, []).cls == "CLOSE-A"         # 12 in prose does not own
    assert classify(14, b, missing, []).cls == "KEEP"             # OK, no test, no fix
    assert classify(14, b, missing, ["abc123def"]).cls == "CLOSE-B"
    r = classify(15, b, missing, ["abc123def"])                   # missing test beats a fix commit
    assert r.cls == "MISSING-TEST" and r.missing_tests == ["test_absent_everywhere"]
    assert classify(16, b, missing, []).cls == "NO-SPEC"          # untagged cite owns nothing
    assert classify(18, b, missing, []).cls == "NO-SPEC"
    assert classify(99, b, missing, ["aaa111bbb"]).cls == "CLOSE-B"
    assert classify(17, b, missing, []).cls == "NO-SPEC"        # prose cite owns nothing

    logsample = ("1111aaaa2222\x1fFix thing (#99)\x1fFixes #99\nCloses #7\x1e"
                 "3333bbbb4444\x1fPart of #8\x1fPart of #8 only\x1e")
    assert fix_commits(logsample) == {7: ["1111aaaa2"], 99: ["1111aaaa2"]}

    import os
    import tempfile
    rows = [classify(n, b, missing, []) for n in (10, 12, 15, 18)]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.tsv")
        write_tsv(p, rows)
        back = read_tsv(p)
    assert [(r.number, r.cls) for r in back] == [(10, "CLOSE-A"), (12, "KEEP"), (15, "MISSING-TEST"), (18, "NO-SPEC")]
    assert spec_milestones("> Milestone: export-pipeline (GitHub #316 — x)\n") == ["export-pipeline"]
    assert spec_milestones("> Milestone: A - B; C D\n") == ["A - B", "C D"]
    assert spec_milestones("> Milestone: TBD (proposed: x; until y)\n") == []
    assert manual_state("> Manual: docs/a.md\n", {"docs/a.md"}) == "OK"
    assert manual_state("> Manual: docs/a.md\n", set()) == "MISSING-PAGE"
    assert manual_state("> Manual: TBD — x\n", set()) == "TBD" and manual_state("x", set()) == "NONE"
    print("self-test OK")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Reconcile open issues against spec lines and fix commits (dry run by default).")
    ap.add_argument("--ref", default=DEFAULT_REF)
    ap.add_argument("--tsv")
    ap.add_argument("--apply", action="store_true", help="apply the decisions in --tsv (dry run otherwise)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--link-audit", metavar="JSON", help="write the link audit (read-only) to this JSON file")
    ap.add_argument("--link-ruled", metavar="LOG", help="apply the owner's link-audit ruling, logging to LOG")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--link-apply", action="store_true", help="apply the safe milestone moves of the link audit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.link_audit:
        with open(args.link_audit, "w") as f:
            json.dump(link_audit(args.ref), f, indent=1)
        return 0
    if args.link_ruled:
        print(json.dumps(link_apply_ruled(args.ref, args.link_ruled, args.dry)))
        return 0
    if args.link_apply:
        print(json.dumps(link_apply(args.ref)))
        return 0
    if not args.tsv:
        ap.error("--tsv is required")
    if shutil.which("gh") is None:
        print("gh is required", file=sys.stderr)
        return 2
    if args.apply:
        counts = apply_rows(read_tsv(args.tsv))
        print(json.dumps(counts))
        return 0 if counts["errors"] == 0 else 1
    specs = load_specs(args.ref)
    bullets = [b for path, text in specs for b in parse_bullets(path, text)]
    fixes = load_fixes(args.ref)
    issues = open_issues()
    names: set[str] = set()
    for b in bullets:
        names |= b.tests
    missing = test_missing_on_ref(args.ref, names)
    rows = [classify(n, bullets, missing, [str(s) for s in fixes.get(n, [])]) for n in issues]
    write_tsv(args.tsv, rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.cls] = counts.get(r.cls, 0) + 1
    print(json.dumps({"ref": args.ref, "open": len(issues), **counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
