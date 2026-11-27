"""GitHub Actions as a source for the `unit` rung (spec github-ci.md: ci.builder-reads-actions, ci.actions-or-local).

`fetch` pushes the batch head to the lane's branch on origin through `ci.Hosted`, waits with `ci.wait` for the twelve `engine (N/12)`
check runs of exactly that sha and returns what the `Unit tests` step of every one of those jobs concluded. It runs in the loop, with
the loop's credentials, never in a worker. Anything that is not twelve finished jobs of that sha (none in time, no `gh`, a bad reply, a
failed push) is `state = "none"` with the reason, and the caller runs the rung on the Macs."""
import json
import subprocess
import time

from fichero_builder import ci

POLL_S = 20.0
SHARDS = 12  # the matrix of tests.yml's engine job; fewer finished jobs is no usable run
NAMES = tuple(f"engine ({n}/{SHARDS})" for n in range(1, SHARDS + 1))  # the check-run names tests.yml gives its unit-tier jobs
STEP = "Unit tests"  # guards never come from here: the `Spec guards` step runs only check_spec_*.py and the head's own workflow


def lane_branch(root, lane: str, head: str) -> str:
    """`lane-<lane>` when `head` is the tip of `work-<lane>` in `root` (do_fetch's ref of that lane's worktree), else ''. The target comes
    from the lane the loop is checking, never from the HEAD of `root`: one engine repo judges every lane, and its HEAD may sit on another's."""
    branch = f"lane-{lane}"
    if not lane or lane.startswith("-") or subprocess.run(["git", "check-ref-format", "--branch", branch], capture_output=True).returncode:
        return ""
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", f"refs/heads/work-{lane}^{{commit}}"], capture_output=True, text=True)
    return branch if r.stdout.strip() == head else ""


def fetch(root, head: str, branch: str, timeout_s: float) -> dict:
    """{"state": "green"|"red"|"none", "run": id, "ok", "conclusion", "lines": failing lines, "why": reason when none}."""
    h = ci.Hosted(ci.Cfg(wait_min=timeout_s / 60, start_min=timeout_s / 60), str(root))
    try:
        if not branch:
            raise RuntimeError("no lane branch to push: the head is not the tip of the checked lane's work-<lane> ref")
        if err := h.push(head, branch):
            raise RuntimeError(f"push to origin {branch} failed: {err}")
        got, end = ci.wait(h, head, NAMES, h.cfg, clock=time.monotonic, poll_s=POLL_S)
        if end:
            return {"state": "none", "why": f"{len(got)} of {SHARDS} engine jobs of {head[:9]} finished within {timeout_s:g} s ({end})"}
        run_ids = {c["run_id"] for c in got.values()}
        if len(run_ids) != 1 or "" in run_ids:
            raise RuntimeError(f"the engine jobs of {head[:9]} are not one Actions run: {sorted(run_ids)}")
        run = run_ids.pop()
        jobs = {j["name"]: j for j in h.jobs(run) if j["name"] in NAMES}
        if missing := [n for n in NAMES if n not in jobs]:
            raise RuntimeError(f"run {run} lacks the jobs {missing}")
        concl = {}
        for n, j in jobs.items():
            step = [s["conclusion"] for s in j["steps"] if s["name"] == STEP]
            if not step:
                raise RuntimeError(f"run {run}: job {n!r} has no step {STEP!r}")
            concl[n] = step[0]
        red = [jobs[n] for n, c in concl.items() if c != "success"]
        bad = sorted({concl[j["name"]] or "none" for j in red})
        lines = "\n".join("\n".join(h.failed_log(run, j["id"]).splitlines()[-60:]) for j in red)
        return {"state": "red" if red else "green", "run": run, "ok": not red, "conclusion": ", ".join(bad) or "success", "lines": lines}
    except (RuntimeError, ci.Down, subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        return {"state": "none", "why": f"Actions not usable: {e}"}
