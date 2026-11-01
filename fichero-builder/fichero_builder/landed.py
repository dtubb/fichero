"""`builder landed <sha> [--push]`: after a verdict, the maintainer runs ONE command instead of fifteen (dev-workflows.tool.landed).

Refuses unless the verdict store has READY for the sha, the owner's journal has a green check row for it and the sha is
a fast-forward of origin/<[land].branch> in the engine repo. Then, each step a journal row (event `landed`: step, ok,
detail) and a red step stops with its reason (exit 1): push (only with --push: the maintainer typed the flag, nothing
else sets it), the engine repo's local branch refreshed, a `pinned-<sha7>` branch and worktree under [land].pinned_dir
replacing the previous one, the jail root fast-forwarded as the worker user, the scratch worktrees of the work rows for
that sha removed, the issues the range cites updated, and a final `done` row (sha, branch, pushed, issues)."""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

from fichero_builder import jail, journal, land_tool


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run([land_tool.GIT, "-C", str(repo), *args], capture_output=True, text=True)


def as_worker(j: jail.Jail, script: str) -> subprocess.CompletedProcess:
    """`script` as the jail user from the workroot (the same boundary `builder work` crosses); a test replaces it."""
    return subprocess.run([j.sudo, "-n", "-H", "-u", j.user, "sh", "-c", f"cd {shlex.quote(j.workroot)} && {script}"],
                          capture_output=True, text=True)


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


def pin(repo, sha: str, pinned_dir: Path) -> str:
    """`pinned-<sha7>` as a branch and a worktree under pinned_dir; every other pinned-* branch and worktree goes."""
    name = f"pinned-{sha[:7]}"
    _ok(_git(repo, "branch", "-f", name, sha), "branch -f")
    for b, path in pinned_worktrees(repo).items():
        if b != name:
            _ok(_git(repo, "worktree", "remove", "--force", path), f"worktree remove {path}")
    for b in _git(repo, "branch", "--list", "pinned-*", "--format=%(refname:short)").stdout.split():
        if b != name:
            _ok(_git(repo, "branch", "-D", b), f"branch -D {b}")
    dest = pinned_dir / name
    if not dest.is_dir():
        pinned_dir.mkdir(parents=True, exist_ok=True)
        _ok(_git(repo, "worktree", "add", "-q", str(dest), name), "worktree add")
    return str(dest)


def worktrees_of(sha: str) -> list[str]:
    """The scratch worktrees `builder work` fetched this sha from (its fetch rows name the worktree)."""
    return sorted({r["worktree"] for r in journal.read()
                   if r.get("event") == "work" and r.get("step") == "fetch" and r.get("detail") == sha and r.get("worktree")})


ISSUE_LINES = re.compile(r"^(Fixes|Closes|Part of|Already built):?\s*#(\d+)(.*)$", re.M | re.I)


def cited_issues(repo, base: str, sha: str) -> list[dict]:
    """[{kind, number, rest}] from every commit message of base..sha, oldest first: `Fixes #N` / `Closes #N` close,
    `Part of #N` comments, `Already built: #N <test>` comments with the proving test and labels."""
    out = []
    for c in _git(repo, "rev-list", "--reverse", f"{base}..{sha}").stdout.split():
        msg = _git(repo, "log", "-n1", "--format=%B", c).stdout
        for m in ISSUE_LINES.finditer(msg):
            out.append({"kind": m.group(1).lower(), "number": int(m.group(2)), "rest": m.group(3).strip()})
    return out


def _gh(gh: str, *args) -> None:
    r = subprocess.run([gh, *args], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise Red(f"gh {' '.join(args[:2])}: {r.stderr.strip()[-300:]}")


def update_issues(gh: str, cited: list[dict], branch: str, sha: str) -> list[str]:
    """One gh call per cited issue; the lines written (for the row). `Fixes`/`Closes` close with a comment (the land
    branch is not the default branch, so GitHub does not), `Part of` comments, `Already built` comments with the test
    and labels the issue needs-your-test."""
    done = []
    note = f"landed on {branch} at {sha[:7]}"
    for c in cited:
        n = str(c["number"])
        if c["kind"] in ("fixes", "closes"):
            _gh(gh, "issue", "close", n, "--comment", note)
            done.append(f"#{n} closed: {note}")
        elif c["kind"] == "part of":
            _gh(gh, "issue", "comment", n, "--body", note)
            done.append(f"#{n} comment: {note}")
        else:
            body = f"already built; the test that proves it: {c['rest'] or '(none named)'} ({note})"
            _gh(gh, "issue", "comment", n, "--body", body)
            _gh(gh, "issue", "edit", n, "--add-label", "needs-your-test")
            done.append(f"#{n} already built, labelled needs-your-test")
    return done


def main(a) -> int:
    rules = Path(a.root) / "harness.toml"
    pushed, cited = False, []

    def row(step: str, ok: bool, detail: str) -> None:
        journal.append("landed", sha=a.sha, step=step, ok=ok, detail=detail)

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
    sha = a.sha

    def verdict():
        if stop := land_tool.unreviewed(repo, branch, sha, a.verdicts):
            raise Red("no READY verdict: " + "; ".join(stop))
        return "READY for the exact range"

    def check_row():
        if not any(r.get("event") == "check" and r.get("head") == sha and r.get("ok") is True for r in journal.read()):
            raise Red(f"no green `builder check` row for {sha[:9]} in {journal.path()}")
        return "green check row"

    def fast_forward():
        _ok(_git(repo, "fetch", "-q", "origin"), "fetch origin")
        if _git(repo, "merge-base", "--is-ancestor", f"refs/remotes/origin/{branch}", sha).returncode:
            raise Red(f"{sha[:9]} is not a fast-forward of origin/{branch}: rebase the lane and check again")
        return f"fast-forward of origin/{branch}"

    def push():
        nonlocal pushed
        if not a.push:
            return "not pushed (no --push)"
        _ok(_git(repo, "push", "-q", "origin", f"{sha}:refs/heads/{branch}"), "push")
        pushed = True
        return f"pushed {sha[:9]} to origin/{branch}"

    def refresh():
        _ok(_git(repo, "fetch", "-q", "origin"), "fetch origin")
        if _git(repo, "merge-base", "--is-ancestor", f"refs/heads/{branch}", f"refs/remotes/origin/{branch}").returncode:
            raise Red(f"the engine repo's {branch} is not behind origin/{branch}: not touched")
        _ok(_git(repo, "update-ref", f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"), "update-ref")
        return f"{branch} = origin/{branch} ({_git(repo, 'rev-parse', '--short', branch).stdout.strip()})"

    def jail_root():
        q = shlex.quote
        return _ok(as_worker(j, f"git -C root fetch -q origin {q(branch)} && git -C root merge -q --ff-only FETCH_HEAD"), "jail root") or "root fast-forwarded"

    def scratch():
        gone = []
        for wt in worktrees_of(sha):
            _ok(as_worker(j, f"rm -rf {shlex.quote(wt)} && git -C root worktree prune"), f"remove {wt}")
            gone.append(wt)
        return "removed " + ", ".join(gone) if gone else "no scratch worktree in the work rows"

    def issues():
        cited[:] = cited_issues(repo, base, sha)
        if a.no_issues:
            return "skipped (--no-issues)"
        return "; ".join(update_issues(a.gh, cited, branch, sha)) or "no issue cited"

    base = _git(repo, "merge-base", f"refs/heads/{branch}", sha).stdout.strip()  # the range: over the local branch BEFORE it is refreshed
    for name, fn in (("verdict", verdict), ("check-row", check_row), ("fast-forward", fast_forward), ("push", push), ("refresh", refresh),
                     ("pinned", lambda: pin(repo, sha, pinned_dir)), ("jail-root", jail_root), ("scratch", scratch), ("issues", issues)):
        if not step(name, fn):
            return 1
    journal.append("landed", sha=sha, step="done", ok=True, branch=branch, pushed=pushed, detail="landed",
                   issues=sorted({c["number"] for c in cited}))
    print(f"landed {sha[:9]} on {branch}" + (" (pushed)" if pushed else " (not pushed)"))
    return 0
