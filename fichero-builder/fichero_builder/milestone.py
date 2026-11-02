"""`builder milestone <name> --spec FILE`: a milestone's open issues placed under the spec's build-order steps, one
cluster brief per step in build order, dependencies respected (dev-workflows.tool.milestone, Step 2.3). An issue under
no step, or a step whose `Depends on` names a step with open issues, is a QUESTION for a person, never a guess.
The step is read from the issue's `step:N.M` label, its title (`... Step 1.3: ...`, the shape `builder steps` files), a `Step: 1.3`
line in the body, or a build-order heading that names the issue (`#### Step 1.3 — title (#N)`, for a spec written before `builder steps`). The build order is parsed by the spec guard's own parser (one parser, never two). Imports nothing from the engine."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

from fichero_builder import codemap

STEP_IN_TITLE = r"\b{slug} Step (\d+\.\d+)\b"   # `<spec slug> Step 1.3: ...`, the shape `builder steps` files
STEP_IN_BODY = re.compile(r"^Step:?\s+(\d+\.\d+)\b", re.M)  # a bare line counts only inside the spec's own milestone
MILESTONE_LINE = re.compile(r"^>\s*Milestone:\s*(\S+)", re.M)
GUARD = Path(__file__).resolve().parents[2] / "scripts" / "check_spec_build_order_shape.py"


def spec_slug(spec_path) -> str:
    """The spec's milestone name from its `> Milestone:` line: the word an issue title puts before `Step`."""
    m = MILESTONE_LINE.search(Path(spec_path).read_text())
    if not m:
        raise ValueError(f"{spec_path} has no `> Milestone:` line")
    return m.group(1)


def build_order(spec_path, guard=GUARD) -> list[dict]:
    """The spec's steps in build order: [{number, title, depends_on, behaviours}], via the guard's parser."""
    import sys

    spec = importlib.util.spec_from_file_location("build_order_guard", guard)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(guard).parent))  # the guard imports helpers beside it
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(Path(guard).parent))
    parsed = mod._parse_build_order(Path(spec_path).read_text())
    if not parsed:
        raise ValueError(f"{spec_path} has no Build order section")
    return [s for stage in parsed["stages"] for s in stage["steps"]]


def step_of(issue: dict, slug: str) -> str | None:
    """The step an issue names for THIS spec: `<slug> Step 1.3` in the title, else a `Step: 1.3` body line (the issue
    is in the spec's milestone already). Another spec's `other Step 1.3` is not this spec's step (first real run 2026-11-01)."""
    for lb in issue.get("labels") or []:  # the labels are the key (`builder steps` applies `step:N.M`); the shapes below are the fallback
        name = lb.get("name", "") if isinstance(lb, dict) else str(lb)
        if name.startswith("step:"):
            return name[5:]
    m = re.search(STEP_IN_TITLE.format(slug=re.escape(slug)), issue.get("title") or "") or STEP_IN_BODY.search(issue.get("body") or "")
    return m.group(1) if m else None


def list_issues(milestone: str, *, gh: str = "gh") -> list[dict]:
    r = subprocess.run([gh, "issue", "list", "--milestone", milestone, "--state", "open", "--limit", "200",
                        "--json", "number,title,body,labels"], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(f"gh could not list milestone {milestone!r}: {r.stderr.strip()}")
    return json.loads(r.stdout)


def plan(issues: list[dict], steps: list[dict], slug: str) -> dict:
    """{'clusters': [{'step', 'title', 'issues', 'waits'}] in build order (waits = the steps with open issues it depends on),
    'questions': [str]} (an issue under no step, a step the spec lacks, and ONE line for all the waits)."""
    by_step: dict[str, list[dict]] = {}
    questions = []
    known = {s["number"] for s in steps}
    named = {}  # a step heading that names issues `(#N, #M)` places them too (specs written before `builder steps`)
    for s in steps:
        for n in re.findall(r"#(\d+)", s.get("title") or "") + ([s["issue"]] if s.get("issue") else []):
            named.setdefault(int(n), s["number"])
    for i in sorted(issues, key=lambda x: x["number"]):
        st = step_of(i, slug) or named.get(i["number"])
        if st is None:
            questions.append(f"#{i['number']} names no build-order step: which step is it, or does it leave the milestone?")
        elif st not in known:
            questions.append(f"#{i['number']} names Step {st}, which the spec's build order does not have")
        else:
            by_step.setdefault(st, []).append(i)
    clusters, waiting = [], []
    for s in steps:
        mine = by_step.get(s["number"])
        if not mine:
            continue
        waits = [d for d in s["depends_on"] if by_step.get(d)]
        clusters.append({"step": s["number"], "title": s["title"], "issues": mine, "waits": waits})
        if waits:
            waiting.append(f"{s['number']} (after {', '.join(waits)})")
    if waiting:  # one line, not one per step: the queue runs them in order, a person only reads it
        questions.append(f"Steps that wait on earlier steps with open issues: {'; '.join(waiting)}: queued after those land, or a person says otherwise")
    return {"clusters": clusters, "questions": questions}


_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.+-]*)")
OUTLINE = re.compile(r"^\s*(?:(?:public|private|internal|final|static|async|override) )*(?:def|class|func|struct|enum|protocol|actor)\s+(\w+)", re.M)


NEVER = re.compile(r"^(agent-work/|LICENSE|COPYING)")  # drafts, experiments and legal text are never a step's starting point


def _outline(repo: str, f: str) -> list[str]:
    text = (Path(repo) / f).read_text(errors="replace")
    return [f"{m.group(1)} ({text.count(chr(10), 0, m.start(1)) + 1})" for m in OUTLINE.finditer(text)][:12]


def _importers(repo: str, files: list[str], limit: int = 5) -> list[str]:
    """Python files that import one of `files` by module name (git grep; Swift has no file imports)."""
    out: list[str] = []
    for f in files:
        stem = Path(f).stem
        if not f.endswith(".py") or stem == "__init__":
            continue
        r = subprocess.run(["git", "-C", repo, "grep", "-w", "-e", stem, "--", "*.py"], capture_output=True, text=True)
        imp = re.compile(rf"^\s*(from|import)\s.*\b{re.escape(stem)}\b")  # git grep's -E has no \b on every platform
        hits = [x.split(":", 1)[0] for x in r.stdout.splitlines() if imp.match(x.split(":", 1)[-1])]
        out += [x for x in dict.fromkeys(hits) if x not in files and not NEVER.match(x)][:limit]
    return list(dict.fromkeys(out))


def _step_text(text: str, step: str) -> str:
    """The step's own section of the build order and the behaviour bullets it lists (with their continuation lines)."""
    m = re.search(rf"^(#+) Step {re.escape(step)}\b.*?$(.*?)(?=^#|\Z)", text, re.M | re.S)
    section = m.group(0) if m else ""
    ids = set(re.findall(r"`([a-z][a-z0-9-]*\.[a-z0-9.-]+)`", section))
    bullets = [b for b in re.findall(r"^- `[^`]+`.*(?:\n  .*)*", text, re.M) if re.match(r"- `([^`]+)`", b).group(1) in ids]
    return "\n".join([section, *bullets])


def where_map(spec_path, step: str, repo: str, binary: str, issues=()) -> list[str]:
    """A step's map, so its worker reads less: the spec, the directories its design section names, and only the files that
    the step's section, its behaviour lines and its issues' Where/Test lines name, plus the Python files importing them, each
    with its outline (the code map when the repo is indexed, else by regex). Never agent-work/ or LICENSE (real use 2026-11-02:
    a search by the step's words listed both)."""
    spec = Path(spec_path)
    text = spec.read_text()
    try:
        rel = spec.resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        rel = spec.name
    m = re.search(r"^## (?:The )?[Dd]esign\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    dirs = []
    for p in _PATH.findall(m.group(1) if m else ""):
        d = p if p.endswith("/") else p.rsplit("/", 1)[0] + "/"
        if (Path(repo) / d).is_dir() and d not in dirs and not NEVER.match(d):
            dirs.append(d)
    lines = [_step_text(text, step)] + [ln for i in issues for ln in (i.get("body") or "").splitlines() if re.search(r"\b(where|tests?)\b", ln, re.I)]
    paths = [f for f in dict.fromkeys(_PATH.findall("\n".join(lines))) if f != rel and not NEVER.match(f)]
    named = [f for f in paths if (Path(repo) / f).is_file()]
    to_write = [(f.rsplit("/", 1)[0] + "/", f) for f in paths if "." in f.rsplit("/", 1)[-1] and not (Path(repo) / f).exists()
                and (Path(repo) / f).parent.is_dir()]  # a file the step writes: its directory exists already
    files = named + _importers(repo, named)
    found = (codemap.outlines(binary, repo, files) if files else None) or {f: _outline(repo, f) for f in files}
    return [f"{rel} (the spec)", *(f"{d} (the directory the spec's design names)" for d in dirs),
            *(f"{d} (where {f} goes; it does not exist yet)" for d, f in to_write),
            *(f"{f}: {', '.join(syms) or '(no symbols)'}" for f, syms in found.items())]


def write_briefs(planned: dict, *, out, repo_dir, base: str, rules: str, fetch, cluster, spec_path=None, binary: str = "", lane: str = "") -> list[Path]:
    """One brief file per cluster, through the brief tool (`fetch` reads an issue with its comments, `cluster` builds the text);
    each carries the step's map when the spec is given."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for c in planned["clusters"]:
        issues = [fetch(i["number"]) for i in c["issues"]]
        where = where_map(spec_path, c["step"], str(repo_dir), binary, issues) if spec_path else []
        text = cluster(issues, repo=str(repo_dir), branch=f"lane-{lane}" if lane else f"step-{c['step']}", base="the lane's head" if lane else base, rules=rules, where=where)
        p = out / f"brief-step-{c['step']}.txt"
        p.write_text(text)
        written.append(p)
    return written
