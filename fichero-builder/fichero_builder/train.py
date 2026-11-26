"""The merge train (local.train.*): the expensive checks run once for many steps.

A step green on the cheap rungs waits in state `train`. When `[train].min_steps` wait, or the oldest has waited
`[train].max_wait_min`, `run_train` merges every waiting step's head onto the land branch in queue order (a throwaway
candidate), runs the Swift build, the Swift tests, the UI pass and the full unit tier on it once, and decides which steps
may land. A red candidate is bisected: the first red rung is re-run over prefixes of the train until one step is the culprit,
then once over the rest; never more than ceil(log2(n)) + 1 extra runs. A step that does not merge cleanly is sent back with
the conflict and the rest go on. The functions take their git and rung runners as arguments; `real_runners` builds the ones
the loop uses."""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable

RUNG_ORDER = ("build", "swift-tests", "ui", "unit")
KEYS = {"enabled", "min_steps", "max_wait_min"}


@dataclass(frozen=True)
class Cfg:
    enabled: bool = True
    min_steps: int = 4
    max_wait_min: float = 45.0


def load(rules: dict) -> Cfg:
    """`[train]` of the rules; a missing table is the defaults, an unknown key or a bad value refuses."""
    t = rules.get("train", {})
    if unknown := sorted(set(t) - KEYS):
        raise ValueError(f"harness.toml [train]: unknown keys {unknown}")
    cfg = Cfg(enabled=bool(t.get("enabled", True)), min_steps=int(t.get("min_steps", 4)), max_wait_min=float(t.get("max_wait_min", 45)))
    if cfg.min_steps < 1 or cfg.max_wait_min <= 0:
        raise ValueError("harness.toml [train]: min_steps must be at least 1 and max_wait_min above 0")
    return cfg


def due(since: list[float], now: float, cfg: Cfg) -> bool:
    """`since`: when each waiting step began to wait. A train starts at min_steps, or when the oldest has waited max_wait_min."""
    return bool(since) and (len(since) >= cfg.min_steps or now - min(since) >= cfg.max_wait_min * 60)


@dataclass
class Result:
    id: str
    candidate: str = ""
    steps: list = field(default_factory=list)    # every step key the train took, in queue order
    landed: list = field(default_factory=list)   # keys cleared to land, in queue order
    back: dict = field(default_factory=dict)     # key -> {kind, why, findings}: sent back to its lane
    again: list = field(default_factory=list)    # keys left unjudged: they wait for the next train
    rungs: list = field(default_factory=list)    # {name, ok, seconds, phase, on}
    bisect: list = field(default_factory=list)   # one line per bisect run, in order
    extra_runs: int = 0                          # rung runs beyond the first pass over the candidate
    result: str = ""                             # green | red | conflict | unresolved


def run_train(steps: list[dict], *, merge: Callable, rung: Callable, rungs_for: Callable, tid: str, clock: Callable = time.time) -> Result:
    """`steps`: [{key, head}] in queue order. `merge(heads) -> (candidate sha, {head: conflict text})`; `rung(name, candidate) ->
    (ok, output)`; `rungs_for(heads) -> [rung names]`, in RUNG_ORDER."""
    res = Result(id=tid, steps=[s["key"] for s in steps])
    cand, conflicts = merge([s["head"] for s in steps])
    for s in steps:
        if s["head"] in conflicts:
            res.back[s["key"]] = {"kind": "conflict", "why": f"the step does not merge with the other steps of train {tid}", "findings": conflicts[s["head"]]}
    keep = [s for s in steps if s["head"] not in conflicts]
    if not keep:
        res.result = "conflict"
        return res
    res.candidate = cand

    def run(names: list[str], on: str, phase: str) -> tuple[str, str] | None:
        """The first red (name, output) of `names` on `on`, else None; one row each."""
        for name in names:
            t0 = clock()
            ok, out = rung(name, on)
            res.rungs.append({"name": name, "ok": bool(ok), "seconds": round(clock() - t0, 1), "phase": phase, "on": on})
            if not ok:
                return name, out
        return None

    names = rungs_for([s["head"] for s in keep])
    red = run(names, cand, "train")
    if red is None:
        res.landed, res.result = [s["key"] for s in keep], "conflict" if conflicts else "green"
        return res
    res.result = "red"
    rung_name, tails = red[0], {len(keep): red[1]}
    rest_names = names[names.index(rung_name):]
    unresolved = [s["key"] for s in keep]

    def subset(n: int) -> str | None:
        """The candidate of the first n kept steps; None when that merge conflicts (the bisect then cannot judge)."""
        c, bad = merge([s["head"] for s in keep[:n]])
        return None if bad else c

    lo, hi = 1, len(keep)
    while lo < hi:
        mid = (lo + hi) // 2
        c = subset(mid)
        if c is None:
            res.bisect.append(f"prefix {mid}: does not merge again; stopped")
            res.again, res.result = unresolved, "unresolved"
            return res
        res.extra_runs += 1
        r = run([rung_name], c, "bisect")
        res.bisect.append(f"prefix {mid}: {'red' if r else 'green'} on {rung_name}")
        if r:
            hi, tails[mid] = mid, r[1]
        else:
            lo = mid + 1
    culprit = keep[lo - 1]
    back = {"kind": "red", "why": f"the merge train {tid} is red at {rung_name} with this step in it", "findings": f"The merge train {tid} is red at {rung_name} with this step in it.\n{rung_name} on the train candidate:\n{tails[lo]}"}
    rest = [s for i, s in enumerate(keep) if i != lo - 1]
    if not rest:
        res.back[culprit["key"]] = back
        return res
    c, bad = merge([s["head"] for s in rest])
    if bad:
        res.back[culprit["key"]] = back
        res.bisect.append("rest: does not merge without the culprit; stopped")
        res.again, res.result = [s["key"] for s in rest], "unresolved"
        return res
    res.extra_runs += 1
    r = run(rest_names, c, "bisect")
    res.bisect.append(f"rest without {culprit['key']}: {'red on ' + r[0] if r else 'green'}")
    if r and r[0] == rung_name and (same := cases(r[1])) and same == cases(tails[lo]):
        # 2026-11-26, train-20261126-120639: every prefix and the rest were red at swift-tests on the same cases, the land branch's own
        # reds, and the first step was sent back for them. Red with and without the "culprit" alike: no step is to blame, none goes back
        res.bisect.append(f"the rest is red on the same cases as the prefix: the red is not {culprit['key']}'s; no step is sent back")
        res.again, res.result = [s["key"] for s in keep], "unresolved"
        return res
    res.back[culprit["key"]] = back
    if r:  # a second culprit: the budget is spent, so none of the rest lands unjudged
        res.again, res.result = [s["key"] for s in rest], "unresolved"
    else:
        res.landed = [s["key"] for s in rest]
    return res


def cases(out: str) -> frozenset:
    """The failing cases a rung's output names (its `failing: a, b` line, else xcodebuild's own lists); empty when it names none."""
    from fichero_builder import check_tool
    line = next((ln[len("failing: "):] for ln in out.splitlines() if ln.startswith("failing: ")), "")
    named = {x.strip() for x in line.split(", ") if x.strip() and not x.startswith("(")}
    return frozenset(named or check_tool.failing_cases(out))


def against_base(failing: list[str], out: str, base: str, run_base: Callable[[], dict]) -> tuple[bool, str]:
    """The train's swift-tests judged like red-on-base: red only for the cases that fail on the candidate and pass on the base. The
    base's failing cases are run once per base sha and kept (`swift-base-<sha>.json` in the state dir); a base that could not be run
    or does not compile judges nothing, and the candidate's red stands. 2026-11-26: the land branch's own known reds (#7095) made
    every train red for hours."""
    import json

    from fichero_builder import journal
    f = journal.STATE / f"swift-base-{base}.json"
    try:
        known = json.loads(f.read_text())["failing"]
    except (OSError, ValueError, KeyError):
        b = run_base()
        if not b.get("ok") and not b.get("failing"):
            return False, out
        known = [] if b.get("ok") else b["failing"]
        journal.STATE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"failing": known}))
    new = sorted(set(failing) - set(known))
    if not new:
        journal.append("train", state="base-reds", base=base, detail=f"{len(failing)} failing case(s), every one failing on the base too")
        return True, f"swift-tests: green against the base {base[:9]}: its {len(failing)} failing case(s) fail on the base too (known reds)"
    return False, (f"RED: {len(new)} case(s) fail on the candidate and pass on the base {base[:9]} ({len(set(failing) & set(known))} known base reds left out)\n"
                   f"failing: {', '.join(new)}\n" + out)[-3000:]


def budget(n: int) -> int:
    """The most extra runs a train of n steps may spend."""
    return math.ceil(math.log2(n)) + 1 if n > 1 else 0


def swift_changed(files: list[str], build_paths: tuple) -> bool:
    return bool(build_paths) and any(f.startswith(tuple(build_paths)) for f in files)


def names_for(files: list[str], build_paths: tuple, ui_required: Callable[[list[str]], bool]) -> list[str]:
    """The rungs a train over `files` runs: the Swift build and tests when Swift changed, the UI pass when the segment editor did, the unit tier always."""
    swift = swift_changed(files, build_paths)
    return [n for n in RUNG_ORDER if n == "unit" or (n in ("build", "swift-tests") and swift) or (n == "ui" and ui_required(files))]


def _git(repo, *args, cwd=None) -> subprocess.CompletedProcess:
    from fichero_builder import land_tool
    return subprocess.run([land_tool.GIT, "-C", str(cwd or repo), "-c", "user.name=builder", "-c", "user.email=builder@localhost", *args], capture_output=True, text=True)


def git_merge(repo, base: str, heads: list[str], ref: str) -> tuple[str, dict]:
    """Merge `heads` one by one onto `base` in a throwaway worktree of `repo`; a head that conflicts is aborted and named with its files.
    Returns the candidate sha (kept at `ref`) and {head: conflict text}."""
    wt = tempfile.mkdtemp(prefix="train-")
    conflicts: dict = {}
    try:
        r = _git(repo, "worktree", "add", "--detach", wt, base)
        if r.returncode:
            raise RuntimeError(f"no worktree for the train candidate: {r.stderr.strip()[-300:]}")
        for h in heads:
            m = _git(repo, "merge", "--no-ff", "--no-edit", "-m", f"train: merge {h[:9]}", h, cwd=wt)
            if m.returncode:
                files = _git(repo, "diff", "--name-only", "--diff-filter=U", cwd=wt).stdout.split()
                conflicts[h] = f"merging {h[:9]} onto the train's earlier steps conflicts in: {', '.join(files) or '(unknown)'}\n{(m.stdout + m.stderr).strip()[-600:]}"
                _git(repo, "merge", "--abort", cwd=wt)
        cand = _git(repo, "rev-parse", "HEAD", cwd=wt).stdout.strip()
        _git(repo, "update-ref", ref, cand)
        return cand, conflicts
    finally:
        _git(repo, "worktree", "remove", "--force", wt)
        shutil.rmtree(wt, ignore_errors=True)
        _git(repo, "worktree", "prune")


def drop_refs(repo, tid: str) -> None:
    """Delete the `refs/train/<tid>-*` refs git_merge wrote: a ref pins its commits against gc, and nothing reads one after the train."""
    for ref in _git(repo, "for-each-ref", "--format=%(refname)", f"refs/train/{tid}-*").stdout.split():
        _git(repo, "update-ref", "-d", ref)


def real_runners(repo, branch: str, pinned: str, tid: str):
    """(merge, rung, rungs_for) over the engine repo, as the ladder runs them: jailed, in a scratch tree of the candidate."""
    from fichero_builder import check_tool, jail, land_tool
    cfg = check_tool.load(pinned)
    base = land_tool.resolve_branch(repo, branch)
    n = [0]

    def merge(heads):
        n[0] += 1
        return git_merge(repo, base, heads, f"refs/train/{tid}-{n[0]}")

    def files_over(cand: str) -> list[str]:
        return _git(repo, "diff", "--name-only", f"{base}...{cand}").stdout.split()

    def rung(name, cand):
        j = jail.load(pinned)
        if j is not None:
            j.require()
        check_tool._jail_enter(j)
        check_tool._KEY[0] = f"train {tid} {name}"
        files, tree = files_over(cand), None
        try:
            tree = check_tool._scratch_tree(repo, cand, pinned, cfg, overlay=(name != "unit"))
            r = (check_tool.build(tree, files, cfg) if name == "build" else check_tool.swift_tests(tree, cfg) if name == "swift-tests"
                 else check_tool.ui(tree, files, cfg) if name == "ui" else check_tool.unit(tree, files, cfg, everything=True))
        finally:
            check_tool._jail_exit()
            if tree:
                check_tool.drop_tree(repo, tree)
        row = (r.get("results") or [{}])[0]
        out = (r.get("stdout_tail") or row.get("errors") or row.get("stdout_tail") or "")[-3000:]
        if name == "swift-tests" and not r.get("ok") and r.get("failing"):
            return against_base(r["failing"], out, base, lambda: swift_on(base))
        return bool(r.get("ok")), out

    def swift_on(sha: str) -> dict:
        j = jail.load(pinned)
        if j is not None:
            j.require()
        check_tool._jail_enter(j)
        check_tool._KEY[0] = f"train {tid} swift-tests base"
        tree = None
        try:
            tree = check_tool._scratch_tree(repo, sha, pinned, cfg, overlay=True)
            return check_tool.swift_tests(tree, cfg)
        finally:
            check_tool._jail_exit()
            if tree:
                check_tool.drop_tree(repo, tree)

    def rungs_for(heads):
        files = sorted({f for h in heads for f in _git(repo, "diff", "--name-only", f"{base}...{h}").stdout.split()})
        return names_for(files, tuple(cfg.build_paths), check_tool.ui_required)
    return merge, rung, rungs_for
