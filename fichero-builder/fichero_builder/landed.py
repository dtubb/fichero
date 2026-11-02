"""`builder landed <sha> [--push]`: after a verdict, the maintainer runs ONE command instead of fifteen (dev-workflows.tool.landed).

Refuses unless the verdict store has READY for the sha, the owner's journal has a green check row for it and the sha is
a fast-forward of origin/<[land].branch> in the engine repo. Then, each step a journal row (event `landed`: step, ok,
detail) and a red step stops with its reason (exit 1): push (only with --push: the maintainer typed the flag, nothing
else sets it), the engine repo's local branch refreshed, a `pinned-<sha7>` branch and worktree under [land].pinned_dir
replacing the previous one, the jail root fast-forwarded as the worker user, the scratch worktrees of the work rows for
that sha removed, the issues the range cites updated, and a final `done` row (sha, branch, pushed, issues)."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from fichero_builder import check_tool, jail, journal, land_tool


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run([land_tool.GIT, "-C", str(repo), *args], capture_output=True, text=True)


def as_worker(j: jail.Jail, script: str) -> subprocess.CompletedProcess:
    """`script` as the jail user from the workroot (the same boundary `builder work` crosses); a test replaces it."""
    return subprocess.run([j.sudo, "-n", "-H", "-u", j.user, "sh", "-c", f"cd {shlex.quote(j.workroot)} && {script}"],
                          capture_output=True, text=True, cwd="/")  # the owner's cwd is unreadable to the worker: getcwd failed (2026-11-02)


class Red(Exception):
    """A step that stops the landing; its text is the row's detail and the message on stderr."""


def _ok(r: subprocess.CompletedProcess, what: str) -> str:
    if r.returncode:
        raise Red(f"{what}: {(r.stderr or r.stdout).strip()[-300:]}")
    return r.stdout.strip()


def pinned_worktrees(repo) -> dict[str, str]:
    """{branch: path} of the engine repo's worktrees on a pinned-* branch."""
    out, cur = {}, ""
    for ln in (_git(repo, "worktree", "list", "--porcelain").stdout or "").splitlines():
        if ln.startswith("worktree "):
            cur = ln[9:]
        elif ln.startswith("branch refs/heads/pinned-"):
            out[ln[len("branch refs/heads/"):]] = cur
    return out


def pin(repo, sha: str, pinned_dir: Path, keep_others: bool = False) -> str:
    """`pinned-<sha7>` as a branch and a worktree under pinned_dir; every other pinned-* branch and worktree goes, unless
    `keep_others` (a check is reading one: the next landing removes them)."""
    name = f"pinned-{sha[:7]}"
    if name not in pinned_worktrees(repo):  # git refuses `branch -f` on a branch its own worktree has out: a rerun finds it in place
        _ok(_git(repo, "branch", "-f", name, sha), "branch -f")
    for b, path in ({} if keep_others else pinned_worktrees(repo)).items():
        if b != name:
            _ok(_git(repo, "worktree", "remove", "--force", path), f"worktree remove {path}")
    for b in ([] if keep_others else _git(repo, "branch", "--list", "pinned-*", "--format=%(refname:short)").stdout.split()):
        if b != name:
            _ok(_git(repo, "branch", "-D", b), f"branch -D {b}")
    dest = pinned_dir / name
    if not dest.is_dir():
        pinned_dir.mkdir(parents=True, exist_ok=True)
        _ok(_git(repo, "worktree", "add", "-q", str(dest), name), "worktree add")
    return str(dest)


def live_worktrees() -> set[str]:
    """The worktrees a queue lane with steps left holds: its session may be working there."""
    from fichero_builder import queue

    return {os.path.realpath(x["worktree"]) for x in queue.load() if x["cursor"] < len(x["steps"])}


def sweep(sh, repo_dir: str, ref: str, grace_h: float, removed: str, live: set[str], now: float | None = None, only: set | None = None) -> list[str]:
    """Remove each linked worktree of `repo_dir` whose HEAD is on `ref` (landed), idle for `grace_h` hours (the newer of its
    index's mtime and its HEAD's commit time) and held by no live lane: first its uncommitted and untracked files go to a
    patch under `removed` (kept even when the removal then fails), then `git worktree remove`, never rm; the branch stays
    (#6204). `sh` runs a script as the jail user. Returns one line per worktree touched.
    ponytail: idle = the index's mtime; a process watch if a worker ever sits 36 h without touching git."""
    q, git, now = shlex.quote, shlex.quote(land_tool.GIT), now or time.time()
    out = []
    listing = sh(f"{git} -C {q(repo_dir)} worktree list --porcelain").stdout or ""
    for block in listing.strip().split("\n\n")[1:]:  # the first is the main tree
        f = dict((ln.split(" ", 1) + [""])[:2] for ln in block.splitlines())
        wt, head = f.get("worktree", ""), f.get("HEAD", "")
        if not wt or not head or os.path.realpath(wt) in live or (only is not None and os.path.realpath(wt) not in only):
            continue
        if sh(f"{git} -C {q(repo_dir)} merge-base --is-ancestor {q(head)} {q(ref)}").returncode:
            continue  # not landed: work in progress
        idx = (sh(f"{git} -C {q(wt)} rev-parse --path-format=absolute --git-path index").stdout or "").strip()
        ct = (sh(f"{git} -C {q(wt)} log -1 --format=%ct HEAD").stdout or "0").strip()
        last = max(int(ct or 0), int(os.stat(idx).st_mtime) if idx and os.path.exists(idx) else 0)
        if now - last < grace_h * 3600:
            continue
        patch = f"{removed}/{Path(wt).name}-{head[:7]}-{int(now)}.patch"
        # the patch first, and the tree goes only when the patch was written (#6204): a failed mkdir, add or diff keeps it
        saved = sh(f"mkdir -p {q(removed)} && cd {q(wt)} && {git} add -A && {git} diff --cached --binary HEAD > {q(patch)} && test -f {q(patch)}")
        if saved.returncode:
            why = (saved.stderr or "").strip()[-200:] or f"exit {saved.returncode}"
            n = sum(1 for x in journal.read() if x.get("event") == "alert") + 1  # the queue's alert row shape (dev-workflows.run.loop-alerts)
            journal.append("alert", id=f"land-sweep-{n}", lane="land", step="sweep", what=f"{wt} kept: its patch could not be written ({why})"[:300],
                           evidence=wt, actions=[])
            out.append(f"{wt}: kept, no patch ({why})")
            continue
        r = sh(f"{git} -C {q(repo_dir)} worktree remove --force {q(wt)}")
        out.append(f"{wt}: " + ("removed" if r.returncode == 0 else f"NOT removed ({(r.stderr or '').strip()[-200:]})") + f", patch {patch}")
    return out


def sweep_one(root, worktree: str) -> tuple[int, str]:
    """`builder sweep --worktree P`: the console's Clean up. The same sweep for that one tree with no grace (the owner asked
    for it): landed, a patch first, `git worktree remove`, never rm. A jail tree is swept as the worker, any other as the owner."""
    doc = tomllib.loads((Path(root) / "harness.toml").read_text())
    branch, j = doc["land"]["branch"], jail.load(root)
    wt = os.path.realpath(worktree)
    if j is not None and j.workroot and wt.startswith(os.path.realpath(j.workroot) + "/"):
        sh, repo_dir, removed = (lambda script: as_worker(j, script)), "root", f"{j.workroot}/.removed"
    else:
        sh = lambda script: subprocess.run(["sh", "-c", script], capture_output=True, text=True, cwd=str(root))  # noqa: E731
        repo_dir, removed = str(Path(root).resolve()), str(journal.STATE / "removed")
    done = sweep(sh, repo_dir, f"origin/{branch}", 0, removed, live_worktrees(), only={wt})
    ok = bool(done) and ": removed" in done[0]
    journal.append("sweep", worktree=wt, ok=ok, detail="; ".join(done) or "not swept: not a linked worktree of the repo, not landed, or a lane holds it")
    return (0 if ok else 1), ("; ".join(done) or "not swept: not landed, or a lane holds it")


def worktrees_of(sha: str) -> list[str]:
    """The scratch worktrees `builder work` fetched this sha from (its fetch rows name the worktree)."""
    return sorted({r["worktree"] for r in journal.read()
                   if r.get("event") == "work" and r.get("step") == "fetch" and r.get("detail") == sha and r.get("worktree")})


ISSUE_LINES = re.compile(r"^(Fixes|Closes|Part of|Already built):?\s*#(\d+)(.*)$", re.M | re.I)
TEST_FILE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|[^/]*Tests?\.swift)$")
BEHAVIOUR_ID = re.compile(r"^Behaviour:\s*`?([a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+)`?\s*$", re.M)  # a trailer line, never an id a message only mentions
OPEN_TAGS = ("[GAP]", "[PARTIAL]", "[PROPOSED]")
SPECS = Path("docs/contributor_manual/specs")


def commits_of(repo, base: str, sha: str) -> list[dict]:
    """[{sha, subject, message, tests}] of base..sha, oldest first; tests = the test files the commit touches."""
    out = []
    for c in _git(repo, "rev-list", "--reverse", f"{base}..{sha}").stdout.split():
        msg = _git(repo, "log", "-n1", "--format=%B", c).stdout
        files = _git(repo, "show", "--name-only", "--format=", c).stdout.split()
        out.append({"sha": c, "subject": msg.strip().split("\n", 1)[0], "message": msg, "tests": [f for f in files if TEST_FILE.search(f)]})
    return out


def cited_issues(repo, base: str, sha: str) -> list[dict]:
    """[{kind, number, rest, commit}] from every commit message of base..sha, oldest first: `Fixes #N` / `Closes #N` close,
    `Part of #N` comments, `Already built: #N <test>` comments with the proving test and labels."""
    out = []
    for c in commits_of(repo, base, sha):
        for m in ISSUE_LINES.finditer(c["message"]):
            kind, rest = m.group(1).lower(), m.group(3).strip()
            # `Fixes #7, #8` closes both; only a plain list right after the number: `Fixes #7 (see #9)` must not close #9
            more = [] if kind == "already built" else re.findall(r"#(\d+)", (re.match(r"(?:,\s*#\d+)*", rest) or [""])[0])
            out += [{"kind": kind, "number": int(n), "rest": rest, "commit": c} for n in [m.group(2), *more]]
    return out


def _gh(gh: str, *args) -> None:
    try:
        r = subprocess.run([gh, *args], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise Red(f"gh {' '.join(args[:2])} timed out") from None
    if r.returncode:
        raise Red(f"gh {' '.join(args[:2])}: {r.stderr.strip()[-300:]}")


def _what(c: dict) -> str:
    return f"{c['sha'][:7]} {c['subject']} ({', '.join(c['tests']) or 'no test file'})"


def update_issues(gh: str, cited: list[dict], branch: str, sha: str) -> list[str]:
    """One comment per cited issue per landing (sha, what landed, its tests; every citing commit in it): `Fixes`/`Closes`
    close with it (the land branch is not the default branch, so GitHub does not), `Part of` comments, `Already built`
    comments the proving test and labels the issue needs-your-test."""
    done = []
    note = f"landed on {branch} at {sha[:7]}"
    by_issue: dict[int, list[dict]] = {}
    for c in cited:
        by_issue.setdefault(c["number"], []).append(c)
    for n, cs in by_issue.items():
        kinds = {c["kind"] for c in cs}
        body = f"{note}: " + "; ".join(_what(c["commit"]) for c in cs)
        if kinds & {"fixes", "closes"}:
            _gh(gh, "issue", "close", str(n), "--comment", body)
            done.append(f"#{n} closed: {note}")
        elif kinds == {"already built"}:
            tests = ", ".join(c["rest"] for c in cs if c["rest"]) or "(none named)"
            _gh(gh, "issue", "comment", str(n), "--body", f"already built; the test that proves it: {tests} ({note})")
            _gh(gh, "issue", "edit", str(n), "--add-label", "needs-your-test")
            done.append(f"#{n} already built, labelled needs-your-test")
        else:
            _gh(gh, "issue", "comment", str(n), "--body", body)
            done.append(f"#{n} comment: {note}")
    return done


def mark_specs_ok(root, commits: list[dict], write: bool = True) -> list[dict]:
    """A behaviour id on a landed commit's `Behaviour: <id>` trailer line: its spec line's open tag becomes [OK], and the commit's test
    files are named on the line when it names none. [{file, id, tests}] of the lines changed (`write=False`: would change)."""
    wanted: dict[str, list[str]] = {}
    for c in commits:
        for bid in BEHAVIOUR_ID.findall(c["message"]):
            wanted.setdefault(bid, []).extend(t for t in c["tests"] if t not in wanted.get(bid, []))
    changed = []
    if not wanted:
        return changed
    for p in sorted((Path(root) / SPECS).rglob("*.md")):
        lines = p.read_text().split("\n")
        hit = False
        for k, ln in enumerate(lines):
            m = re.match(r"^- `([^`]+)` (\[[A-Z]+\])", ln)
            if not m or m.group(1) not in wanted or m.group(2) not in OPEN_TAGS:
                continue
            end = k + 1
            while end < len(lines) and lines[end].startswith("  "):
                end += 1
            tests = wanted[m.group(1)]
            ln = ln.replace(m.group(2), "[OK]", 1)
            if tests and not re.search(r"\bTests?\b|test_", "\n".join(lines[k:end])):
                ln += " Tests: " + ", ".join(f"`{t}`" for t in tests)
            lines[k] = ln
            hit = True
            changed.append({"file": p.relative_to(root).as_posix(), "id": m.group(1), "tests": tests})
        if hit and write:
            p.write_text("\n".join(lines))
    return changed


def main(a) -> int:
    rules = Path(a.root) / "harness.toml"
    pushed, cited = False, []
    if problem := land_tool.journal_problem(journal.path()):  # before any row: it allows the push and names what `scratch` removes
        print(f"REFUSED (journal): {problem}", file=sys.stderr)
        return 1

    def row(step: str, ok: bool, detail: str) -> None:
        journal.append("landed", sha=a.sha, step=step, ok=ok, detail=detail, **({"base": base} if step == "refresh" else {}))

    def step(name: str, fn) -> bool:
        try:
            detail = fn()
        except (Red, RuntimeError, OSError, ValueError, KeyError) as e:  # a refusal is a row and a line, never a traceback
            row(name, False, str(e))
            print(f"REFUSED ({name}): {e}", file=sys.stderr)
            return False
        row(name, True, detail or "ok")
        return True

    try:
        if problems := check_tool.rules_problems(a.root):  # the same refusal the land gate gives: one rules file, one answer
            raise ValueError("; ".join(problems))
        doc = tomllib.loads(rules.read_text())
        land = doc["land"]
        branch, pinned_dir = land["branch"], Path(land.get("pinned_dir", ""))
        repo = a.repo or doc.get("check", {}).get("engine_repo", "")
        j = jail.load(a.root)
        if not repo:
            raise ValueError("no --repo and no [check].engine_repo in the rules file")
        if not pinned_dir.is_absolute():
            raise ValueError(f"[land].pinned_dir {str(pinned_dir)!r} must be an absolute path (a relative one lands inside the repo)")
        if j is None or not j.user or not j.workroot:
            raise ValueError("no [jail] user and workroot in the rules file: the jail root has nowhere to be refreshed")
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as e:
        row("rules", False, str(e))
        print(f"REFUSED (rules file): {e}", file=sys.stderr)
        return 1
    # one full sha for every comparison: a short one typed never matches a check row's head (manager 2026-11-02)
    sha = _git(repo, "rev-parse", "--verify", "--end-of-options", f"{a.sha}^{{commit}}").stdout.strip()
    if not sha:
        row("sha", False, f"{a.sha!r} is not a commit in {repo}")
        print(f"REFUSED (sha): {a.sha!r} is not a commit in {repo}", file=sys.stderr)
        return 1
    a.sha = sha
    # the engine repo's local land branch can lag origin, and a check or review made over origin/<branch> is the same batch:
    # the verdict and the check row may be over either base (manager 2026-11-02)
    _git(repo, "fetch", "-q", "origin")
    bases = list(dict.fromkeys(x for x in (land_tool.resolve_branch(repo, branch),
                                           _git(repo, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}^{{commit}}").stdout.strip()) if x))

    def verdict():  # without --verdicts: the stores under --state (`builder work` and the queue write verdicts-<name>.json there)
        stores = [Path(a.verdicts)] if a.verdicts else sorted(journal.STATE.glob("verdicts*.json"))
        stops = []
        for store in stores:
            for b in bases:
                if not (stop := land_tool.unreviewed(repo, branch, sha, store, base=b)):
                    return f"READY for the exact range in {store}"
            stops += stop
        raise Red("no READY verdict: " + ("; ".join(stops) or f"no verdict store under {journal.STATE}"))

    def check_row():
        row_ = next((r for b in bases if (r := land_tool.green_row(journal.read(), sha, b))), None)
        if row_ is None:
            raise Red(f"no green `builder check` row over {branch}..{sha[:9]} in {journal.path()}")
        return "green check row" + (" (a maintainer batch)" if row_.get("maintainer") else "")

    def fast_forward():
        _ok(_git(repo, "fetch", "-q", "origin"), "fetch origin")
        if _git(repo, "merge-base", "--is-ancestor", f"refs/remotes/origin/{branch}", sha).returncode:
            raise Red(f"{sha[:9]} is not a fast-forward of origin/{branch}: rebase the lane and check again")
        return f"fast-forward of origin/{branch}"

    def boundary():
        if hits := land_tool.boundary(repo, base, sha, land["boundary"]):
            raise Red("the public boundary: " + "; ".join(hits))
        return "clear"

    def push():
        nonlocal pushed
        if not a.push:
            return "not pushed (no --push)"
        _ok(_git(repo, "push", "-q", "origin", f"{sha}:refs/heads/{branch}"), "push")
        pushed = True
        return f"pushed {sha[:9]} to origin/{branch}"

    def on_origin():
        _ok(_git(repo, "fetch", "-q", "origin"), "fetch origin")  # a push by hand counts; nothing below may run for a sha origin lacks
        if _git(repo, "merge-base", "--is-ancestor", sha, f"refs/remotes/origin/{branch}").returncode:
            raise Red(f"{sha[:9]} is not on origin/{branch}: nothing is pinned, removed or closed for it; push by hand or run again with --push")
        return f"on origin/{branch}"

    def refresh():
        _ok(_git(repo, "fetch", "-q", "origin"), "fetch origin")
        if _git(repo, "merge-base", "--is-ancestor", f"refs/heads/{branch}", f"refs/remotes/origin/{branch}").returncode:
            raise Red(f"the engine repo's {branch} is not behind origin/{branch}: not touched")
        _ok(_git(repo, "update-ref", f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"), "update-ref")
        return f"{branch} = origin/{branch} ({_git(repo, 'rev-parse', '--short', branch).stdout.strip()})"

    def pinned():
        try:  # it removes every other pinned copy, which another lane's running check may be reading: never wait for that check
            with journal.Lock("ladder", wait=False):
                return pin(repo, sha, pinned_dir)
        except BlockingIOError:
            return pin(repo, sha, pinned_dir, keep_others=True) + " (the older pinned copies kept: a check holds the ladder)"

    def jail_root():
        q, g = shlex.quote, shlex.quote(land_tool.GIT)
        # a local file equal to what lands is dropped first (a hand edit the landing now carries aborted the merge, 2026-11-02);
        # any other local edit stays and the merge refuses, naming it: never discarded. A failed fetch stops here: the merge
        # would take the FETCH_HEAD an earlier fetch left (review 2026-11-02)
        same = (f'{{ {g} -C root diff --name-only; {g} -C root ls-files --others --exclude-standard; }} | while IFS= read -r f; do '
                f'[ "$({g} -C root hash-object -- "$f")" = "$({g} -C root rev-parse -q --verify "FETCH_HEAD:$f" 2>/dev/null)" ] && '
                f'{{ {g} -C root checkout -q -- "$f" 2>/dev/null || rm -f -- "root/$f"; }}; done; ')
        return _ok(as_worker(j, f"{g} -C root fetch -q origin {q(branch)} || exit 1; {same}{g} -C root merge -q --ff-only FETCH_HEAD"), "jail root") or "root fast-forwarded"

    def scratch():  # never this landing's own worktree at once: a grace period, a patch, `git worktree remove` (#6204)
        grace = float(land.get("worktree_grace_hours", 36))
        done = sweep(lambda script: as_worker(j, script), "root", f"origin/{branch}", grace, f"{j.workroot}/.removed", live_worktrees())
        kept = "worktree kept: a lane's session is still working in it; " if a.keep_worktree else ""
        return kept + ("; ".join(done) or f"nothing past the {grace:g} h grace period")

    def spec_clean():
        if a.no_issues:
            return "skipped (--no-issues)"
        would = sorted({ch["file"] for ch in mark_specs_ok(a.root, commits_of(repo, base, sha), write=False)})
        status = {f: _git(a.root, "status", "--porcelain", "--", f) for f in would}
        if unread := [f for f, r in status.items() if r.returncode]:
            raise Red(f"the state of a spec file this landing would edit could not be read: {', '.join(unread)}")
        if dirty := [f for f, r in status.items() if r.stdout.strip()]:
            raise Red(f"a spec file this landing would edit has uncommitted changes: {', '.join(dirty)}")
        return "; ".join(would) or "no spec line to edit"

    def issues():
        cited[:] = cited_issues(repo, base, sha)
        if a.no_issues:
            return "skipped (--no-issues)"
        return "; ".join(update_issues(a.gh, cited, branch, sha)) or "no issue cited"

    def specs():
        if a.no_issues:
            return "untouched"
        changed = mark_specs_ok(a.root, commits_of(repo, base, sha))
        for ch in changed:
            journal.append("landed", sha=sha, step="spec-ok", ok=True, **ch)
        return "; ".join(f"{ch['file']}: `{ch['id']}` [OK]" for ch in changed) or "no behaviour line named"

    # a rerun after a red step past the refresh: the local branch has moved, so the range is empty and only the first run's base names it
    earlier = [r for r in journal.read() if r.get("event") == "landed" and r.get("sha") == sha]
    resume = None if any(r.get("step") == "done" for r in earlier) else next((r for r in earlier if r.get("step") == "refresh" and r.get("ok") and r.get("base")), None)
    pushed = any(r.get("step") == "push" and r.get("ok") and str(r.get("detail")).startswith("pushed") for r in earlier) if resume else False
    base = resume["base"] if resume else _git(repo, "merge-base", f"refs/heads/{branch}", sha).stdout.strip()  # the range: over the local branch BEFORE it is refreshed
    steps = [("verdict", verdict), ("check-row", check_row), ("fast-forward", fast_forward), ("boundary", boundary), ("spec-clean", spec_clean), ("push", push), ("on-origin", on_origin),
             # the push is the landing: its issues close at once, so a refresh that fails never loses them (manager 2026-11-02)
             ("issues", issues), ("refresh", refresh), ("pinned", pinned), ("jail-root", jail_root), ("scratch", scratch), ("specs", specs)]
    if resume:
        steps = steps[[n for n, _ in steps].index("refresh") + 1:]
    journal.append("activity", kind="land", key=f"land {sha[:9]}", state="start")
    for name, fn in steps:
        if not step(name, fn):
            journal.append("activity", kind="land", key=f"land {sha[:9]}", state="end", ok=False, failed=name)
            return 1
    journal.append("activity", kind="land", key=f"land {sha[:9]}", state="end", ok=True)
    closing = {c["number"] for c in cited if c["kind"] in ("fixes", "closes")}
    left_open = sorted({c["number"] for c in cited} - closing)  # a row, not a close: nothing is silently left (owner ruling)
    journal.append("landed", sha=sha, step="done", ok=True, branch=branch, pushed=pushed, detail="landed",
                   issues=sorted({c["number"] for c in cited}), left_open=left_open)
    print(f"landed {sha[:9]} on {branch}" + (" (pushed)" if pushed else " (not pushed)"))
    if left_open:
        print("left open: " + ", ".join(f"#{n}" for n in left_open))
    return 0
