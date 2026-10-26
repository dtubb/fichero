"""`plan <spec>` (pipeline.spec-to-plan): a big spec with no ordered build steps gets a PROPOSED `## Proposed build order`.
The facts are deterministic (every behaviour that owes a step, the tests it cites, what already exists in the tree);
ONE big-tier call writes the steps; the runner validates them against scripts/check_spec_build_order_shape.py's own
parser, appends the section to the spec (never editing a behaviour line or a status) and queues "approve this plan?"."""
from __future__ import annotations

import importlib.util
import re
import sys
import time
from pathlib import Path

from pipeline import ROOT, STATE, checks, coder, core, journal

MAX_BEHAVIOURS = 120  # ponytail: one call writes the whole plan; a bigger spec needs a per-section plan first
PROPOSED = "## Proposed build order (proposed, not approved)"
OWN = re.compile(r"^- `([a-z][a-z0-9+_-]*(?:\.[a-z0-9+_-]+)+)` \[(PARTIAL|MISSING|GAP|BROKEN|OK)[^\]]*\]", re.M)
TEST_REF = re.compile(r"[\w./-]*test[\w./-]*\.(?:py|swift)(?:::\w+)?", re.I)
TOKEN = re.compile(r"`([A-Za-z_][\w./-]*(?:\(\))?)`")


def guard():
    """scripts/check_spec_build_order_shape.py as a module: its parser and checks are the definition of the shape."""
    sys.path.insert(0, str(ROOT / "scripts"))
    s = importlib.util.spec_from_file_location("check_spec_build_order_shape", ROOT / "scripts" / "check_spec_build_order_shape.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)  # type: ignore[union-attr]
    return m


def behaviours(text: str) -> list[dict]:
    """The behaviours that owe a step: {id, tag, text, tests}, in spec order (an owned `- `id` [TAG]` list line and its
    indented continuation; ids cited inline in prose are another spec's)."""
    out, lines = [], text.splitlines()
    for i, ln in enumerate(lines):
        m = OWN.match(ln)
        if not m or m.group(2) == "OK":
            continue
        block = [ln]
        for nxt in lines[i + 1:]:
            if not nxt[:1].isspace():
                break
            block.append(nxt)
        body = " ".join(x.strip() for x in block)
        out.append({"id": m.group(1), "tag": m.group(2), "text": body[:420], "tests": sorted(set(TEST_REF.findall(body)))})
    return out


def exists(root: Path, b: dict) -> dict:
    """What the tree already holds for one behaviour: cited test/path files that exist, and files naming a cited symbol."""
    files = [t.split("::")[0] for t in b["tests"]]
    tokens = [t for t in TOKEN.findall(b["text"]) if t not in b["id"] and ("/" in t or "_" in t or t[:1].isupper() or t.endswith("()"))][:6]
    have, hits = [f for f in files if (root / f).exists()], {}
    for t in tokens:
        r = checks.sh(["git", "grep", "-l", "-F", "-m", "1", t.rstrip("()"), "--", ".", ":!docs", ":!agent-work"], cwd=root)
        if r.stdout.strip():
            hits[t] = r.stdout.split()[:3]
    return {"tests_present": have, "tests_missing": [f for f in files if f not in have], "symbols": hits}


def prompt(spec: Path, bs: list[dict], text: str, root: Path) -> str:
    old = next(iter(re.findall(r"(?ms)^## Build order.*?(?=^## |\Z)", text)), "")[:4000]
    rows = []
    for b in bs:
        e = exists(root, b)
        rows.append(f"- `{b['id']}` [{b['tag']}] {b['text']}\n  tests cited: {', '.join(b['tests']) or 'none'}; present: {', '.join(e['tests_present']) or 'none'}; "
                    f"symbols found in: {'; '.join(f'{k} -> {v[0]}' for k, v in e['symbols'].items()) or 'none'}")
    return "\n".join([
        f"Write a build order for the spec `{spec.name}` and nothing else. Reply with ONLY the section, starting with the line "
        f"`{PROPOSED}`.", "",
        "Shape (a script checks it): optional `### Stage N — title`; then ordered `#### Step N.M — title` entries, each followed by "
        "`- Behaviours: `id`, `id`` (ids in backticks), `- Tests: path, path` (test paths from the facts; invent none: for a behaviour "
        "with none cited, name the file where its test belongs), `- Depends on: N.M, ...` (only EARLIER steps; omit when it is the step "
        "before) and `- Size: S` or `M` (never L).", "",
        "Rules: every behaviour below in exactly ONE step; at most 5 behaviours per step, so one coder session finishes a step; mechanical "
        "and independent steps first, steps that others depend on before them; person-visible value early; behaviours that touch the same "
        "files together. Do not edit, restate or re-tag any behaviour line.", "",
        *([f"The author's current ordering notes (keep their intent where it fits):\n{old}", ""] if old else []),
        f"## Behaviours that owe a step ({len(bs)})", *rows])


def check_plan(section: str, bs: list[dict]) -> list[str]:
    """Problems with a proposed section: the guard's own structure checks, and every behaviour in exactly one step."""
    g = guard()
    body = section.replace(PROPOSED, "## Build order", 1)
    approved = g._check_spec("**Status: APPROVED\n\n" + body)
    probs = list(approved[1]) if approved else ["no Build order section"]
    steps = [s for st in (g._parse_build_order(body) or {"stages": []})["stages"] for s in st["steps"]]
    for b in bs:
        n = [s["number"] for s in steps if b["id"] in s["behaviours"]]
        if len(n) != 1:
            probs.append(f"`{b['id']}` is in {len(n)} steps")
    known = {b["id"] for b in bs}
    probs += [f"Step {s['number']} names `{i}`, which is not a behaviour owing a step" for s in steps for i in s["behaviours"] if i not in known]
    return probs


def plan(spec: str) -> dict:
    """Propose (not approve) a build order for `spec` (a path from the repo root). One model call, at most; the spec file
    gains a `## Proposed build order` section and the owner's question is queued."""
    core._require_running()
    core._require_budget()
    c = core.cfg()
    root = Path(c["repo"]["path"])
    path = root / spec
    text = path.read_text()
    if PROPOSED.split(" (")[0] in text:
        raise RuntimeError(f"{spec} already has a proposed build order; approve it (`plan-approve`) or delete the section first")
    bs = behaviours(text)
    if not bs:
        return {"spec": spec, "behaviours": 0, "note": "every behaviour is [OK]: nothing to plan"}
    if len(bs) > MAX_BEHAVIOURS:
        raise RuntimeError(f"{spec} has {len(bs)} behaviours owing a step (max {MAX_BEHAVIOURS} in one plan): plan a section of it first")
    worker = core.config.at_tier(c, core.workers("manager")[0], "big")
    session = STATE / "sessions" / "plan" / f"{path.stem}-{time.strftime('%Y%m%d-%H%M%S')}"
    st = coder.ask_once(c, worker, prompt(path, bs, text, root), session)
    journal.append("cost", issue=0, key=f"plan:{spec}", task="plan", session=str(session), usd=round(st["cost_usd"], 4),
                   tokens=st["tokens"], model=st["model"], tools={})
    m = re.search(r"(?ms)^## Proposed build order.*", st.get("answer") or "")
    if not m:
        raise RuntimeError(f"the planner returned no `{PROPOSED}` section; nothing was written (cost ${st['cost_usd']:.2f})")
    section = "\n".join([PROPOSED, *m.group(0).strip().splitlines()[1:]])
    problems = check_plan(section, bs)
    path.write_text(text.rstrip("\n") + "\n\n" + section + "\n")
    note = f" The shape check found {len(problems)} problem(s): {'; '.join(problems[:5])}." if problems else " It passes the shape check."
    core._queue("plan", f"Approve the build order proposed for {spec}? It is the section '{PROPOSED[3:]}' at the end of the file." + note +
                f" To approve: `python -m pipeline plan-approve {spec}`; to change it, edit the section or answer with what to change.",
                options=["approve", "change"])
    return {"spec": spec, "behaviours": len(bs), "steps": len(re.findall(r"(?m)^#### Step ", section)), "problems": problems,
            "cost_usd": round(st["cost_usd"], 4)}


core.API.update(plan=plan)
core.WORKER_FORBIDDEN += ("plan",)
