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
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

RUNG_ORDER = ("build", "swift-tests", "ui", "guards", "whole-tests", "unit", "security", "perf")
KEYS = {"enabled", "min_steps", "max_wait_min", "max_run_min", "max_steps", "overlap", "whole_tests", "security_perf", "side_by_side"}
SWIFT_CHAIN = ("build", "swift-tests", "ui")  # local.train.rungs-side-by-side: the rungs that need the app build; the rest run beside them
CAND: dict = {}  # tid -> its first candidate merge, once made: a second train's base (local.train.second-train-on-the-first)


@dataclass(frozen=True)
class Cfg:
    enabled: bool = True
    min_steps: int = 4
    max_wait_min: float = 45.0
    max_run_min: float = 30.0  # owner 2026-11-26: a train never holds its steps longer; past it, it stops and they wait again
    overlap: int = 1  # local.train.second-train-on-the-first: 2 = a second train may run on the first one's candidate; 1 = one at a time
    max_steps: int = 6  # local.train.size-follows-the-last-result: the most steps one train takes; its size halves after a red, doubles after a green
    whole_tests: bool = False  # local.check.red-on-base-changed-tests-only: the steps owe their whole-tests dirs to the train, which runs them once
    security_perf: bool = False  # local.train.security-and-perf-once: a step runs the added-line lints only; the train the scanners and perf
    side_by_side: bool = False  # local.train.rungs-side-by-side: the rungs with no app build run while the build and the Swift tests run


def load(rules: dict) -> Cfg:
    """`[train]` of the rules; a missing table is the defaults, an unknown key or a bad value refuses."""
    t = rules.get("train", {})
    if unknown := sorted(set(t) - KEYS):
        raise ValueError(f"harness.toml [train]: unknown keys {unknown}")
    cfg = Cfg(enabled=bool(t.get("enabled", True)), min_steps=int(t.get("min_steps", 4)), max_wait_min=float(t.get("max_wait_min", 45)),
              max_run_min=float(t.get("max_run_min", 30)), max_steps=int(t.get("max_steps", 6)), overlap=int(t.get("overlap", 1)),
              whole_tests=bool(t.get("whole_tests", False)), security_perf=bool(t.get("security_perf", False)),
              side_by_side=bool(t.get("side_by_side", False)))
    if cfg.overlap not in (1, 2):
        raise ValueError("harness.toml [train]: overlap is 1 or 2 (never more than two trains)")
    if cfg.min_steps < 1 or cfg.max_steps < 1 or cfg.max_wait_min <= 0 or cfg.max_run_min <= 0:
        raise ValueError("harness.toml [train]: min_steps and max_steps must be at least 1, max_wait_min and max_run_min above 0")
    return cfg


def next_size(size: int, result: str, cfg: Cfg) -> int:
    """local.train.size-follows-the-last-result (2026-11-26: trains of 4, 6 and 8 all failed; only trains of 1 were green): a train
    that is green (a dropped conflict included) doubles the size up to max_steps; red, unresolved, timed out or an error halves it."""
    return min(cfg.max_steps, size * 2) if result in ("green", "conflict") else max(1, size // 2)


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
    ci: dict = field(default_factory=dict)       # local.ci.train-lands-on-green-checks: the hosted checks of the candidate


class OutOfTime(Exception):
    pass


CANCEL: dict = {}  # tid -> () -> reason ("" = go on): a second train stops at its next run once its base train failed


def _stop(res, t_start, deadline, clock) -> None:
    if deadline is not None and clock() > deadline:
        raise OutOfTime(res, t_start)
    if (f := CANCEL.get(res.id)) and (why := f()):
        raise OutOfTime(res, t_start, why)


def run_train(steps: list[dict], *, merge: Callable, rung: Callable, rungs_for: Callable, tid: str, clock: Callable = time.time,
              deadline: float | None = None, touches_swift: Callable[[str], bool] | None = None,
              on_candidate: Callable[[str], None] | None = None, touches: Callable[[str, str, frozenset], bool] | None = None,
              side_by_side: bool = False) -> Result:
    """`steps`: [{key, head}] in queue order. `merge(heads) -> (candidate sha, {head: conflict text})`; `rung(name, candidate) ->
    (ok, output)` (`rung(name, candidate, only=cases)` for a targeted Swift run); `rungs_for(heads) -> [rung names]`, in RUNG_ORDER.
    `deadline` (a clock value): no run starts past it, and the train ends `timeout` with every step waiting again. `touches_swift(head)`:
    a swift-tests red that names new cases looks for its step among the Swift steps only, newest first, never by prefixes.
    `on_candidate(sha)` hears the candidate before any rung runs (local.ci.train-candidate-on-a-branch pushes it). `touches(rung, head,
    names)`: a whole-tests or guards red naming cases or guards is searched among the steps whose diff touches them (red-goes-to-its-step)."""
    try:
        return _run_train(steps, merge, rung, rungs_for, tid, clock, deadline, touches_swift, on_candidate, touches, side_by_side)
    except OutOfTime as e:
        res = e.args[0]
        res.again, res.result = [s["key"] for s in steps if s["key"] not in res.back], "timeout" if len(e.args) < 3 else "cancelled"
        res.bisect.append(f"stopped: past the train's time limit ({'%.0f' % (clock() - e.args[1])} s in)" if len(e.args) < 3
                          else f"cancelled {'%.0f' % (clock() - e.args[1])} s in: {e.args[2]}")
        return res


def _run_train(steps, merge, rung, rungs_for, tid, clock, deadline, touches_swift, on_candidate=None, touches=None, side_by_side=False) -> Result:
    t_start = clock()
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
    if on_candidate is not None:
        on_candidate(cand)

    def run(names: list[str], on: str, phase: str) -> tuple[str, str] | None:
        """The first red (name, output) of `names` on `on`, else None; one row each."""
        for name in names:
            _stop(res, t_start, deadline, clock)
            t0 = clock()
            ok, out = rung(name, on)
            res.rungs.append(_row(rung, name, ok, out, round(clock() - t0, 1), phase, on))
            if not ok:
                return name, out
        return None

    def side(names: list[str], on: str, phase: str) -> tuple[str, str] | None:
        """local.train.rungs-side-by-side: the Swift chain and the other rungs at once, each chain stopping at its own first red; the
        red that counts is the first in RUNG_ORDER. The wall time is the longer chain; a chain past the deadline ends the train."""
        chains = [[n for n in names if n in SWIFT_CHAIN], [n for n in names if n not in SWIFT_CHAIN]]
        reds, late = [None, None], []

        def go(i):
            try:
                reds[i] = run(chains[i], on, phase)
            except OutOfTime as e:
                late.append(e)
        ts = [threading.Thread(target=go, args=(i,), name=f"train-{tid}-{i}") for i, c in enumerate(chains) if c]
        [t.start() for t in ts]
        [t.join() for t in ts]
        if late:
            raise late[0]
        got = [r for r in reds if r]
        return min(got, key=lambda r: RUNG_ORDER.index(r[0]) if r[0] in RUNG_ORDER else len(RUNG_ORDER)) if got else None

    names = rungs_for([s["head"] for s in keep])
    red = (side if side_by_side else run)(names, cand, "train")
    if red is None:
        res.landed, res.result = [s["key"] for s in keep], "conflict" if conflicts else "green"
        return res
    res.result = "red"
    rung_name, tails = red[0], {len(keep): red[1]}
    rest_names = names[names.index(rung_name):]
    unresolved = [s["key"] for s in keep]
    new = cases(red[1])
    if rung_name == "swift-tests" and new and touches_swift is not None:
        return _swift_search(res, keep, new, red[1], rest_names, merge, rung, tid, clock, deadline, t_start, touches_swift, run)
    if rung_name == "security" and (heads := _named_heads(red[1])):  # local.train.security-and-perf-once: back to the step that added the line
        for s in keep:
            if s["head"] in heads:
                res.back[s["key"]] = {"kind": "red", "why": f"the merge train {tid}'s security scan names a line this step added",
                                      "findings": f"The merge train {tid}'s security scan over its candidate names lines this step added:\n{red[1]}"}
        if res.back:
            res.landed = [s["key"] for s in keep if s["key"] not in res.back]
            res.bisect.append(f"security: sent back {', '.join(res.back)}; the rest go on")
            return res
    if rung_name in ("whole-tests", "guards") and new and touches is not None:
        return _swift_search(res, keep, new, red[1], rest_names, merge, rung, tid, clock, deadline, t_start,
                             lambda h: touches(rung_name, h, new), run, name=rung_name)

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


def _swift_search(res, keep, new, tail, rest_names, merge, rung, tid, clock, deadline, t_start, touches_swift, run, name: str = "swift-tests") -> Result:
    """2026-11-26 (owner: an 88-minute merge is crazy): a train red at swift-tests on cases that pass on its base is searched for the
    step that adds them, never by running the whole suite over each prefix: each step that touches Swift, newest first, on the base
    alone, running only the new cases; the first that fails one is sent back and the rest go on as after any bisect.
    local.train.red-goes-to-its-step: a whole-tests or guards red (`name`) is searched the same way over the steps that touch the
    failing tests or guards; when none fails alone, the newest of them goes back with the output and the others' names."""
    culprit, others = None, []
    touching = [s for s in keep if touches_swift(s["head"])]
    for s in reversed(touching):
        _stop(res, t_start, deadline, clock)
        c, bad = merge([s["head"]])
        if bad:
            continue
        res.extra_runs += 1
        t0 = clock()
        ok, out = rung(name, c, only=sorted(new))
        res.rungs.append(_row(rung, name, ok, out, round(clock() - t0, 1), "search", c))
        res.bisect.append(f"{s['key']} alone, the {len(new)} new case(s): {'green' if ok else 'red'}")
        if not ok:
            culprit = s
            break
    if culprit is None and (name == "swift-tests" or not touching):
        res.bisect.append(f"no {'Swift ' if name == 'swift-tests' else ''}step alone fails the new {'cases' if name != 'guards' else 'guard reds'}: "
                          "they come from the steps together; none is sent back")
        res.again, res.result = [s["key"] for s in keep], "unresolved"
        return res
    if culprit is None:  # only two (or more) together break it: the newest goes back, naming the others
        culprit, others = touching[-1], [s["key"] for s in touching[:-1]]
        res.bisect.append(f"no step alone fails it: {culprit['key']}, the newest that touches it, goes back naming {', '.join(others) or 'no other'}")
    what = "alone on the land branch fails" if not others else "and " + ", ".join(others) + " together fail"
    res.back[culprit["key"]] = {"kind": "red", "why": f"the merge train {tid} is red at {name} with this step in it",
                                "findings": f"The merge train {tid} is red at {name}: this step {what} "
                                            f"{', '.join(sorted(new))}, which pass on the land branch.\n{name} on the train candidate:\n{tail}"}
    rest = [s for s in keep if s is not culprit]
    if not rest:
        return res
    c, bad = merge([s["head"] for s in rest])
    if bad:
        res.bisect.append("rest: does not merge without the culprit; stopped")
        res.again, res.result = [s["key"] for s in rest], "unresolved"
        return res
    res.extra_runs += 1
    r = run(rest_names, c, "bisect")
    res.bisect.append(f"rest without {culprit['key']}: {'red on ' + r[0] if r else 'green'}")
    if r:
        res.again, res.result = [s["key"] for s in rest], "unresolved"
    else:
        res.landed = [s["key"] for s in rest]
    return res


def search(res: Result, steps: list[dict], new: list[str], merge: Callable, rung: Callable, touches: Callable, clock: Callable = time.time,
           deadline: float | None = None) -> Result:
    """local.ci.red-is-retried-once-and-judged-against-base -> local.train.red-goes-to-its-step: hosted CI's red cases (green on the
    base) are searched on the local runners among the train's cleared steps, as a whole-tests red is."""
    keep = [s for s in steps if s["key"] in res.landed]
    res.landed, res.result, t_start = [], "red", clock()

    def run(names, on, phase):
        for name in names:
            t0 = clock()
            ok, out = rung(name, on)
            res.rungs.append(_row(rung, name, ok, out, round(clock() - t0, 1), phase, on))
            if not ok:
                return name, out
        return None
    return _swift_search(res, keep, frozenset(new), "hosted CI: " + ", ".join(new), ["whole-tests"], merge, rung, res.id, clock, deadline, t_start,
                         lambda h: touches("whole-tests", h, frozenset(new)), run, name="whole-tests")


def _named_heads(out: str) -> set:
    """The heads a train rung's `added by: <head>, <head>` line names (the security scan's findings, by the step that added the line)."""
    line = next((ln[len("added by: "):] for ln in out.splitlines() if ln.startswith("added by: ")), "")
    return {x.strip() for x in line.split(",") if x.strip()}


def cases(out: str) -> frozenset:
    """The failing cases a rung's output names (its `failing: a, b` line, else xcodebuild's own lists); empty when it names none."""
    from fichero_builder import check_tool
    line = next((ln[len("failing: "):] for ln in out.splitlines() if ln.startswith("failing: ")), "")
    named = {x.strip() for x in line.split(", ") if x.strip() and not x.startswith("(")}
    return frozenset(named or check_tool.failing_cases(out))


def _row(rung, name: str, ok, out: str, seconds: float, phase: str, on: str) -> dict:
    """One rung row of the train: what the rung said about itself (`rung.last`: the Swift selection, the base run's seconds), and a
    red's last lines, so a slow or red train can be read from the journal alone (2026-11-26: a 1651 s swift-tests row said nothing)."""
    row = {"name": name, "ok": bool(ok), "seconds": seconds, "phase": phase, "on": on, **(getattr(rung, "last", None) or {})}
    if hasattr(rung, "last"):
        rung.last = {}
    if not ok:
        row["tail"] = (out or "")[-800:]
    return row


def suites_of(failing: list[str], target: str) -> list[str] | None:
    """The `<target>/<suite>` ids of failing cases (`-[Target.Suite test]`, `Target/Suite/test()`, `Suite/test()`), so the base runs
    only those suites; None when a name cannot be read (the base then runs the candidate's selection)."""
    out = set()
    for f in failing:
        m = re.match(r"-\[(?:[\w]+\.)?(\w+) \w+\]$", f) or re.match(r"(?:([\w]+)/)?(\w+)/\w+", f)
        if not m:
            return None
        out.add(f"{target}/{m.group(1) if f.startswith('-[') else m.group(2)}")
    return sorted(out)


def against_base(failing: list[str], out: str, base: str, run_base: Callable[[], dict], only: list[str] | tuple = (), label: str = "swift-tests") -> tuple[bool, str]:
    """The train's swift-tests judged like red-on-base: red only for the cases that fail on the candidate and pass on the base. The
    base's failing cases are run once per base sha and kept (`swift-base-<sha>.json` in the state dir); a base that could not be run
    or does not compile judges nothing, and the candidate's red stands. 2026-11-26: the land branch's own known reds (#7095) made
    every train red for hours."""
    import json

    from fichero_builder import journal
    import hashlib
    sel = hashlib.sha256("\n".join(sorted(only)).encode()).hexdigest()[:12] if only else "all"  # the base runs the same selection
    f = journal.STATE / f"{'swift' if label == 'swift-tests' else label}-base-{base}-{sel}.json"
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
        return True, f"{label}: green against the base {base[:9]}: its {len(failing)} failing case(s) fail on the base too (known reds)"
    return False, (f"RED: {len(new)} case(s) fail on the candidate and pass on the base {base[:9]} ({len(set(failing) & set(known))} known base reds left out)\n"
                   f"failing: {', '.join(new)}\n" + out)[-3000:]


def guards_against_base(cand: dict, run_base: Callable[[list[str]], dict]) -> tuple[bool, str]:
    """local.train.guards-on-candidate: the guards the train's combined diff touches, judged on its candidate; a guard red there counts
    only when it is green on the train's base (`run_base(names)` runs just those there). Two steps each green alone that break a
    guard together make the train red at `guards`, which the same-file rule used to stop by never checking them at once."""
    reds = [x["name"] for x in cand.get("results") or [] if not x.get("ok")]
    if cand.get("ok") or not reds:
        return True, f"guards: {sum(1 for x in cand.get('results') or [] if not x.get('skipped'))} run on the candidate, green"
    on_base = {x["name"] for x in run_base(reds).get("results") or [] if not x.get("ok")}
    new = [n for n in reds if n not in on_base]
    if not new:
        return True, f"guards: {', '.join(reds)} red on the candidate and on the base too (the land branch's own)"
    tails = "\n".join(f"{x['name']}: {((x.get('stdout_tail') or '') + (x.get('stderr_tail') or '')).strip()[-600:]}"
                      for x in cand["results"] if x.get("name") in new)
    return False, f"RED: {len(new)} guard(s) red on the candidate and green on the base\nfailing: {', '.join(new)}\n{tails}"[-3000:]


def budget(n: int) -> int:
    """The most extra runs a train of n steps may spend."""
    return math.ceil(math.log2(n)) + 1 if n > 1 else 0


def swift_changed(files: list[str], build_paths: tuple) -> bool:
    return bool(build_paths) and any(f.startswith(tuple(build_paths)) for f in files)


def names_for(files: list[str], build_paths: tuple, ui_required: Callable[[list[str]], bool], whole: tuple = (), scans: bool = False) -> list[str]:
    """The rungs a train over `files` runs: the Swift build and tests when Swift changed, the UI pass when the segment editor did, the
    whole-tests dirs its steps owe when there are any, the unit tier always, and with `scans` the security scanners and perf, last."""
    swift = swift_changed(files, build_paths)
    return [n for n in RUNG_ORDER if n in ("guards", "unit") or (n in ("build", "swift-tests") and swift) or (n == "ui" and ui_required(files))
            or (n == "whole-tests" and bool(whole)) or (n in ("security", "perf") and scans)]


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


def real_runners(repo, branch: str, pinned: str, tid: str, deadline: float | None = None, base: str = "", scans: bool = False):
    """(merge, rung, rungs_for) over the engine repo, as the ladder runs them: jailed, in a scratch tree of the candidate. `rung` carries
    `touches_swift(head)` for the Swift search; a swift-tests run is cut at `deadline`."""
    from fichero_builder import check_tool, jail, land_tool
    cfg = check_tool.load(pinned)
    base = base or land_tool.resolve_branch(repo, branch)  # a second train's base is the first one's candidate
    n = [0]

    def merge(heads):
        n[0] += 1
        cand, bad = git_merge(repo, base, heads, f"refs/train/{tid}-{n[0]}")
        if cand:
            CAND.setdefault(tid, cand)
        return cand, bad

    def files_over(cand: str) -> list[str]:
        return _git(repo, "diff", "--name-only", f"{base}...{cand}").stdout.split()

    def left() -> float | None:
        return None if deadline is None else max(60.0, deadline - time.time())

    def rung(name, cand, only=()):
        rung.last = {}
        j = jail.load(pinned)
        if j is not None:
            j.require()
        check_tool._jail_enter(j)
        check_tool._KEY[0] = f"train {tid} {name}"
        files, tree = files_over(cand), None
        try:
            tree = check_tool._scratch_tree(repo, cand, pinned, cfg, overlay=(name not in ("unit", "whole-tests")))
            if name == "whole-tests" and only:  # the step search: only those cases, on one step alone
                r = check_tool.green_runs(tree, list(only), (), cfg, 1800)
                return bool(r.get("ok")), "\n".join((x.get("stdout_tail") or "") for x in r.get("runs") or [r])[-3000:]
            if name == "guards" and only:
                g = guards_on(cand, list(only))
                return bool(g.get("ok")), "\n".join(f"{x['name']}: {'ok' if x.get('ok') else 'red'}" for x in g.get("results") or [])
            if name == "whole-tests":
                return whole_on(tree, cand, files)
            if name in ("security", "perf"):
                return scans_on(name, tree, cand, files)
            if name == "guards":
                return guards_against_base(check_tool.guards(tree, replace(cfg, guards_by_diff=True), files),
                                           lambda reds: guards_on(base, reds))
            sel = list(only) or (check_tool.swift_affected(tree, files, cfg) if name == "swift-tests" else None)
            if name == "swift-tests":
                rung.last = {"selection": f"{len(sel)} suite(s)" if sel else f"whole: {check_tool.swift_whole_why(files, cfg) or f'more than {check_tool.SWIFT_SELECT_MAX} suites'}"}
            if sel == []:
                return True, "swift-tests: no Swift test suite the train's Swift diff can affect (the nightly runs the whole suite)"
            r = (check_tool.build(tree, files, cfg) if name == "build" else check_tool.swift_tests(tree, cfg, sel or (), left()) if name == "swift-tests"
                 else check_tool.ui(tree, files, cfg) if name == "ui" else check_tool.unit(tree, files, cfg, everything=True))
        finally:
            check_tool._jail_exit()
            if tree:
                check_tool.drop_tree(repo, tree)
        row = (r.get("results") or [{}])[0]
        out = (r.get("stdout_tail") or row.get("errors") or row.get("stdout_tail") or "")[-3000:]
        if name == "swift-tests" and not r.get("ok") and r.get("failing"):
            on_base = (cfg.swift_test_target and suites_of(r["failing"], cfg.swift_test_target)) or sel or ()

            def timed():
                t0 = time.time()
                try:
                    return swift_on(base, on_base)
                finally:
                    rung.last = {**rung.last, "base_seconds": round(time.time() - t0, 1), "base_selection": f"{len(on_base)} suite(s)" if on_base else "whole"}
            return against_base(r["failing"], out, base, timed, on_base)
        return bool(r.get("ok")), out

    def whole_on(tree, cand: str, files: list[str]) -> tuple[bool, str]:
        """local.train.whole-tests-against-base: every [check.whole_tests] dir the combined diff owes, once on the candidate; a red is
        judged on the train's base, kept per base sha and selection: red only for cases that fail here and pass there."""
        from fichero_builder import ci
        dirs = check_tool._whole_tests(files, cfg)
        rung.last = {"dirs": list(dirs)}
        r = check_tool.green_runs(tree, [], dirs, cfg, 1800)
        out = "\n".join((x.get("stdout_tail") or "") + (x.get("stderr_tail") or "") for x in r.get("runs") or [r])[-3000:]
        if r.get("ok"):
            return True, f"whole-tests: {len(dirs)} dir(s) green on the candidate"
        failing = ci.failing(out)
        if not failing:
            return False, out  # no case named (a collection error): the red stands

        def on_base() -> dict:
            btree = None
            try:
                btree = check_tool._scratch_tree(repo, base, pinned, cfg, overlay=False)
                b = check_tool.green_runs(btree, [], dirs, cfg, 1800)
                return {"ok": bool(b.get("ok")), "failing": ci.failing("\n".join((x.get("stdout_tail") or "") for x in b.get("runs") or [b]))}
            finally:
                if btree:
                    check_tool.drop_tree(repo, btree)
        return against_base(failing, out, base, on_base, dirs, label="whole-tests")

    def scans_on(name: str, tree, cand: str, files: list[str]) -> tuple[bool, str]:
        """local.train.security-and-perf-once: the security scanners and perf, once over base...candidate. A scanner finding names the
        head of each step whose diff added that line (`added by:`); perf stays report-only and names the steps touching what it measured."""
        from fichero_builder import perf_rung
        if name == "perf":
            r = check_tool.perf(tree, base, files, cfg)
            touching = [h for h in heads_now if any(f.startswith(perf_rung.ENGINE_PATHS + perf_rung.APP_PATHS) for f in _git(repo, "diff", "--name-only", f"{base}...{h}").stdout.split())]
            rung.last = {"steps": touching}
            return True, f"perf (report-only) for train {tid}; steps touching what it measured: {', '.join(h[:9] for h in touching) or 'none'}\n{r.get('stdout_tail') or ''}"[-3000:]
        r = check_tool.security(tree, base, cand, files, cfg)
        out = r.get("stdout_tail") or ""
        if r.get("ok"):
            return True, out
        blamed = set()
        for m in re.finditer(r"(\S+?):(\d+)\b", out):  # a finding's `where`: file:line on the candidate
            text = (_git(repo, "show", f"{cand}:{m.group(1)}").stdout.splitlines() or [""])[max(0, int(m.group(2)) - 1):int(m.group(2))]
            for h in heads_now:
                if text and any(f == m.group(1) and t == text[0] for f, _n, t in check_tool._added_lines(repo, base, h, (m.group(1),))):
                    blamed.add(h)
        return False, (f"added by: {', '.join(sorted(blamed))}\n" if blamed else "") + out

    heads_now: list = []

    def guards_on(sha: str, names: list[str]) -> dict:
        """Only `names` of the guards, over a scratch tree of `sha` (the train's base)."""
        tree = None
        try:
            tree = check_tool._scratch_tree(repo, sha, pinned, cfg)
            every = {p.stem for p in Path(tree).glob(cfg.guard_glob)} if cfg.guard_glob else set()
            return check_tool.guards(tree, replace(cfg, guard_skip=frozenset(every - set(names)), min_guards=0))
        finally:
            if tree:
                check_tool.drop_tree(repo, tree)

    def touches_swift(head: str) -> bool:
        return any(f.endswith(".swift") and (not cfg.build_paths or f.startswith(tuple(cfg.build_paths)))
                   for f in _git(repo, "diff", "--name-only", f"{base}...{head}").stdout.split())
    rung.touches_swift = touches_swift

    def touches(name: str, head: str, names) -> bool:
        """local.train.red-goes-to-its-step: the step's diff touches a failing test's directory or a [check.whole_tests] prefix that
        runs it (whole-tests), or a failing guard's inputs or script (guards; a guard with no declared inputs reads everything)."""
        files = _git(repo, "diff", "--name-only", f"{base}...{head}").stdout.split()
        if name == "guards":
            return any(not cfg.guard_inputs.get(g) or any(f.startswith(tuple(cfg.guard_inputs[g])) or Path(f).stem == g for f in files) for g in names)
        tests = {n.split("::")[0] for n in names}
        dirs = {str(Path(x).parent) + "/" for x in tests}
        prefixes = [p for p, v in cfg.whole_tests.items() if any(x.startswith(d) for d in ([v] if isinstance(v, str) else v) for x in tests)]
        return any(f.startswith(tuple(dirs)) or f.startswith(tuple(prefixes)) or f in tests for f in files)
    rung.touches = touches

    def swift_on(sha: str, sel=()) -> dict:
        j = jail.load(pinned)
        if j is not None:
            j.require()
        check_tool._jail_enter(j)
        check_tool._KEY[0] = f"train {tid} swift-tests base"
        tree = None
        try:
            tree = check_tool._scratch_tree(repo, sha, pinned, cfg, overlay=True)
            return check_tool.swift_tests(tree, cfg, sel, left())
        finally:
            check_tool._jail_exit()
            if tree:
                check_tool.drop_tree(repo, tree)

    def rungs_for(heads):
        heads_now[:] = list(heads)
        files = sorted({f for h in heads for f in _git(repo, "diff", "--name-only", f"{base}...{h}").stdout.split()})
        return names_for(files, tuple(cfg.build_paths), check_tool.ui_required, check_tool._whole_tests(files, cfg), scans)
    return merge, rung, rungs_for
