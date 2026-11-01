"""`builder work`: the chain a person ran by hand, as ONE process (dev-workflows.tool.work).

run -> patches -> fetch -> check -> review -> land, each step a journal row (event "work": step, ok, detail). It stops with
`QUESTION: <why>` (exit 2) on a worker that did not finish, a red check, a NOT READY review or a refused land, and it only
prints the push line; nothing here pushes. Each step is a module function so a test replaces it."""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

from fichero_builder import check_tool, jail, journal, land_tool, models

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _jail(a):
    j = jail.load(a.pinned)
    if j is None or not j.user or not j.workroot:
        raise jail.JailMissing("no [jail] user and workroot in the rules file: the worker side of the chain has nowhere to run")
    return j


def shared_state(a) -> Path:
    """`<[jail].workroot>/state`: the one folder both users read (the worker's journal, patches and bundle live here)."""
    return Path(_jail(a).workroot) / "state"


def as_worker(a, script: str) -> subprocess.CompletedProcess:
    """`script` as the jail user from the workroot: the owner cannot read the worker's session files or git in its tree.
    The one place the chain crosses the user boundary; a test replaces it."""
    j = _jail(a)
    return subprocess.run([j.sudo, "-n", "-H", "-u", j.user, "sh", "-c", f"cd {shlex.quote(j.workroot)} && {script}"],
                          capture_output=True, text=True)


def _shared_rows(a) -> list[dict]:
    p = shared_state(a) / "journal.jsonl"
    rows = []
    for x in p.read_text().splitlines() if p.exists() else []:  # the worker writes this file: skip what is not a row
        try:
            r = json.loads(x)
        except ValueError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def do_run(a, model: str) -> str:
    """`builder run` as the jail user; the end is read from the SHARED journal (the cost row, and the worker row's worktree)."""
    j = _jail(a)
    j.require()
    before = len(_shared_rows(a))
    py = check_tool.load(a.pinned).python or sys.executable
    pkg = Path(__file__).resolve().parents[1]
    cmd = " ".join(["PYTHONPATH=" + shlex.quote(str(pkg)), shlex.quote(py), "-m fichero_builder run",
                    *(f"{k} {shlex.quote(str(v))}" for k, v in (
                        ("--worktree", a.worktree), ("--brief", a.brief), ("--root", a.root), ("--name", a.name), ("--model", model),
                        ("--kind", a.kind), ("--session", a.session), ("--tick", a.tick), ("--state", shared_state(a))))])
    r = as_worker(a, cmd)
    if r.stdout.strip():
        print(r.stdout.strip())
    new = _shared_rows(a)[before:]
    mine = [x for x in new if x.get("task") == a.name]
    if not any(x.get("event") == "worker" and x.get("worktree") == str(a.worktree) for x in mine):
        raise RuntimeError(f"the worker never started (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-300:] or 'no output'}")
    ends = [x["end"] for x in mine if x.get("event") == "cost" and x.get("end") and x["end"] != "handoff"]
    if not ends:
        raise RuntimeError(f"the worker left no end row in the shared journal (exit {r.returncode})")
    return ends[-1]


def do_export(a, branch: str) -> int:
    """The worktree's commits over origin/<land branch> as patch files; the count (0 = nothing to land)."""
    out = shared_state(a) / f"patches-{a.name}"
    g = shlex.quote(jail_git())
    r = as_worker(a, f"mkdir -p {shlex.quote(str(out))} && {g} -C {shlex.quote(str(a.worktree))} format-patch -o {shlex.quote(str(out))} "
                     f"origin/{shlex.quote(branch)}")
    return len(r.stdout.split()) if r.returncode == 0 else 0


def jail_git() -> str:
    return jail.real_git()


def do_fetch(a, repo: str, branch: str) -> str:
    """Bring the worktree's commits into the engine-owned repo as refs/heads/work-<name>; its head sha ('' = failed).
    The worker's branch NAME is never passed to git on the owner's side (a name like `--upload-pack=...` ran a command):
    the worktree makes a bundle of origin/<branch>..HEAD and the owner fetches HEAD from that file."""
    state = shared_state(a)
    bundle = state / f"work-{a.name}.bundle"
    q = shlex.quote
    r = as_worker(a, f"mkdir -p {q(str(state))} && rm -f {q(str(bundle))} && {q(jail_git())} -C {q(str(a.worktree))} bundle create "
                     f"{q(str(bundle))} origin/{q(branch)}..HEAD && chmod a+r {q(str(bundle))}")
    ref = f"refs/heads/work-{a.name}"
    if r.returncode or _git(repo, "fetch", "-q", "--no-tags", "--", str(bundle), f"+HEAD:{ref}").returncode:
        return ""
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").stdout.strip()


def do_check(a, repo: str, branch: str, head: str, ladder: str) -> dict:
    """The ladder over <branch>..head; the range is the same refusal `builder check` has, `since` is a sha, not a name."""
    since = land_tool.resolve_branch(repo, branch)
    if not since:
        raise RuntimeError(f"{branch!r} is not a branch in {repo}")
    r = check_tool.ladder_over(repo, since, head, a.pinned, getattr(a, "ids", []))
    Path(ladder).write_text(json.dumps(r, indent=1))
    journal.append("check", repo=str(repo), since=since, head=head, ok=bool(r.get("ok")), failed=r.get("failed", ""))
    return r


def _script(name: str, *argv) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(SCRIPTS / name), *argv], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def do_review(a, repo: str, head: str, ladder: str, verdicts: str, model: str) -> tuple[bool, str]:
    ok, out = _script("harness_review.py", repo, head, "--pinned", a.pinned, "--verdicts", verdicts, "--ladder", ladder, "--model", model)
    return ok, out.splitlines()[-1] if out else "the reviewer said nothing"


def do_land(a, repo: str, head: str, verdicts: str, log: str) -> tuple[bool, str]:
    return _script("harness_land.py", repo, head, "--pinned", a.pinned, "--verdicts", verdicts, "--log", log)


def main(a) -> int:
    issues = list(a.issues)

    def step(name: str, ok: bool, detail: str) -> bool:
        journal.append("work", name=a.name, issues=issues, step=name, ok=ok, detail=detail)
        return ok

    def question(why: str) -> int:
        print(f"QUESTION: {why}")
        return 2

    try:
        cfg = check_tool.load(a.pinned)
        rules = tomllib.loads((Path(a.pinned) / "harness.toml").read_text())
        mdl = models.load(a.pinned)
        builder = a.model or models.for_role(mdl, "builder").model
        reviewer = models.for_role(mdl, "reviewer").model
        branch = rules["land"]["branch"]
    except (models.Question, ValueError, OSError, KeyError) as e:
        step("rules", False, str(e))
        return question(f"the rules file cannot run the chain: {e}")
    repo = a.repo or cfg.engine_repo
    if not repo:
        step("rules", False, "no --repo and no [check].engine_repo")
        return question("no --repo and no [check].engine_repo in the pinned rules")
    state = Path(journal.STATE)
    state.mkdir(parents=True, exist_ok=True)
    ladder, verdicts, log = (str(state / f"{k}-{a.name}.{e}") for k, e in (("ladder", "json"), ("verdicts", "json"), ("land", "log")))

    try:
        end = do_run(a, builder)
    except (RuntimeError, OSError, ValueError) as e:  # JailMissing is a RuntimeError: a start that raised is a question, not a traceback
        step("run", False, str(e))
        return question(f"the worker could not run: {e}")
    if not step("run", end == "done", end):
        return question(f"the worker ended {end!r}, not done; read its handoff and the journal, then decide")
    n = do_export(a, branch)
    if not step("patches", n > 0, f"{n} patch(es) under patches-{a.name} in the shared state"):
        return question(f"the worktree has no commits over origin/{branch}")
    head = do_fetch(a, repo, branch)
    if not step("fetch", bool(head), head or f"could not fetch the worktree branch into {repo}"):
        return question(f"could not fetch the worktree's branch into {repo}")
    try:
        r = do_check(a, repo, branch, head, ladder)
    except (RuntimeError, OSError, ValueError) as e:
        step("check", False, str(e))
        return question(f"the check could not run: {e}")
    if not step("check", bool(r.get("ok")), f"failed: {r.get('failed') or '-'}"):
        return question(f"the check is red at {head[:9]} (failed: {r.get('failed') or '?'}); ladder in {ladder}")
    ok, last = do_review(a, repo, head, ladder, verdicts, reviewer)
    if not step("review", ok, last):
        return question(f"the review is not READY: {last}")
    ok, out = do_land(a, repo, head, verdicts, log)
    if not step("land", ok, out[-300:]):
        return question(f"the land gate refused: {out[-300:]}")
    print(next((x for x in out.splitlines() if x.startswith("READY TO LAND")), out))
    return 0
