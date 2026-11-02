"""`builder work`: the chain a person ran by hand, as ONE process (dev-workflows.tool.work).

run -> rebase -> patches -> fetch -> check -> review -> land, each step a journal row (event "work": step, ok, detail). It stops with
`QUESTION: <why>` (exit 2) on a worker that did not finish, a red check, a NOT READY review or a refused land, and it only
prints the push line; nothing here pushes. Each step is a module function so a test replaces it."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

from fichero_builder import check_tool, codemap, jail, journal, land_tool, models

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


def run_cmd(a, model: str, *extra) -> str:
    """The `builder run` command line the jail user runs (the one-brief path, and the queue's long-running session with --feed)."""
    py = check_tool.load(a.pinned).python or sys.executable
    pkg = Path(__file__).resolve().parents[1]
    return codemap.index_prefix(a.pinned, a.worktree) + " ".join(["PYTHONPATH=" + shlex.quote(str(pkg)), shlex.quote(py), "-m fichero_builder run",
                     *(f"{k} {shlex.quote(str(v))}" for k, v in (
                         ("--worktree", a.worktree), ("--brief", a.brief), ("--root", a.root), ("--name", a.name), ("--model", model),
                         ("--kind", a.kind), ("--session", a.session), ("--tick", a.tick), ("--state", shared_state(a)))),
                     *(shlex.quote(str(x)) for x in extra)])


def ensure_worktree(a, new_branch: str) -> str:
    """As the worker, when the worktree is missing: `<workroot>/root` makes it on a new branch at --base, else origin's head of the
    land branch. '' or why it could not. The path is checked first, so an existing tree costs no sudo."""
    if Path(a.worktree).exists():
        return ""
    q, g, branch = shlex.quote, shlex.quote(jail_git()), tomllib.loads((Path(a.pinned) / "harness.toml").read_text())["land"]["branch"]
    root = q(str(Path(_jail(a).workroot) / "root"))
    r = as_worker(a, f"{g} -C {root} fetch -q origin {q(branch)} && {g} -C {root} worktree add -q -b {q(new_branch)} {q(str(a.worktree))} "
                     f"{q(getattr(a, 'base', '') or 'origin/' + branch)}")
    return "" if r.returncode == 0 else f"the worktree could not be made: {(r.stderr or r.stdout).strip()[-300:]}"


def do_run(a, model: str) -> str:
    """`builder run` as the jail user; the end is read from the SHARED journal (the cost row, and the worker row's worktree)."""
    j = _jail(a)
    j.require()
    if why := ensure_worktree(a, a.name):
        raise RuntimeError(why)
    before = len(_shared_rows(a))
    codemap.provide(a.pinned)
    cmd = run_cmd(a, model)
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


def do_rebase(a, branch: str) -> str:
    """As the worker: fetch origin and rebase the worktree onto origin/<branch>, so a lane that lands after another is judged
    on the range that will land. '' = done; otherwise why (the rebase aborted, never resolved here)."""
    q, g, wt = shlex.quote, shlex.quote(jail_git()), shlex.quote(str(a.worktree))
    r = as_worker(a, f"{g} -C {wt} fetch -q origin && {g} -C {wt} rebase -q origin/{q(branch)}")
    if r.returncode == 0:
        return ""
    as_worker(a, f"{g} -C {wt} rebase --abort")
    return f"rebase onto origin/{branch} could not finish (conflict left to a person): {(r.stderr or r.stdout).strip()[-300:]}"


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
    maintainer = bool(getattr(a, "maintainer", False))  # the manager approved a pinned-file change (dev-workflows.run.loop-needs-maintainer)
    r = check_tool.ladder_over(repo, since, head, a.pinned, getattr(a, "ids", []), maintainer=maintainer)
    Path(ladder).write_text(json.dumps(r, indent=1))
    journal.append("check", repo=str(repo), since=since, head=head, ok=bool(r.get("ok")), failed=r.get("failed", ""), maintainer=maintainer)
    return r


def _script(name: str, *argv) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(SCRIPTS / name), *argv], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def do_review(a, repo: str, head: str, ladder: str, verdicts: str, model: str) -> tuple[bool, str]:
    ok, out = _script("harness_review.py", repo, head, "--pinned", a.pinned, "--verdicts", verdicts, "--ladder", ladder, "--model", model)
    return ok, out or "the reviewer said nothing"  # the whole text: a queue sends the findings back to the worker


def do_land(a, repo: str, head: str, verdicts: str, log: str) -> tuple[bool, str]:
    """The check step just wrote the green row for this head: the verdict and the boundary, no second ladder (land_tool.gate)."""
    try:
        return land_tool.gate(repo, head, a.pinned, verdicts, log)
    except OSError as e:  # in-process since the ladder stopped running twice: a bad log at the end of the work is a question, not a traceback
        return False, f"REFUSED: {e}"


def base_of(brief: str, given: str) -> str:
    """--base, else `(base <sha>)` on the brief's first line (brief_tool.cluster writes it)."""
    if given:
        return given
    m = re.search(r"\(base ([0-9a-f]{7,40})\)", Path(brief).read_text().split("\n", 1)[0])
    if not m:
        raise ValueError(f"no --base and no `(base <sha>)` on the first line of {brief}")
    return m.group(1)


def ensure_pinned(root: str, brief: str, base: str) -> str:
    """[land].pinned_dir/pinned-<base7> of root's harness.toml, a worktree of [check].engine_repo on branch pinned-<base7>
    (the shape `builder landed` makes and later removes); made when missing, found otherwise."""
    rules = tomllib.loads((Path(root) / "harness.toml").read_text())
    repo, pinned_dir = rules["check"]["engine_repo"], Path(rules["land"]["pinned_dir"])
    if not pinned_dir.is_absolute():
        raise ValueError(f"[land].pinned_dir {str(pinned_dir)!r} must be an absolute path")
    name = f"pinned-{base_of(brief, base)[:7]}"
    dest = pinned_dir / name
    if not dest.is_dir():
        pinned_dir.mkdir(parents=True, exist_ok=True)
        for args in (("branch", "-f", name, name[7:]), ("worktree", "add", "-q", str(dest), name)):
            r = _git(repo, *args)
            if r.returncode:
                raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return str(dest)


def _tail(r: dict) -> str:
    """What a red rung said, for the worker's fix brief."""
    last = (r.get("rungs") or [{}])[-1]
    keys = ("reason", "stdout_tail", "stderr_tail")
    red = [f"{x.get('name')}: " + "\n".join(str(x[k]) for k in keys if x.get(k)) for x in last.get("results") or [] if not x.get("ok")]  # a guards rung
    return "\n".join([*(str(last[k]) for k in keys if last.get(k)), *red])[-3000:]


def r_since(repo: str, branch: str) -> str:
    return land_tool.resolve_branch(repo, branch) or branch


MOVES = 3  # ponytail: a busier landing branch than three moves in one chain is a row for a person


def _base_moved(a, branch: str, head: str) -> bool:
    """As the worker: has origin/<branch> moved past the base `head` was made on? (fetch; is it still an ancestor of HEAD)"""
    g, wt = shlex.quote(jail_git()), shlex.quote(str(a.worktree))
    r = as_worker(a, f"{g} -C {wt} fetch -q origin && {g} -C {wt} merge-base --is-ancestor origin/{shlex.quote(branch)} HEAD")
    return r.returncode == 1


def after_run(a, repo: str, branch: str, reviewer: str, stage=lambda name: None) -> dict:
    """Rebase, patches, fetch, check, review, land gate: one journal row each; {ok, head, out} or {ok: False, kind, why,
    findings}. kind red / not-ready / refused can go back to the worker; error needs a person. `stage` hears checking, reviewing."""
    issues = list(a.issues)

    def step(name: str, ok: bool, detail: str) -> bool:
        journal.append("work", name=a.name, issues=issues, step=name, ok=ok, detail=detail, worktree=str(a.worktree))
        return ok

    def no(kind: str, why: str, findings: str = "", evidence: str = "") -> dict:
        return {"ok": False, "kind": kind, "why": why, "findings": findings, "evidence": evidence}

    state = Path(journal.STATE)
    state.mkdir(parents=True, exist_ok=True)
    ladder, verdicts, log = (str(state / f"{k}-{a.name}.{e}") for k, e in (("ladder", "json"), ("verdicts", "json"), ("land", "log")))
    moved = 0
    while True:  # dev-workflows.run.loop-chain: a ready range whose base moved is rebased and re-checked
        why = do_rebase(a, branch)
        if not step("rebase", not why, why or f"on top of origin/{branch}"):
            return no("error", why)
        n = do_export(a, branch)
        if not step("patches", n > 0, f"{n} patch(es) under patches-{a.name} in the shared state"):
            return no("error", f"the worktree has no commits over origin/{branch}")
        head = do_fetch(a, repo, branch)
        if not step("fetch", bool(head), head or f"could not fetch the worktree branch into {repo}"):
            return no("error", f"could not fetch the worktree's branch into {repo}")
        with journal.Lock("ladder"):  # one ladder at a time across the queue's lanes and any `builder work` (the machine is loaded)
            if getattr(a, "repin", None):  # another lane's landing may have removed the copy this one started from; the lock keeps it from here on
                a.pinned = a.repin()
            stage("checking")
            try:
                r = do_check(a, repo, branch, head, ladder)
            except (RuntimeError, OSError, ValueError) as e:
                step("check", False, str(e))
                return no("error", f"the check could not run: {e}")
            if not step("check", bool(r.get("ok")), f"failed: {r.get('failed') or '-'}"):
                if r.get("failed") == "pinned-checks" and "needs-maintainer" in _tail(r):
                    diff = state / f"pinned-{a.name}.diff"
                    diff.write_text(_git(repo, "diff", r_since(repo, branch), head, "--", *check_tool.load(a.pinned).check_paths).stdout)
                    return no("needs-maintainer", f"pinned-checks at {head[:9]}: {_tail(r)[-300:]}", _tail(r), str(diff))
                return no("red", f"the check is red at {head[:9]} (failed: {r.get('failed') or '?'}); ladder in {ladder}", f"failed rung: {r.get('failed') or '?'}\n{_tail(r)}", ladder)
            stage("reviewing")
            if land_tool.unreviewed(repo, branch, head, verdicts):
                ok, text = do_review(a, repo, head, ladder, verdicts, reviewer)
            else:  # same input, same model: this exact range has its READY (a queue restarted in `reviewing` lands here)
                ok, text = True, "READY (the verdict this range already has; no second model pass)"
            last = text.splitlines()[-1] if text else "the reviewer said nothing"
            if not step("review", ok, last):
                (state / f"review-{a.name}.txt").write_text(text)
                return no("not-ready", f"the review is not READY: {last}", text, str(state / f"review-{a.name}.txt"))
            ok, out = do_land(a, repo, head, verdicts, log)
            if not step("land", ok, out[-300:]):
                if moved < MOVES and _base_moved(a, branch, head):
                    moved += 1  # another lane landed after our rebase: rebase and judge the new range, never a person's hand step
                    step("rebase", True, f"origin/{branch} moved under {head[:9]}: rebased and checked again ({moved}/{MOVES})")
                    continue
                return no("refused", f"the land gate refused: {out[-300:]}", out[-2000:])
        return {"ok": True, "head": head, "out": out}


def main(a) -> int:
    """The chain; a pinned copy another lane's landing removed takes the rules with it, which is a row and a question, not a traceback."""
    try:
        return _chain(a)
    except jail.JailMissing as e:
        journal.append("work", name=a.name, issues=list(a.issues), step="rules", ok=False, detail=str(e), worktree=str(a.worktree))
        print(f"QUESTION: the rules this chain started from are gone or refuse: {e}")
        return 2


def _chain(a) -> int:
    issues = list(a.issues)

    def step(name: str, ok: bool, detail: str) -> bool:
        journal.append("work", name=a.name, issues=issues, step=name, ok=ok, detail=detail, worktree=str(a.worktree))
        return ok

    def question(why: str) -> int:
        print(f"QUESTION: {why}")
        return 2

    try:
        if not a.pinned:
            a.pinned = ensure_pinned(a.root, a.brief, getattr(a, "base", ""))
            a.repin = lambda: ensure_pinned(a.root, a.brief, getattr(a, "base", ""))
            step("pinned", True, a.pinned)
        cfg = check_tool.load(a.pinned)
        rules = tomllib.loads((Path(a.pinned) / "harness.toml").read_text())
        mdl = models.load(a.pinned)
        builder = a.model or models.for_role(mdl, "builder").model
        reviewer = models.for_role(mdl, "reviewer").model
        branch = rules["land"]["branch"]
    except (models.Question, ValueError, OSError, KeyError, RuntimeError) as e:
        step("rules", False, str(e))
        return question(f"the rules file cannot run the chain: {e}")
    repo = a.repo or cfg.engine_repo
    if not repo:
        step("rules", False, "no --repo and no [check].engine_repo")
        return question("no --repo and no [check].engine_repo in the pinned rules")
    Path(journal.STATE).mkdir(parents=True, exist_ok=True)
    if problem := land_tool.log_problem(Path(journal.STATE) / f"land-{a.name}.log"):  # before the worker and the ladder, not after
        step("rules", False, problem)
        return question(f"the land log cannot be written: {problem}")

    try:
        end = do_run(a, builder)
    except (RuntimeError, OSError, ValueError) as e:  # JailMissing is a RuntimeError: a start that raised is a question, not a traceback
        step("run", False, str(e))
        return question(f"the worker could not run: {e}")
    if not step("run", end in ("done", "done-unsaid"), end):
        return question(f"the worker ended {end!r}, not done; read its handoff and the journal, then decide")
    r = after_run(a, repo, branch, reviewer)
    if not r["ok"]:
        return question(r["why"])
    out = r["out"]
    print(next((x for x in out.splitlines() if x.startswith("READY TO LAND")), out))
    return 0
