"""`builder work`: the chain a person ran by hand, as ONE process (dev-workflows.tool.work).

run -> rebase -> patches -> fetch -> check -> review -> land, each step a journal row (event "work": step, ok, detail). It stops with
`QUESTION: <why>` (exit 2) on a worker that did not finish, a red check, a NOT READY review or a refused land, and it only
prints the push line; nothing here pushes. Each step is a module function so a test replaces it."""
from __future__ import annotations

import contextlib
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
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


def owner_tree(a) -> bool:
    """A worktree outside the jail's workroot: an external lane's own checkout (land-*, lane-*), which the worker cannot read.
    Its chain steps run as the owner, whose tree it is (soak 2026-11-02: ie-batch2 in land-ie)."""
    if not getattr(a, "external", False):  # only the queue's external lanes; a worker's tree is always the jail's
        return False
    root = os.path.realpath(_jail(a).workroot) + "/"
    return not os.path.realpath(str(a.worktree)).startswith(root)


def shared_state(a) -> Path:
    """`<[jail].workroot>/state`: the one folder both users read (the worker's journal, patches and bundle live here); for an
    owner's tree, the owner's own journal dir (the shared one is the worker's and the owner cannot write it)."""
    return Path(journal.STATE) / "owner-trees" if owner_tree(a) else Path(_jail(a).workroot) / "state"


def as_worker(a, script: str) -> subprocess.CompletedProcess:
    """`script` as the jail user from the workroot: the owner cannot read the worker's session files or git in its tree.
    The one place the chain crosses the user boundary; a test replaces it."""
    j = _jail(a)
    if owner_tree(a):
        return subprocess.run(["sh", "-c", script], capture_output=True, text=True, cwd=str(a.worktree))
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


_LANE = threading.local()


def _activity(**kw) -> None:
    journal.append("activity", lane=getattr(_LANE, "name", ""), **kw)


def pinned_approvals(t: str) -> list[str]:
    """The approvals a pinned-checks refusal needs, one per reason it lists (a reason with none was unapprovable: 2026-11-02)."""
    return [k for k, hit in (("maintainer", "a pinned check file was" in t or " is pinned by name anywhere (" in t),
                             ("approve_weakened", "weakens existing tests" in t),
                             ("approve_pinned_new", "a new file under a pinned path" in t)) if hit]


def blocking(text: str, last: str) -> str:
    """What blocked: the first review group whose own closing line is NOT READY, named by its `[group n of m]` header with that
    line quoted. The file's last line alone says READY when a later group passed (alert -75 read 'not READY: READY', 2026-11-02)."""
    parts = re.split(r"(?m)^(?=\[group \d+ of \d+)", text or "")
    for part in parts:
        lines = [ln for ln in part.strip().splitlines() if ln.strip()]
        if lines and lines[-1].startswith("NOT READY"):
            head = lines[0] if lines[0].startswith("[group") else ""
            return (f"{head.split(']')[0]}] " if head else "") + lines[-1]
    return last


def green_before_approve(ladder: str, since: str, head: str, pinned) -> dict:
    """An approve resumes the SAME batch at the rung it excused (manager 2026-11-02): the rungs green in the last ladder file, for this
    head, this base and this pinned copy, stand and only the red rung and those after it run. Any difference = {} (start over)."""
    try:
        prev = json.loads(Path(ladder).read_text())
    except (OSError, ValueError):
        return {}
    if prev.get("ok") or (prev.get("head"), prev.get("since"), prev.get("pinned")) != (head, since, str(pinned)):
        return {}
    green = {}
    for row in prev.get("rungs") or []:
        if not row.get("ok"):
            break
        green[row["name"]] = row
    return green


def do_check(a, repo: str, branch: str, head: str, ladder: str) -> dict:
    """The ladder over <branch>..head; the range is the same refusal `builder check` has, `since` is a sha, not a name."""
    since = land_tool.resolve_branch(repo, branch)
    if not since:
        raise RuntimeError(f"{branch!r} is not a branch in {repo}")
    maintainer = bool(getattr(a, "maintainer", False))  # the manager approved a pinned-file change (dev-workflows.run.loop-needs-maintainer)
    approve = bool(getattr(a, "approve_weakened", False))  # the manager approved weakened tests (an alert's approve)
    red_ok = getattr(a, "approve_red", False)
    red_ok = red_ok if isinstance(red_ok, tuple) else bool(red_ok)  # a tuple: only the test files the approved alert named
    _LANE.name = a.name  # per chain thread: two ladders at once each write their own lane's rows (speed 3)
    check_tool.ACTIVITY = _activity
    check_tool.GUARD_CACHE[0] = journal.STATE / "guard-cache.json"  # speed 5
    pin_new = bool(getattr(a, "approve_pinned_new", False))  # the manager approved a new file under a pinned path
    guard_data = tuple(getattr(a, "guard_data", ()) or ())
    approved = maintainer or approve or bool(red_ok) or pin_new or bool(guard_data)
    check_tool.REUSE[0] = green_before_approve(ladder, since, head, a.pinned) if approved else None
    try:
        r = check_tool.ladder_over(repo, since, head, a.pinned, getattr(a, "ids", []), maintainer=maintainer, approve_weakened=approve, approve_red=red_ok,
                                   approve_pinned_new=pin_new, guard_data=guard_data)
    finally:
        check_tool.REUSE[0] = None
    Path(ladder).write_text(json.dumps({**r, "head": head, "since": since, "pinned": str(a.pinned)}, indent=1))
    journal.append("check", repo=str(repo), since=since, head=head, ok=bool(r.get("ok")), failed=r.get("failed", ""), maintainer=maintainer, approve_weakened=approve, approve_red=red_ok)
    return r


def _script(name: str, *argv) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(SCRIPTS / name), *argv], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def do_review(a, repo: str, head: str, ladder: str, verdicts: str, model: str, holder: dict | None = None) -> tuple[bool, str]:
    """The review script; with `holder`, its process is kept there so a later red rung can kill it (speed 2)."""
    key = f"review {head[:9]}"
    journal.append("activity", kind="review", key=key, state="start", lane=a.name, model=model)  # which reviewer (6a)
    argv = [sys.executable, str(SCRIPTS / "harness_review.py"), repo, head, "--pinned", a.pinned, "--verdicts", verdicts, "--ladder", ladder, "--model", model]
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if holder is not None:
        holder["proc"] = p
    out = (p.communicate()[0] or "").strip()
    ok = p.returncode == 0
    groups = re.findall(r"^\[group (\d+) of (\d+)", out or "", re.M)
    journal.append("activity", kind="review", key=key, state="end", ok=ok, groups=len(groups) or 1)
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
    keys = ("reason", "stdout_tail", "stderr_tail", "errors", "log")  # errors and the log path LAST: the 3000-character cut keeps the end
    red = [f"{x.get('name')}: " + "\n".join(str(x[k]) for k in keys if x.get(k)) for x in last.get("results") or [] if not x.get("ok")]  # a guards rung
    return "\n".join([*(str(last[k]) for k in keys if last.get(k)), *red])[-3000:]


def r_since(repo: str, branch: str) -> str:
    return land_tool.resolve_branch(repo, branch) or branch


MOVES = 3  # ponytail: a busier landing branch than three moves in one chain is a row for a person


def keep_green(repo: str, old_base: str, old_files: list[str], new_base: str, files: list[str], cfg, old_head: str = "", head: str = "") -> str:
    """Stale base (manager 2026-11-02): a green check survives a clean rebase when the base delta (old..new) touches no file
    the batch changes, nothing under the top-level dirs it changes (its tests and whole-tests inputs), no pinned check file
    and no guard, and the rebased batch is the same patch as the checked one (review 2026-11-02: file names alone let new content
    ride a green). '' = check again; else the row's words."""
    if not files or sorted(files) != sorted(old_files) or not old_base or new_base == old_base or not old_head or not head:
        return ""
    old_patch, new_patch = _git(repo, "diff", old_base, old_head), _git(repo, "diff", new_base, head)
    if old_patch.returncode or new_patch.returncode or old_patch.stdout != new_patch.stdout:
        return ""
    if _git(repo, "merge-base", "--is-ancestor", old_base, new_base).returncode:
        return ""
    delta = _git(repo, "diff", "--name-only", old_base, new_base).stdout.split()
    tops = tuple({f.split("/", 1)[0] + "/" for f in files if "/" in f})
    if not delta or any(p in files or p.startswith(tops) or p.startswith(tuple(cfg.check_paths)) or (cfg.guard_glob and fnmatch.fnmatch(p, cfg.guard_glob))
                        for p in delta):
        return ""
    return f"kept across rebase onto {new_base[:9]}: base delta disjoint ({len(delta)} file(s))"


def _base_moved(a, branch: str, head: str) -> bool:
    """As the worker: has origin/<branch> moved past the base `head` was made on? (fetch; is it still an ancestor of HEAD)"""
    g, wt = shlex.quote(jail_git()), shlex.quote(str(a.worktree))
    r = as_worker(a, f"{g} -C {wt} fetch -q origin && {g} -C {wt} merge-base --is-ancestor origin/{shlex.quote(branch)} HEAD")
    return r.returncode == 1


@contextlib.contextmanager
def ladder_slot(name: str, files: list[str], n: int, sleep=time.sleep):
    """Speed 3 (manager 2026-11-02): up to n ladders at once ([check].parallel), never two whose batches share a file (an
    unknown file list shares every file). The slot's files sit beside its lock while it runs; a slot whose lock is free is
    not running, whatever file it left. A wait over Lock.WARN_S is one row, like the single lock's."""
    t0, said, state = time.time(), False, Path(journal.STATE)
    while True:
        with journal.Lock("ladder-pick"):  # pick and claim as one step: two chains never both see the other's slot empty
            free, clash = None, ""
            for slot in journal.ladder_slots(n):
                lk = journal.Lock(slot, wait=False, what=f"the check of {name}")
                try:
                    lk.__enter__()
                except BlockingIOError:
                    other = state / f"{slot}.files"
                    try:
                        o = json.loads(other.read_text())
                    except (OSError, ValueError):
                        o = {"name": "?", "files": []}
                    if not files or not o["files"] or set(files) & set(o["files"]):
                        clash = o["name"]
                    continue
                if free is None:
                    free = (slot, lk)
                else:
                    lk.__exit__()
            if free and clash:
                free[1].__exit__()
                free = None
            if free:
                (state / f"{free[0]}.files").write_text(json.dumps({"name": name, "files": files}))
        if free:
            break
        if not said and time.time() - t0 > journal.Lock.WARN_S:
            why = f"its batch shares files with the check of {clash}" if clash else f"all {n} ladder slot(s) are busy"
            journal.append("lock", state="waiting", name="ladder", holder=clash or "?", what=f"the check of {name}", pid=os.getpid(), detail=why)
            said = True
        sleep(1)
    if said:
        journal.append("lock", state="acquired", name="ladder", what=f"the check of {name}", pid=os.getpid(), seconds=int(time.time() - t0))
    try:
        yield free[0]
    finally:
        (state / f"{free[0]}.files").unlink(missing_ok=True)
        free[1].__exit__()


_EARLY = __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=2)  # early reviews (speed 2)
OPUS_PATHS = ("fichero-builder/", "scripts/harness_", "scripts/lane_ready_check.sh", "harness.toml")


def pick_reviewer(a, repo: str, branch: str, head: str, full: str) -> str:
    """The review model (dev-workflows.models.review-by-path, manager 2026-11-02): `[models].reviewer_fast` (sonnet) by default;
    the full reviewer (opus) when the range touches the harness, land or jail paths (`[models].reviewer_paths`), and for a
    worker lane's last step of its milestone (one opus pass per milestone)."""
    fast = getattr(a, "reviewer_fast", "") or full
    if fast == full or getattr(a, "last_step", False):
        return full
    names = _git(repo, "diff", "--name-only", r_since(repo, branch), head).stdout.split()
    return full if any(n.startswith(tuple(getattr(a, "opus_paths", OPUS_PATHS))) for n in names) else fast


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
    carry = None  # (base, files, head) of a green check whose base moved before its review
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
        try:
            since_now = r_since(repo, branch)
            files = _git(repo, "diff", "--name-only", since_now, head).stdout.split()
        except (RuntimeError, OSError):
            since_now, files = "", []  # unknown: shares every file, so it runs alone
        kept = keep_green(repo, carry[0], carry[1], since_now, files, check_tool.load(a.pinned), carry[2], head) if carry else ""
        carry = None
        with ladder_slot(a.name, files, check_tool.load(a.pinned).parallel):  # speed 3: [check].parallel ladders, disjoint batches only
            if getattr(a, "repin", None):  # another lane's landing may have removed the copy this one started from; the lock keeps it from here on
                a.pinned = a.repin()
            stage("checking")
            early: dict = {}  # speed 2: the review starts once ready and red-on-base are green, beside the rest of the ladder

            def on_rung(name, ok, rungs):
                if name == "red-on-base" and ok and all(x["ok"] for x in rungs) and "fut" not in early and land_tool.unreviewed(repo, branch, head, verdicts):
                    partial = f"{ladder}.partial"
                    # the rungs still to come are named, so the reviewer never reads them as missing (reviews 199 and 207, 2026-11-03)
                    pending = [n for n in check_tool.RUNGS if n not in {x["name"] for x in rungs}]
                    Path(partial).write_text(json.dumps({"ok": None, "failed": "", "rungs": rungs, "pending": pending}))
                    model = pick_reviewer(a, repo, branch, head, reviewer)
                    early["fut"] = _EARLY.submit(do_review, a, repo, head, partial, verdicts, model, early)
            check_tool.ON_RUNG[0] = on_rung
            try:
                if kept:  # the green check of the same batch on the old base stands (its row names why)
                    r = {"ok": True, "failed": ""}
                    journal.append("check", repo=str(repo), since=since_now, head=head, ok=True, failed="", kept=kept)
                    step("kept", True, kept)
                else:
                    r = do_check(a, repo, branch, head, ladder)
            except (RuntimeError, OSError, ValueError) as e:
                step("check", False, str(e))
                return no("error", f"the check could not run: {e}")
            finally:
                check_tool.ON_RUNG[0] = None
            if not r.get("ok") and early.get("proc"):  # a later rung went red: the early review is cancelled, its verdict never written
                early["proc"].kill()
                journal.append("activity", kind="review", key=f"review {head[:9]}", state="end", ok=False, failed="cancelled: a later rung red")
            if not step("check", bool(r.get("ok")), f"failed: {r.get('failed') or '-'}"):
                if r.get("failed") == "red-on-base" and "needs-approval" in _tail(r):  # a refusal, not a red test: the manager's call
                    return {**no("red-on-base", f"red-on-base at {head[:9]}: {_tail(r).replace('needs-approval', '').strip()[-300:]}", _tail(r), ladder),
                            "approvals": ["approve_red"]}
                if r.get("failed") == "pinned-checks" and "needs-maintainer" in _tail(r):
                    # ONE alert for every reason the refusal lists, and one approve carries them all (manager 2026-11-02: an approve
                    # re-ran with maintainer only and refused again on the weakened tests it had already listed)
                    t = _tail(r)
                    approvals = pinned_approvals(t)
                    paths = list(check_tool.load(a.pinned).check_paths) + [f":(glob)**/{g}" for g in check_tool.load(a.pinned).test_globs]
                    diff = state / f"pinned-{a.name}.diff"
                    diff.write_text(_git(repo, "diff", r_since(repo, branch), head, "--", *paths).stdout)
                    kind = "needs-maintainer" if "maintainer" in approvals else "weakened-tests" if "approve_weakened" in approvals else "pinned-new"
                    return {**no(kind, f"pinned-checks at {head[:9]}: {t[-300:]}", t, str(diff)), "approvals": approvals}
                if r.get("failed") == "guards" and not getattr(a, "guard_data", ()):
                    # a guard reads an allowlist beside itself (a .json under a check path): pinned, it judges head's routes against the
                    # OLD list, so a batch that changes the list can never pass. The manager's approve, by file name, lays head's copy over it.
                    cfg_now = check_tool.load(a.pinned)
                    data = [f for f in files if f.endswith(".json") and f.startswith(tuple(cfg_now.check_paths))]
                    if data:
                        diff = state / f"guard-data-{a.name}.diff"
                        diff.write_text(_git(repo, "diff", since_now, head, "--", *data).stdout)
                        return {**no("guard-data", f"guards red at {head[:9]} with guard data changed by the batch: {', '.join(data)}; approve lays HEAD's copy of "
                                     f"exactly these files under the pinned guards (the scripts stay pinned)", _tail(r), str(diff)), "approvals": ["approve_guard_data"]}
                return no("red", f"the check is red at {head[:9]} (failed: {r.get('failed') or '?'}); ladder in {ladder}", f"failed rung: {r.get('failed') or '?'}\n{_tail(r)}", ladder)
            if moved < MOVES and since_now and _base_moved(a, branch, head):  # never review a range that cannot land
                moved += 1
                if early.get("proc"):
                    early["proc"].kill()
                carry = (since_now, files, head)
                step("rebase", True, f"origin/{branch} moved under {head[:9]} before its review: rebasing first ({moved}/{MOVES})")
                continue
            stage("reviewing")
            if early.get("fut"):  # started beside the ladder: its result
                ok, text = early["fut"].result()
            elif land_tool.unreviewed(repo, branch, head, verdicts):
                model = pick_reviewer(a, repo, branch, head, reviewer)
                ok, text = do_review(a, repo, head, ladder, verdicts, model)
            else:  # same input, same model: this exact range has its READY (a queue restarted in `reviewing` lands here)
                ok, text = True, "READY (the verdict this range already has; no second model pass)"
            last = text.splitlines()[-1] if text else "the reviewer said nothing"
            if not step("review", ok, last):
                (state / f"review-{a.name}.txt").write_text(text)
                return no("not-ready", f"the review is not READY: {blocking(text, last)}", text, str(state / f"review-{a.name}.txt"))
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
