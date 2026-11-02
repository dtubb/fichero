"""`builder milestone <name> --spec FILE`: a milestone's open issues placed under the spec's build-order steps, one
cluster brief per step in build order, dependencies respected (dev-workflows.tool.milestone, Step 2.3). An issue under
no step, or a step whose `Depends on` names a step with open issues, is a QUESTION for a person, never a guess.
The step is read from the issue title (`... Step 1.3: ...`, the shape `builder steps` files) or a `Step: 1.3` line in
the body. The build order is parsed by the spec guard's own parser (one parser, never two). Imports nothing from the engine."""
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
    for i in sorted(issues, key=lambda x: x["number"]):
        st = step_of(i, slug)
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
STOP = {"the", "and", "for", "with", "from", "into", "that", "this", "step", "builder", "spec"}
OUTLINE = re.compile(r"^\s*(?:(?:public|private|internal|final|static|async|override) )*(?:def|class|func|struct|enum|protocol|actor)\s+(\w+)", re.M)


def _grep_map(repo: str, words: list[str], dirs: list[str], limit: int = 10) -> dict[str, list[str]]:
    """The fallback when the repo has no index: files that mention a word, with an outline read by regex."""
    found: dict[str, list[str]] = {}
    for w in words:
        r = subprocess.run(["git", "-C", repo, "grep", "-l", "-i", w, "--", *(dirs or ["."]), ":(exclude,glob)**/*.md"], capture_output=True, text=True)
        for f in r.stdout.split()[:limit]:
            if f not in found and len(found) < limit:
                text = (Path(repo) / f).read_text(errors="replace")
                found[f] = [f"{m.group(1)} ({text.count(chr(10), 0, m.start(1)) + 1})" for m in OUTLINE.finditer(text)][:12]
    return found


def where_map(spec_path, step_title: str, repo: str, binary: str) -> list[str]:
    """A step's map, so its worker reads less: the spec, the directories its design section names, and the files and symbols
    for the step's words (the code map when the repo is indexed, else grep), each with its outline."""
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
        if (Path(repo) / d).is_dir() and d not in dirs:
            dirs.append(d)
    words = [w for w in re.findall(r"[a-z]{4,}", step_title.lower()) if w not in STOP]
    found = (codemap.search(binary, repo, words) if words else None) or _grep_map(repo, words, dirs)
    return [f"{rel} (the spec)", *(f"{d} (the directory the spec's design names)" for d in dirs),
            *(f"{f}: {', '.join(syms) or '(no symbols)'}" for f, syms in found.items())]


def write_briefs(planned: dict, *, out, repo_dir, base: str, rules: str, fetch, cluster, spec_path=None, binary: str = "") -> list[Path]:
    """One brief file per cluster, through the brief tool (`fetch` reads an issue with its comments, `cluster` builds the text);
    each carries the step's map when the spec is given."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for c in planned["clusters"]:
        issues = [fetch(i["number"]) for i in c["issues"]]
        where = where_map(spec_path, c["title"], str(repo_dir), binary) if spec_path else []
        text = cluster(issues, repo=str(repo_dir), branch=f"step-{c['step']}", base=base, rules=rules, where=where)
        p = out / f"brief-step-{c['step']}.txt"
        p.write_text(text)
        written.append(p)
    return written
