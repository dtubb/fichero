"""`builder work`: the chain a person ran by hand, as ONE process (dev-workflows.tool.work).

run -> patches -> fetch -> check -> review -> land, each step a journal row (event "work": step, ok, detail). It stops with
`QUESTION: <why>` (exit 2) on a worker that did not finish, a red check, a NOT READY review or a refused land, and it only
prints the push line; nothing here pushes. Each step is a module function so a test replaces it."""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from fichero_builder import check_tool, journal, models
from fichero_builder import run as run_mod

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def do_run(a, model: str) -> str:
    procs = run_mod.real_procs(Path.home(), a.worktree)
    return run_mod.run(a.root, a.worktree, a.brief, name=a.name, model=model, kind=a.kind, tmux_session=a.session,
                       tick_s=a.tick, procs=procs, handoff=None)


def do_export(a, branch: str) -> int:
    """The worktree's commits over origin/<land branch> as patch files; the count (0 = nothing to land)."""
    out = Path(journal.STATE) / f"patches-{a.name}"
    out.mkdir(parents=True, exist_ok=True)
    r = _git(a.worktree, "format-patch", "-o", str(out), f"origin/{branch}")
    return len(r.stdout.split()) if r.returncode == 0 else 0


def do_fetch(a, repo: str, branch: str) -> str:
    """Bring the worktree's commits into the engine-owned repo as refs/heads/work-<name>; its head sha ('' = failed).
    The worker's branch NAME is never passed to git on the owner's side (a name like `--upload-pack=...` ran a command):
    the worktree makes a bundle of origin/<branch>..HEAD and the owner fetches HEAD from that file."""
    bundle = Path(journal.STATE) / f"work-{a.name}.bundle"
    bundle.unlink(missing_ok=True)
    if _git(a.worktree, "bundle", "create", str(bundle), f"origin/{branch}..HEAD").returncode:
        return ""
    ref = f"refs/heads/work-{a.name}"
    if _git(repo, "fetch", "-q", "--no-tags", "--", str(bundle), f"HEAD:{ref}").returncode:
        return ""
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").stdout.strip()


def do_check(a, repo: str, since: str, head: str, ladder: str) -> dict:
    r = check_tool.run_ladder(repo, since, head, a.pinned, [])
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

    end = do_run(a, builder)
    if not step("run", end == "done", end):
        return question(f"the worker ended {end!r}, not done; read its handoff and the journal, then decide")
    n = do_export(a, branch)
    if not step("patches", n > 0, f"{n} patch(es) in {state / ('patches-' + a.name)}"):
        return question(f"the worktree has no commits over origin/{branch}")
    head = do_fetch(a, repo, branch)
    if not step("fetch", bool(head), head or f"could not fetch the worktree branch into {repo}"):
        return question(f"could not fetch the worktree's branch into {repo}")
    r = do_check(a, repo, branch, head, ladder)
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
