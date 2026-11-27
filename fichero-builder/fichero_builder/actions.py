"""GitHub Actions as a source for the `unit` rung (spec github-ci.md: ci.builder-reads-actions, ci.actions-or-local).

`fetch` pushes the batch head to the lane's branch on origin, waits for the `tests.yml` run of exactly that sha through the GitHub
CLI and returns what the `Unit tests` step of every `engine` shard job concluded. It runs in the loop, with the loop's credentials, never in
a worker. Anything that is not a finished run of that sha (no run in time, no `gh`, a bad reply, a failed push, a run for another sha)
is `state = "none"` with the reason, and the caller runs the rung on the Macs."""
import json
import subprocess
import time

GH = "gh"            # the tests point this at a fake
POLL_S = 20.0
WORKFLOW = "tests.yml"
ENGINE_JOB = "engine ("  # tests.yml names the unit-tier jobs "engine (N of the twelve)"
SHARDS = 12              # the matrix of tests.yml's engine job; fewer jobs in a run is no usable run
STEPS = {"unit": "Unit tests"}  # guards never come from here: the step runs only check_spec_*.py and the head's own workflow
_MEMO: dict = {}     # (head, branch) -> result, for one ladder: a repeat read of the `unit` rung reuses the run


def reset() -> None:
    _MEMO.clear()


def _gh(*args, timeout_s: float = 120) -> str:
    r = subprocess.run([GH, *args], capture_output=True, text=True, timeout=timeout_s)
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} exited {r.returncode}: {r.stderr.strip()[-200:]}")
    return r.stdout


def lane_branch(root) -> str:
    """The branch the batch head sits on; only a `lane-*` branch is pushed (the workflow runs on those)."""
    r = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True)
    name = r.stdout.strip()
    return name if name.startswith("lane-") else ""


def _push(root, head: str, branch: str) -> None:
    r = subprocess.run(["git", "-C", str(root), "push", "--force", "-q", "origin", f"{head}:refs/heads/{branch}"], capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise RuntimeError(f"push to origin {branch} failed: {r.stderr.strip()[-200:]}")


def _wait(head: str, timeout_s: float) -> dict | None:
    """The finished run of exactly `head`, or None at the timeout. A run listed for another sha is never taken."""
    end = time.monotonic() + timeout_s
    while True:
        runs = json.loads(_gh("run", "list", "--commit", head, "--workflow", WORKFLOW, "--json", "databaseId,status,conclusion,headSha") or "[]")
        mine = [r for r in runs if r.get("headSha") == head]
        done = [r for r in mine if r.get("status") == "completed"]
        if done:
            return done[0]
        if time.monotonic() >= end:
            return None
        time.sleep(POLL_S)


def _parts(run_id) -> dict:
    jobs = json.loads(_gh("api", f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs"))["jobs"]
    engine = [j for j in jobs if j.get("name", "").startswith(ENGINE_JOB)]  # tests.yml also has contracts and builder jobs: read per job
    if len(engine) < SHARDS:
        raise RuntimeError(f"run {run_id} has {len(engine)} {ENGINE_JOB!r} jobs, not {SHARDS}")
    out = {}
    for rung, name in STEPS.items():
        concl = []
        for j in engine:
            step = [s.get("conclusion") for s in j.get("steps", []) if s.get("name") == name]
            if not step:
                raise RuntimeError(f"run {run_id}: job {j.get('name')!r} has no step {name!r}")
            concl.append(step[0])
        bad = sorted({c or "none" for c in concl if c != "success"})
        out[rung] = {"ok": not bad, "step": name, "conclusion": ", ".join(bad) or "success"}
    return out


def _failing(run_id) -> str:
    try:
        return "\n".join(_gh("run", "view", str(run_id), "--log-failed", timeout_s=120).splitlines()[-60:])
    except (RuntimeError, subprocess.SubprocessError, OSError) as e:
        return f"(the failing lines could not be read: {e})"


def fetch(root, head: str, branch: str, timeout_s: float) -> dict:
    """{"state": "green"|"red"|"none", "run": id, "parts": {rung: {ok, step, conclusion}}, "lines": failing lines, "why": reason when none}."""
    key = (head, branch)
    if key in _MEMO:
        return _MEMO[key]
    try:
        if not branch:
            raise RuntimeError("the batch is not on a lane-* branch")
        _push(root, head, branch)
        run = _wait(head, timeout_s)
        if run is None:
            res = {"state": "none", "why": f"no finished Actions run of {head[:9]} within {timeout_s:g} s"}
        else:
            parts = _parts(run["databaseId"])
            green = all(p["ok"] for p in parts.values())
            res = {"state": "green" if green else "red", "run": run["databaseId"], "parts": parts,
                   "lines": "" if green else _failing(run["databaseId"])}
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError) as e:
        res = {"state": "none", "why": f"Actions not usable: {e}"}
    _MEMO[key] = res  # a missing run too: the second rung must not wait the timeout again
    return res
