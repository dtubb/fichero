"""The check tool: plain argv commands, each with a cwd and a timeout, typed results.

(dev-workflows.tool.check, #6116.) No shell, no route yet. Nothing here names a project: what to run comes from the
project's `harness.toml` `[check]` table (`load`), Fichero being the first project. Rungs: `ready`, `pytest_rung`,
`guards`, `contract_current`, `diff_bound`, `red_on_base`, composed by `run_ladder`. A red or missing program is a
result, never a raise.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """One project's rules; the all-default Config runs nothing project-specific."""
    python: str = ""                    # interpreter for pytest and guards; "" = the engine's own
    python_path: tuple = ()             # folders (relative to the repo) put on PYTHONPATH
    test_env: dict = field(default_factory=dict)  # env for every test and guard run
    base_path_env: str = ""             # env var given a fresh scratch dir per pytest run ("" = none)
    ready: tuple = ()                   # argv of the project's readiness check ("" = none)
    guard_glob: str = ""                # e.g. "scripts/check_*.py"; "" = no guards rung
    guard_skip: frozenset = frozenset()  # guard names the nightly gate runs instead
    guard_timeout_s: float = 60
    min_guards: int = 0                 # fewer guards found than this = blind = not green
    contract_paths: tuple = ()          # a diff touching these runs the contract guards
    contract_guards: tuple = ()         # guard script paths (relative)
    check_paths: tuple = ()             # files/folders that judge a diff: run from the pinned copy, never the worker's
    test_globs: tuple = ("test_*.py", "*_test.py")
    max_files: int = 25
    max_lines: int = 1500


def load(root) -> Config:
    """`<root>/harness.toml` [check]; no file = the default Config."""
    f = Path(root) / "harness.toml"
    if not f.is_file():
        return Config()
    c = tomllib.loads(f.read_text()).get("check", {})
    d = Config()
    return Config(
        python=c.get("python", d.python), python_path=tuple(c.get("python_path", d.python_path)),
        test_env=dict(c.get("test_env", {})), base_path_env=c.get("base_path_env", d.base_path_env),
        ready=tuple(c.get("ready", d.ready)), guard_glob=c.get("guard_glob", d.guard_glob),
        guard_skip=frozenset(c.get("guard_skip", ())), guard_timeout_s=c.get("guard_timeout_s", d.guard_timeout_s),
        min_guards=c.get("min_guards", d.min_guards), contract_paths=tuple(c.get("contract_paths", d.contract_paths)),
        contract_guards=tuple(c.get("contract_guards", d.contract_guards)),
        check_paths=tuple(c.get("check_paths", d.check_paths)), test_globs=tuple(c.get("test_globs", d.test_globs)), max_files=c.get("max_files", d.max_files),
        max_lines=c.get("max_lines", d.max_lines))


def tail(text: str, lines: int = 40, chars: int = 4000, line_chars: int = 300) -> str:
    kept = [ln[:line_chars] for ln in (text or "").strip().splitlines()[-lines:]]
    return "\n".join(kept)[-chars:]


def run_command(name: str, argv: list[str], cwd, timeout_s: float, env: dict | None = None) -> dict:
    """Run argv (own process group, killed whole on timeout) and return the typed result."""
    t = time.time()
    out = err = ""
    code: int | None = None
    timed_out = False
    try:
        p = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
    except OSError as e:
        err = str(e)
    else:
        try:
            out, err = p.communicate(timeout=timeout_s)
            code = p.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = p.communicate()
    return {"name": name, "argv": list(argv), "exit_code": code, "ok": code == 0 and not timed_out,
            "timed_out": timed_out, "seconds": round(time.time() - t, 1),
            "stdout_tail": tail(out), "stderr_tail": tail(err)}


def _env(root, cfg: Config, extra: dict | None = None) -> dict:
    # a scratch HOME: no gh token, no ~/.gitconfig credential helper, no user settings reach a check or a worker's conftest
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "TERM", "LANG")}
    env["HOME"] = tempfile.mkdtemp(prefix="check-home-")
    if cfg.base_path_env:
        env[cfg.base_path_env] = tempfile.mkdtemp(prefix="check-base-")
    if cfg.python_path:
        env["PYTHONPATH"] = ":".join(str(Path(root) / p) for p in cfg.python_path)
    env.update(cfg.test_env)
    env.update(extra or {})
    return env


def _py(cfg: Config) -> str:
    return cfg.python or sys.executable


def _skipped(name: str) -> dict:
    return {"name": name, "argv": [], "exit_code": 0, "ok": True, "timed_out": False, "seconds": 0,
            "stdout_tail": "skipped: not configured", "stderr_tail": ""}


def ready(root, cfg: Config, timeout_s: float = 600) -> dict:
    if not cfg.ready:
        return _skipped("ready")
    argv = [str(Path(root) / cfg.ready[0]) if "/" in cfg.ready[0] and not cfg.ready[0].startswith("/") else cfg.ready[0],
            *cfg.ready[1:]]
    return run_command("ready", argv, root, timeout_s, _env(root, cfg))


def pytest_rung(root, files: list[str], cfg: Config = Config(), timeout_s: float = 1800) -> dict:  # noqa: B008
    """Named test files only (the env gives a fresh base path, so a run never opens real data)."""
    if not files:
        return run_command("pytest", [sys.executable, "-c", "import sys; sys.exit('no test files named')"], root, 5)
    return run_command("pytest", [_py(cfg), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", *files],
                       root, timeout_s, _env(root, cfg))


def _isolated(script: Path, root: Path, cfg: Config) -> list[str]:
    """`python -I` so a planted sitecustomize/.pth is never imported; the tree's paths go in after site."""
    paths = [str(script.parent), *[str(root / p) for p in cfg.python_path]]
    code = ("import sys, runpy; i = next((n for n, p in enumerate(sys.path) if 'site-packages' in p), len(sys.path)); "
            f"sys.path[i:i] = {paths!r}; runpy.run_path({str(script)!r}, run_name='__main__')")
    return [_py(cfg), "-I", "-c", code]


def guards(root, cfg: Config) -> dict:
    """Every guard script matching the project's glob and not in its skip list. Fewer than `min_guards` found =
    blind = not green."""
    root = Path(root)
    if not cfg.guard_glob:
        return {"ok": True, "reason": "skipped: not configured", "results": []}
    found = sorted(root.glob(cfg.guard_glob))
    if len(found) < cfg.min_guards:
        return {"ok": False, "reason": f"fewer than {cfg.min_guards} guards found ({len(found)}): blind is not green",
                "results": []}
    results = []
    for s in found:
        if s.stem in cfg.guard_skip:
            continue
        r = run_command(s.stem, _isolated(s, root, cfg), root, cfg.guard_timeout_s, _env(root, cfg))
        r["argv"] = [str(s)]
        results.append(r)
    return {"ok": all(r["ok"] for r in results), "reason": "", "results": results}


def contract_current(root, changed: list[str], cfg: Config, timeout_s: float = 300) -> dict:
    """The project's contract guards, only when the diff touches its contract paths."""
    if not cfg.contract_guards or not any(f.startswith(cfg.contract_paths) for f in changed):
        return {"ok": True, "skipped": True, "results": []}
    root = Path(root)
    results = [run_command(Path(g).stem, _isolated(root / g, root, cfg), root, timeout_s, _env(root, cfg))
               for g in cfg.contract_guards]
    return {"ok": all(r["ok"] for r in results), "skipped": False, "results": results}


def _git(root, *args, timeout_s: float = 60) -> dict:
    # hooks and fsmonitor off, as the frozen pipeline ran every git
    return run_command("git", ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args], root, timeout_s)


def _lines(root, *args) -> list[str] | None:
    """git stdout, whole (the typed result's tail is capped); None on failure."""
    r = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
                       cwd=str(root), capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else None


def diff_bound(root, since: str, head: str, cfg: Config) -> dict:
    """The diff since the item's start stays inside a size bound (files and added+removed lines).
    ponytail: a size bound only; a per-folder scope bound if workers wander."""
    out = _lines(root, "diff", "--numstat", f"{since}...{head}")
    if out is None:
        return {**_git(root, "diff", "--numstat", f"{since}...{head}"), "name": "diff-bound"}
    r = _git(root, "rev-parse", "--short", head)  # a typed shell of the result
    rows = [ln.split("\t") for ln in out if ln.count("\t") == 2]
    lines = sum(int(a) + int(d) for a, d, _ in rows if a.isdigit() and d.isdigit())
    msg = ""
    if len(rows) > cfg.max_files:
        msg = f"diff bound: {len(rows)} files, over {cfg.max_files}"
    elif lines > cfg.max_lines:
        msg = f"diff bound: {lines} lines, over {cfg.max_lines}"
    return {**r, "name": "diff-bound", "ok": not msg, "stderr_tail": msg}


def red_on_base(root, since: str, head: str, files: list[str], cfg: Config = Config(), timeout_s: float = 600,  # noqa: B008
                head_tree=None) -> dict:
    """The failing run: each changed test file, copied onto a scratch tree at `since`, must FAIL there on its
    own, and all must PASS at `head`. A test that passes on base proves nothing."""
    root = Path(root)

    def red(msg: str) -> dict:
        return {"name": "red-on-base", "argv": [], "exit_code": 1, "ok": False, "timed_out": False, "seconds": 0,
                "stdout_tail": "", "stderr_tail": msg}
    if not files:
        return red("no test file changed: a source change needs a test (red on base, green on the branch)")
    sha = _git(root, "rev-parse", head)["stdout_tail"].strip()  # `HEAD` inside the scratch tree would be `since`
    base = tempfile.mkdtemp(prefix="check-base-tree-")
    try:
        if not _git(root, "worktree", "add", "--detach", "-q", base, since)["ok"]:
            return red(f"could not make a scratch tree at {since[:9]}")
        _git(base, "checkout", sha, "--", *files)  # a new file is not on base; checkout still copies it
        for f in files:
            r = pytest_rung(base, [f], cfg, timeout_s)
            if r["ok"]:
                return red(f"NOT RED ON BASE: {f} passes at {since[:9]}, so it proves nothing")
        here = pytest_rung(head_tree or root, files, cfg, timeout_s)  # the green run: in the pinned-overlay tree when given
        return {**here, "name": "red-on-base"}
    finally:
        _git(root, "worktree", "remove", "--force", base)


def ladder(rungs: list) -> dict:
    """Run (name, callable) rungs in order and stop at the first red, so the worker gets one failure at a time."""
    out = []
    for name, fn in rungs:
        r = {"name": name, **fn()}
        out.append(r)
        if not r["ok"]:
            return {"ok": False, "failed": name, "rungs": out}
    return {"ok": True, "failed": "", "rungs": out}


BYPASS_NAMES = ("sitecustomize.py", "usercustomize.py")


def pinned_violations(root, since: str, head: str, cfg: Config, pinned) -> list[str]:
    """What the diff may not do: change or delete a pinned check file, add a file that would run before or instead of
    the checks (sitecustomize, .pth, a conftest outside a test folder), or touch .claude/ (a hook there runs outside
    any check). Adding a new guard is allowed. Ported from the frozen pipeline's pinned-checks."""
    pinned_set = {f for f in (_lines(pinned, "ls-files") or []) if f.startswith(cfg.check_paths)}
    bad = []
    for row in _lines(root, "diff", "--name-status", "--no-renames", f"{since}...{head}") or []:
        status, f = row.split("\t", 1)
        name, parts = Path(f).name, Path(f).parts
        if f in pinned_set:
            bad.append(f"{f}: a pinned check file was {'deleted' if status == 'D' else 'changed'}")
        elif f.startswith(".claude/"):
            bad.append(f"{f}: .claude/ changed")
        elif status == "A" and (name in BYPASS_NAMES or name.endswith(".pth")
                                or (name == "conftest.py" and not any("test" in x.lower() for x in parts[:-1]))):
            bad.append(f"{f}: would run before or instead of the checks")
    return bad


def _scratch_tree(root, head: str, pinned, cfg: Config) -> str:
    """A detached worktree of `head` with the pinned copy's check files laid over it: the checks judge the worker's
    committed code, never its uncommitted edits and never its own copies of the checks."""
    sha = (_lines(root, "rev-parse", head) or [""])[0]
    tree = tempfile.mkdtemp(prefix="check-tree-")
    r = _git(root, "worktree", "add", "--detach", "-q", tree, sha)
    if not r["ok"]:
        raise RuntimeError(f"scratch tree failed: {r['stderr_tail']}")
    for f in _lines(pinned, "ls-files") or []:
        if f.startswith(cfg.check_paths):
            dest = Path(tree) / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((Path(pinned) / f).read_bytes())
            dest.chmod((Path(pinned) / f).stat().st_mode)
    return tree


def run_ladder(root, since: str, head: str, pinned) -> dict:
    """The project's whole ladder over the diff since..head, judged by the PINNED copy (an engine-owned checkout
    outside the worker's tree; its harness.toml is the config): pinned-checks, ready, diff bound, red-on-base for
    the changed test files (its green run is the pytest rung), guards, contract. Stops at the first red.
    ponytail: weakened-test and spec-acceptance rules of the frozen pipeline are not ported yet."""
    import fnmatch
    cfg = load(pinned)
    bad = pinned_violations(root, since, head, cfg, pinned)
    if bad:
        r = {"name": "pinned-checks", "argv": [], "exit_code": 1, "ok": False, "timed_out": False, "seconds": 0,
             "stdout_tail": "", "stderr_tail": "\n".join(bad) + "\nneeds-maintainer"}
        return {"ok": False, "failed": "pinned-checks", "rungs": [r]}
    names = [ln.split("\t", 1)[1] for ln in _lines(root, "diff", "--name-status", "--no-renames", "--diff-filter=AM",
                                                    f"{since}...{head}") or []]
    tests = [f for f in names if any(fnmatch.fnmatch(Path(f).name, g) for g in cfg.test_globs)]
    tree = _scratch_tree(root, head, pinned, cfg)
    try:
        ok_pin = {"name": "pinned-checks", "argv": [], "exit_code": 0, "ok": True, "timed_out": False, "seconds": 0,
                  "stdout_tail": f"checks from the pinned copy over {head}", "stderr_tail": ""}
        out = ladder([
            ("ready", lambda: ready(tree, cfg)),
            ("diff-bound", lambda: diff_bound(root, since, head, cfg)),
            ("red-on-base", lambda: red_on_base(root, since, head, tests, cfg, head_tree=tree)),
            ("guards", lambda: guards(tree, cfg)),
            ("contract-current", lambda: contract_current(tree, names, cfg)),
        ])
    finally:
        _git(root, "worktree", "remove", "--force", tree)
    return {**out, "rungs": [ok_pin, *out["rungs"]]}
