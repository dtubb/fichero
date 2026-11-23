"""`builder review start|check|approve <area>`: a review is a step kind (local.review.*, #6847).

A review session writes a report (headings in `prompts/review-common.md`) and spec changes on branch `review-<area>`.
This module reads the report, refuses a malformed one, and does what a program can do after the owner approves it:
file the issues, map the spec's `NEW` tags by id, number the Build order, add the milestone to build-order.md, comment
on the issues that gained evidence, turn the owner's questions into alerts, commit, and enqueue the steps once landed."""
from __future__ import annotations

import json
import re
import subprocess
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
            title = re.split(r"(?<=[.])\s", re.split(r"\s*\(`", m.group(2).strip())[0])[0].strip().rstrip(" .:")
            issues.append({"key": m.group(1), "title": title[:200], "behaviours": BEHAVIOUR.findall(it), "text": it})
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


BULLET = re.compile(r"^\s*-\s+`([\w.-]+)`")
TAG = re.compile(r"#NEW-(S?\d+)\b")
BARE = re.compile(r"#NEW(?![-\w])")
STEP_HEAD = re.compile(r"^(####\s+Step\s+(\d+\.\d+)\s*[—–-]\s*)(.*?)\s*$")
TAIL = re.compile(r"\s*\((#\d+(?:,\s*#\d+)*)\)\s*$")
ORDER_FILE = "docs/contributor_manual/specs/build-order.md"
SPECS = "docs/contributor_manual/specs/"
TRAILERS = "Spec-change: owner 2026-11-21 a review incorporates itself\nWritten-By: Claude Opus 5.5 using Claude Code using Fichero Builder"


def owners_of(issues: list[dict]) -> dict[str, list[str]]:
    """{behaviour id: [issue keys that name it]}: how a bare `#NEW` is mapped (by id, never by order)."""
    out: dict[str, list[str]] = {}
    for i in issues:
        for b in i["behaviours"]:
            out.setdefault(b, []).append(i["key"])
    return out


def map_tags(spec: str, nums: dict[str, int], owners: dict[str, list[str]]) -> tuple[str, list[str]]:
    """The spec with each `#NEW-n` / `#NEW-Sn` replaced by its filed number, and each bare `#NEW` on a behaviour bullet by the
    number of the one issue that names that behaviour. A tag with no filed issue, and a bare tag whose bullet no issue (or two
    issues) names, are problems; a bare tag on no bullet is legend text and stays."""
    out, bad, cur = [], [], None
    for n, ln in enumerate(spec.split("\n"), 1):
        if not ln.strip() or ln.startswith("#"):
            cur = None
        elif m := BULLET.match(ln):
            cur = m.group(1)

        def numbered(m):
            if m.group(1) not in nums:
                bad.append(f"spec line {n}: #NEW-{m.group(1)} is not in the report's Issues list")
                return m.group(0)
            return f"#{nums[m.group(1)]}"

        ln = TAG.sub(numbered, ln)

        def bare(m):
            keys = owners.get(cur or "", [])
            if cur and len(keys) == 1 and keys[0] in nums:
                return f"#{nums[keys[0]]}"
            if cur:
                bad.append(f"spec line {n}: a bare #NEW on `{cur}`, which {'two issues name' if len(keys) > 1 else 'no issue names'}")
            return m.group(0)

        out.append(BARE.sub(bare, ln))
    return "\n".join(out), bad


def number_steps(spec: str, fixes: list[dict], nums: dict[str, int]) -> tuple[str, list[str]]:
    """Each Build order step heading takes `(#N, #M)`: the issues of the ranked fixes that cite the step as `[N.M]`. A fix
    with no step, a fix whose step the spec lacks, and a step no fix cites are problems."""
    lines = spec.split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(r"^##\s+Build order\b", ln)), None)
    if start is None:
        return spec, ["the spec has no `## Build order` section: the review writes one step per ranked fix"]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    by_step: dict[str, list[int]] = {}
    bad = []
    for f in fixes:
        if not f["step"]:
            bad.append(f"ranked fix {f['n']} cites no spec step as `[N.M]`")
            continue
        got = [nums[k] for k in f["new"] if k in nums] + f["old"]
        by_step.setdefault(f["step"], []).extend(x for x in got if x not in by_step.get(f["step"], []))
    seen = set()
    for i in range(start + 1, end):
        m = STEP_HEAD.match(lines[i])
        if not m:
            continue
        step, title = m.group(2), m.group(3)
        seen.add(step)
        if step not in by_step:
            bad.append(f"Step {step} has no ranked fix, so no issue")
            continue
        tail = TAIL.search(title)
        have = [int(x) for x in re.findall(r"#(\d+)", tail.group(1))] if tail else []
        title = TAIL.sub("", title)
        both = have + [x for x in by_step[step] if x not in have]
        lines[i] = f"{m.group(1)}{title} ({', '.join('#%d' % x for x in both)})"
    bad += [f"a ranked fix cites Step {s}, which the spec's Build order lacks" for s in by_step if s not in seen]
    return "\n".join(lines), bad


def add_order_line(text: str, milestone: str, spec_rel: str, after: str = "", desc: str = "") -> str:
    """build-order.md with the milestone's line under `## In order` (after `after`, else last), numbered; a line that is there
    only has its `Spec:` path set. Nothing outside the `## In order` list is touched."""
    from fichero_builder import order

    if "## In order" not in text:
        raise ValueError("build-order.md has no `## In order` section")
    head, rest = text.split("## In order", 1)
    body, sep, tail = rest.partition("\n## ")
    lines = body.split("\n")
    idx = [i for i, ln in enumerate(lines) if order.LINE.match(ln)]
    names = [order.LINE.match(lines[i]).group(1) for i in idx]
    if milestone in names:
        i = idx[names.index(milestone)]
        lines[i] = re.sub(r"Spec:\s*\S+", f"Spec: {spec_rel}", lines[i]) if "Spec:" in lines[i] else f"{lines[i].rstrip()} Spec: {spec_rel}"
    else:
        if after and after not in names:
            raise ValueError(f"build-order.md has no `{after}` line to put `{milestone}` after")
        at = (idx[names.index(after)] if after else idx[-1] if idx else len(lines) - 1) + 1
        lines.insert(at, f"0. `{milestone}` — {desc or milestone}. Spec: {spec_rel}")
        n = 0
        for i, ln in enumerate(lines):
            if order.LINE.match(ln):
                n += 1
                lines[i] = re.sub(r"^\d+\.", f"{n}.", ln)
    joined = "\n".join(lines)
    return f"{head}## In order{joined}{sep}{tail}"


def _gh(gh: str, args: list[str], cwd) -> str:
    r = subprocess.run([gh, *args], capture_output=True, text=True, cwd=str(cwd), timeout=120)
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def _issue_body(area: str, spec_rel: str, issue: dict, steps: list[str]) -> str:
    ids = ", ".join(f"`{b}`" for b in issue["behaviours"])
    return (f"{issue['text']}\n\nFrom the review of `{area}` (spec `{spec_rel}`)." + (f"\nBehaviours: {ids}" if ids else "")
            + (f"\n\nStep: {steps[0]}" if steps else ""))


def approve(a) -> tuple[int, str]:
    """local.review.approve-files-and-maps, .every-fix-has-an-issue, .evidence-and-questions, .approve-lands-then-enqueues."""
    from fichero_builder import journal

    if not a.milestone or not a.spec:
        return 1, "REFUSED: approve needs --milestone and --spec"
    wt, area = worktree_of(a.repo_dir, a.area), a.area
    try:
        text = report_of(a.repo_dir, area, a.report).read_text()
        spec_f, order_f = wt / a.spec, wt / ORDER_FILE
        spec, order_text = spec_f.read_text(), order_f.read_text()
    except OSError as e:
        return 1, f"REFUSED: {e}"
    faults = check(text)
    p = parse(text)
    keys = {i["key"]: 0 for i in p["issues"]}
    spec_rel = a.spec[len(SPECS):] if a.spec.startswith(SPECS) else a.spec
    if not faults:  # a dry pass with placeholder numbers: nothing is filed unless the whole approve can finish
        faults += map_tags(spec, keys, owners_of(p["issues"]))[1] + number_steps(spec, p["fixes"], keys)[1]
        try:
            add_order_line(order_text, a.milestone, spec_rel, a.after, a.desc)
        except ValueError as e:
            faults.append(str(e))
    if faults:
        return 1, "\n".join(f"REFUSED: {f}" for f in faults)
    state = Path(journal.STATE)
    state.mkdir(parents=True, exist_ok=True)
    mapf = state / f"review-{area}-issues.json"
    done = json.loads(mapf.read_text()) if mapf.exists() else {}
    done.setdefault("issues", {}), done.setdefault("comments", []), done.update(area=area, milestone=a.milestone, spec=a.spec)

    def save():
        mapf.write_text(json.dumps(done, indent=1))

    for i in p["issues"]:
        if i["key"] in done["issues"]:
            continue
        steps = [f["step"] for f in p["fixes"] if i["key"] in f["new"] and f["step"]]
        out = _gh(a.gh, ["issue", "create", "--title", f"[{a.milestone}] {i['title']}", "--milestone", a.milestone,
                         "--body", _issue_body(area, spec_rel, i, steps)], a.repo_dir)
        m = re.search(r"/issues/(\d+)\s*$", out)
        if not m:
            return 1, f"REFUSED: gh issue create printed no issue url for NEW-{i['key']}: {out[-200:]}"
        done["issues"][i["key"]] = int(m.group(1))
        done.setdefault("titles", {})[i["key"]] = f"[{a.milestone}] {i['title']}"
        save()
    for n, (num, ev) in enumerate(p["evidence"]):
        if f"{num}:{n}" not in done["comments"]:
            _gh(a.gh, ["issue", "comment", str(num), "--body", f"Evidence from the review of `{area}`: {ev}"], a.repo_dir)
            done["comments"].append(f"{num}:{n}")
            save()
    from fichero_builder import queue

    done.setdefault("alerts", [])
    first = [min(int(v) for v in done["issues"].values())]
    for n, q in enumerate(p["questions"], 1):  # one alert per owner question, once
        if n not in done["alerts"]:
            queue.alert(f"review-{area}", f"question-{n}", f"Owner question {n} of the {area} review: {q}", str(report_of(a.repo_dir, area, a.report)),
                        ["ask-owner", "park"], issues=first)
            done["alerts"].append(n)
            save()
    nums = {k: int(v) for k, v in done["issues"].items()}
    spec2, _ = map_tags(spec, nums, owners_of(p["issues"]))
    spec2, _ = number_steps(spec2, p["fixes"], nums)
    spec_f.write_text(spec2)
    order_f.write_text(add_order_line(order_text, a.milestone, spec_rel, a.after, a.desc))
    listing = state / f"review-{area}-issue-list.txt"
    listing.write_text("".join(f"#{n} {done['titles'][k]}\n" for k, n in nums.items()))
    _git(wt, "add", "--", a.spec, ORDER_FILE)
    if _git(wt, "diff", "--cached", "--quiet").returncode:
        msg = state / f"review-{area}-commit.txt"
        msg.write_text(f"docs(spec): the {area} review lands with its issues and its build order "
                       f"({', '.join('#%d' % n for n in nums.values())})\n\nIssues filed in milestone {a.milestone}; the spec's NEW tags are "
                       f"their numbers, its Build order steps name them, build-order.md lists the milestone.\n\nPart of #6847\n\n{TRAILERS}\n")
        r = _git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-q", "-F", str(msg))
        if r.returncode:
            return 1, f"REFUSED: commit failed: {r.stderr.strip()[-300:]}"
    done["commit"] = _git(wt, "rev-parse", "HEAD").stdout.strip()
    save()
    return 0, (f"approved {area}: {len(nums)} issue(s) {', '.join('#%d' % n for n in nums.values())}, spec committed at {done['commit'][:10]} "
               f"on review-{area}; issue list for the landing step: {listing}")


AREA = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
COMMON = Path(__file__).resolve().parents[1] / "prompts" / "review-common.md"


def _git(cwd, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(cwd), *args], capture_output=True, text=True)


def start(repo_dir, area: str, base: str = "", scope: str = "") -> tuple[int, str]:
    """local.review.start-queues-a-session: the review worktree and branch from the base, the brief, one queued step."""
    import tomllib

    from fichero_builder import journal, queue

    if not AREA.fullmatch(area):
        return 1, f"REFUSED: area {area!r} is not a word of lowercase letters, digits and dashes"
    wt, branch = worktree_of(repo_dir, area), f"review-{area}"
    if wt.exists() or _git(repo_dir, "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode == 0:
        return 1, f"REFUSED: the review of {area} was started: worktree {wt} or branch {branch} exists"
    land = tomllib.loads((Path(repo_dir) / "harness.toml").read_text()).get("land", {}).get("branch", "")
    base = base or (f"origin/{land}" if land else "")
    sha = _git(repo_dir, "rev-parse", "--verify", "-q", f"{base}^{{commit}}").stdout.strip() if base else ""
    if not sha:
        return 1, f"REFUSED: base {base!r} is not a commit in {repo_dir}"
    made = _git(repo_dir, "worktree", "add", "-q", "-b", branch, str(wt), sha)
    if made.returncode:
        return 1, f"REFUSED: could not make the worktree: {made.stderr.strip()[-300:]}"
    exclude = Path(_git(wt, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip())
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a") as f:
        f.write(f"review-{area}.md\n")
    brief = journal.STATE / f"review-{area}-brief.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(f"# Review: {area}\n\nArea: {area}\nScope: {scope or 'the area named, its code, its specs and its issues'}\n"
                     f"Worktree: {wt} (branch {branch}, base {sha[:10]})\nReport: review-{area}.md in the worktree root (not committed)\n"
                     f"Trailers: `Written-By: Claude Opus 5.5 using Claude Code using Fichero Builder` and `Spec-change: owner 2026-11-21 a review incorporates itself`\n\n"
                     + COMMON.read_text())
    queue.add(f"review-{area}", str(wt), "review", str(brief), [])
    return 0, f"review {area}: worktree {wt}, branch {branch} at {sha[:10]}, step `review` queued on lane review-{area} (brief {brief})"


def main(a) -> int:
    if a.action == "start":
        try:
            rc, msg = start(a.repo_dir, a.area, a.base, a.scope)
        except (OSError, ValueError) as e:
            rc, msg = 1, f"REFUSED: {e}"
        print(msg)
        return rc
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
    if a.action == "approve":
        try:
            rc, msg = approve(a)
        except (OSError, RuntimeError, ValueError) as e:
            rc, msg = 1, f"REFUSED: {e}"
        print(msg)
        return rc
    return 1
