"""The check tool: plain argv commands, each with a cwd and a timeout, typed results.

(dev-workflows.tool.check, #6116.) No shell, no route yet. Nothing here names a project: what to run comes from the
project's `harness.toml` `[check]` table (`load`), Fichero being the first project. Rungs: `ready`, `pytest_rung`,
`guards`, `contract_current`, `diff_bound`, `red_on_base`, composed by `run_ladder`. A red or missing program is a
result, never a raise.
"""

from __future__ import annotations

import ast
import fcntl
import fnmatch
import importlib.util
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """One project's rules; the all-default Config runs nothing project-specific."""
    python: str = ""                    # interpreter for pytest and guards; "" = the engine's own
    path: str = ""                      # PATH for every rung ("" = the caller's); the jail user needs its own tools, not the owner's
    python_path: tuple = ()             # folders (relative to the repo) put on PYTHONPATH
    test_env: dict = field(default_factory=dict)  # env for every test and guard run
    base_path_env: str = ""             # env var given a fresh scratch dir per pytest run ("" = none)
    ready: tuple = ()                   # argv of the project's readiness check ("" = none)
    base_ref: str = ""                  # e.g. "origin/main": the ref the ready check diffs against; set in a remote-less clone ("" = leave alone)
    guard_glob: str = ""                # e.g. "scripts/check_*.py"; "" = no guards rung
    guard_skip: frozenset = frozenset()  # guard names the nightly gate runs instead
    guard_timeout_s: float = 60
    min_guards: int = 0                 # fewer guards found than this = blind = not green
    contract_paths: tuple = ()          # a diff touching these runs the contract guards
    contract_guards: tuple = ()         # guard script paths (relative)
    since_guards: dict = field(default_factory=dict)  # {guard path: path prefix}: a diff under the prefix runs the guard with `--since <base>`
    spec_dir: str = ""                  # folder of the specs whose item acceptance a worker may not rewrite ("" = none)
    check_paths: tuple = ()             # files/folders that judge a diff: run from the pinned copy, never the worker's
    red_paths: tuple = ()               # a diff touching these (prefixes) needs a failing-on-base test; () = any file
    whole_tests: dict = field(default_factory=dict)  # {path prefix: tests dir}: a diff under the prefix runs that dir WHOLE in the green run
    test_globs: tuple = ("test_*.py", "*_test.py")
    pytest_config: str = ""             # the pinned pytest config file (relative to the tree), passed as `-c`; "" = pytest's own search
    pytest_plugins: tuple = ()          # plugins loaded by -p; autoload is OFF, so a dist-info entry point in the tree loads nothing
    max_files: int = 25
    max_lines: int = 1500
    build_paths: tuple = ()             # a diff touching these (prefixes) runs the build rung; () = no build rung
    build: tuple = ()                   # argv of a build-only compile (never a test run), run in the scratch tree
    build_timeout_s: float = 1800
    build_lock: str = ""                # a lock file: one build at a time on the machine ("" = no lock)
    remote: str = ""                    # "host:dir": the engine pytest runs go over ssh to that machine ("" = here); unreachable = an alert, then here
    remote_python: str = ""             # the interpreter there ("" = <dir>/venv/bin/python)
    engine_repo: str = ""               # the engine-owned repository check and land judge from: outside every home dir, readable by the jailed user ("" = the caller names one)


def load(root) -> Config:
    """`<root>/harness.toml` [check]; no file = the default Config."""
    f = Path(root) / "harness.toml"
    if not f.is_file():
        return Config()
    doc = tomllib.loads(f.read_text())
    c = doc.get("check", {})
    if unknown := sorted(set(c) - {x.name for x in fields(Config)} - {"test_env"}):  # fail closed (review 3, spec item 2)
        raise ValueError(f"harness.toml [check]: unknown keys {unknown}")
    if unknown := sorted(set(doc) - {"check", "jail", "policy", "land", "brief", "spend", "models", "triage", "queue", "loop"}):
        raise ValueError(f"harness.toml: unknown tables {unknown}")
    brief = doc.get("brief", {})
    if unknown := sorted(set(brief) - {"rules"}):
        raise ValueError(f"harness.toml [brief]: unknown keys {unknown}")
    if not isinstance(brief.get("rules", ""), str):
        raise ValueError("harness.toml [brief]: rules must be text")
    d = Config()
    return Config(
        python=c.get("python", d.python), python_path=tuple(c.get("python_path", d.python_path)),
        path=c.get("path", d.path), test_env=dict(c.get("test_env", {})), base_path_env=c.get("base_path_env", d.base_path_env),
        ready=tuple(c.get("ready", d.ready)), base_ref=c.get("base_ref", d.base_ref), guard_glob=c.get("guard_glob", d.guard_glob),
        guard_skip=frozenset(c.get("guard_skip", ())), guard_timeout_s=c.get("guard_timeout_s", d.guard_timeout_s),
        min_guards=c.get("min_guards", d.min_guards), contract_paths=tuple(c.get("contract_paths", d.contract_paths)),
        contract_guards=tuple(c.get("contract_guards", d.contract_guards)), since_guards=dict(c.get("since_guards", {})),
        whole_tests=dict(c.get("whole_tests", {})), spec_dir=c.get("spec_dir", d.spec_dir), check_paths=tuple(c.get("check_paths", d.check_paths)), red_paths=tuple(c.get("red_paths", d.red_paths)), test_globs=tuple(c.get("test_globs", d.test_globs)),
        pytest_config=c.get("pytest_config", d.pytest_config), pytest_plugins=tuple(c.get("pytest_plugins", d.pytest_plugins)), max_files=c.get("max_files", d.max_files),
        max_lines=c.get("max_lines", d.max_lines), build_paths=tuple(c.get("build_paths", d.build_paths)),
        build=tuple(c.get("build", d.build)), build_timeout_s=c.get("build_timeout_s", d.build_timeout_s),
        build_lock=c.get("build_lock", d.build_lock), engine_repo=c.get("engine_repo", d.engine_repo),
        remote=c.get("remote", d.remote), remote_python=c.get("remote_python", d.remote_python))


def rules_problems(root) -> list[str]:
    """Every reason the rules file is not good enough to start, check or land on; empty = fine (review 4 B5).
    One function for start, the ladder and land: a file the start refuses never lands."""
    from . import jail as _j
    f = Path(root) / "harness.toml"
    if not f.is_file():
        return [f"{f} is missing"]
    try:
        c = load(root)
        tomllib.loads(f.read_text())
        j = _j.load(root)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        return [f"harness.toml: {e}"]
    out: list[str] = []
    if j is None:
        out.append("harness.toml has no [jail]: nothing runs unjailed")
    elif not j.user:
        out.append("[jail].user is not set")
    elif not j.deny_read:
        out.append("[jail].deny_read is empty: the probe needs paths to prove unreadable")
    for name, val in (("python", c.python), ("ready", c.ready), ("guard_glob", c.guard_glob), ("min_guards", c.min_guards),
                      ("contract_guards", c.contract_guards), ("check_paths", c.check_paths), ("contract_paths", c.contract_paths),
                      ("pytest_config", c.pytest_config)):  # review-2 H10: an unlisted key must not fail open
        if not val:
            out.append(f"harness.toml [check].{name} is not declared")
    if c.python and not Path(c.python).is_absolute():
        out.append(f"[check].python {c.python!r} must be an absolute path (no PATH lookup, no shim)")
    if c.engine_repo and not (Path(c.engine_repo) / ".git").exists():  # first real check 2026-11-01: a tree under ~ is unreadable to the jailed user
        out.append(f"[check].engine_repo {c.engine_repo!r} is not a git repository (clone the owner's repo there, readable by the jailed user)")
    land = tomllib.loads(f.read_text()).get("land", {})
    if unknown := sorted(set(land) - {"branch", "boundary", "pinned_dir", "worktree_grace_hours"}):
        out.append(f"harness.toml [land]: unknown keys {unknown}")
    for k in ("branch", "boundary"):
        if not land.get(k):
            out.append(f"harness.toml [land].{k} is not declared")
    return out


FAILURES = re.compile(r"^=+ (?:FAILURES|ERRORS) =+$")


def tail(text: str, lines: int = 40, chars: int = 4000, line_chars: int = 300) -> str:
    """The last lines, bounded. A pytest failure section is kept whatever follows it: its end (the `E` lines) plus the run's
    end, half the bound each; 40 lines of warnings once pushed the failure out of a red rung."""
    all_lines = [ln[:line_chars] for ln in (text or "").strip().splitlines()]
    start = next((i for i, ln in enumerate(all_lines) if FAILURES.match(ln)), None)
    last = all_lines[-lines:]
    if start is None or start >= len(all_lines) - lines:
        return "\n".join(last)[-chars:]
    stop = next((i for i in range(start + 1, len(all_lines)) if all_lines[i].startswith("=")), len(all_lines))
    failure = "\n".join(all_lines[start:stop][-(lines // 2):])[-(chars // 2):]
    return failure + "\n...\n" + "\n".join(all_lines[-(lines // 2 - 1):])[-(chars // 2):]


_JAIL = None  # ponytail: module state set by run_ladder for the length of one ladder; per-call plumbing if two ladders overlap


def _mkdtemp(prefix: str, readable: bool = False) -> str:
    if _JAIL is not None:
        d = _JAIL.mkdtemp(prefix)  # under the shared workroot, writable by the jailed user
    else:
        d = tempfile.mkdtemp(prefix=prefix)
    if readable:
        os.chmod(d, 0o755)  # a tree the jailed user reads (public repo content only)
    return d


def run_command(name: str, argv: list[str], cwd, timeout_s: float, env: dict | None = None, as_jail: bool = True) -> dict:
    """Run argv (own process group, killed whole on timeout) and return the typed result. While a ladder runs under a
    jail, everything but the engine's own git steps runs as the jailed user."""
    if _JAIL is not None and as_jail:
        argv, env, cwd = _JAIL.argv(argv, cwd=cwd, env=env), {"PATH": os.environ.get("PATH", "")}, "/"
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
    if cfg.path:
        env["PATH"] = cfg.path
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"  # review 4 B6: only [check].pytest_plugins load, never a tree's entry points
    env["RUFF_NO_CACHE"] = "true"                 # the scratch tree is owner-made and read-only to the jailed user: no caches in it
    env["HOME"] = tempfile.mkdtemp(prefix="check-home-")  # (jailed: dropped, the user's own HOME is used)
    if cfg.base_path_env:
        env[cfg.base_path_env] = _mkdtemp("check-base-")
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


_SHIPPED: dict = {}  # local tree -> its copy on [check].remote, for this ladder; removed at the end (_drop_remote)
_DOWN: list = []  # the remote failed once in this ladder: one alert, then every run here


def _ssh(host: str, script: str, timeout_s: float, stdin=None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script], input=stdin,
                              capture_output=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError) as e:
        return subprocess.CompletedProcess([], 255, b"", str(e).encode())


def _ship(root, cfg: Config) -> str:
    """The tree's files (tracked and the overlay's untracked ones, never .git) into a fresh dir on the remote; its absolute path."""
    root = str(root)
    if root in _SHIPPED:
        return _SHIPPED[root]
    host, _, base = cfg.remote.partition(":")
    mk = _ssh(host, f'mkdir -p {base or "."} && cd {base or "."} && d=$(mktemp -d "$PWD/run-XXXXXX") && echo "$d"', 30)
    rdir = mk.stdout.decode().strip()
    if mk.returncode or not rdir.startswith("/"):
        raise OSError(f"{host}: {(mk.stderr.decode().strip() or 'no run dir')[-200:]}")
    names = subprocess.run(_git_argv(root, ["ls-files", "-z", "-co", "--exclude-standard"]), cwd=root, capture_output=True, env=_git_env()).stdout
    tar = subprocess.run(["tar", "-C", root, "--null", "-T", "-", "-czf", "-"], input=names, capture_output=True)
    up = _ssh(host, f"tar -xzf - -C {shlex.quote(rdir)}", 600, stdin=tar.stdout)
    if tar.returncode or up.returncode:
        _ssh(host, f"rm -rf {shlex.quote(rdir)}", 60)
        raise OSError(f"{host}: copy failed: {(tar.stderr or up.stderr).decode().strip()[-200:]}")
    _SHIPPED[root] = rdir
    return rdir


def _drop_remote(cfg: Config) -> None:
    for rdir in _SHIPPED.values():
        _ssh(cfg.remote.partition(":")[0], f"rm -rf {shlex.quote(rdir)}", 120)
    _SHIPPED.clear()
    _DOWN.clear()


def _remote_run(name, argv, root, timeout_s, cfg: Config, extra: dict | None, cwd) -> dict | None:
    """The same pytest command on [check].remote over the shipped tree: local paths become the copy's, the interpreter the
    remote's, the env the rung's own keys (a fresh base dir there). None when the remote cannot be reached: one alert row,
    and the caller runs it here (progress never waits on that machine). ponytail: the remote runs the tests unjailed as the
    ssh user; that machine holds nothing but its gate dir."""
    host, _, base = cfg.remote.partition(":")
    try:
        rdir = _ship(root, cfg)
    except OSError as e:
        return _remote_down(cfg, str(e))
    py = cfg.remote_python or f"{rdir.rsplit('/', 1)[0]}/venv/bin/python"
    sub = lambda x: str(x).replace(str(root), rdir)  # noqa: E731
    cmd = [py if a == _py(cfg) else sub(a) for a in argv]
    env = {k: sub(v) for k, v in _env(root, cfg, extra).items() if k not in ("HOME", "PATH", "TERM", cfg.base_path_env)}
    kv = " ".join(shlex.quote(f"{k}={v}") for k, v in env.items())
    bp = f'{cfg.base_path_env}="$B" ' if cfg.base_path_env else ""
    script = (f'cd {shlex.quote(sub(cwd or root))} && B=$(mktemp -d) && env -i HOME="$HOME" PATH=/usr/bin:/bin {kv} {bp}'
              f'{shlex.join(cmd)}; rc=$?; rm -rf "$B"; exit $rc')
    r = run_command(name, ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script], root, timeout_s, None, as_jail=False)
    if r["exit_code"] == 255:  # ssh's own failure, never pytest's
        return _remote_down(cfg, r["stderr_tail"][-200:])
    return {**r, "remote": host}


def _remote_down(cfg: Config, why: str) -> None:
    from . import queue
    _DOWN.append(why)
    queue.alert("check", "remote", f"the check runner {cfg.remote} is unreachable; the tests ran here: {why}", cfg.remote, [])
    return None


def _run(name, argv, root, timeout_s, cfg: Config, extra: dict | None = None, cwd=None, remote: bool = False) -> dict:
    """run_command with a fresh scratch env, its HOME and base dirs removed afterwards (no litter per rung). `remote`: an
    engine pytest run, sent to [check].remote when one is set."""
    if remote and cfg.remote and not _DOWN and (r := _remote_run(name, argv, root, timeout_s, cfg, extra, cwd)) is not None:
        return r
    env = _env(root, cfg, extra)
    try:
        return run_command(name, argv, cwd or root, timeout_s, env)
    finally:
        for d in (env["HOME"], env.get(cfg.base_path_env or "")):
            if d:
                _remove_scratch(d)


def _remove_scratch(d: str) -> None:
    """A scratch dir the jailed user wrote into is removed AS that user (the owner cannot delete its files: nine
    check-base dirs were left behind on 2026-11-01); unjailed, a plain rmtree."""
    if _JAIL is not None:
        run_command("cleanup", ["rm", "-rf", d], "/", 60)
    shutil.rmtree(d, ignore_errors=True)


def ready(root, cfg: Config, timeout_s: float = 600) -> dict:
    if not cfg.ready:
        return _skipped("ready")
    argv = [str(Path(root) / cfg.ready[0]) if "/" in cfg.ready[0] and not cfg.ready[0].startswith("/") else cfg.ready[0],
            *cfg.ready[1:]]
    return _run("ready", argv, root, timeout_s, cfg)


def pytest_argv(root, files: list[str], cfg: Config, package: str = "") -> list[str]:
    """The engine-shaped command (cwd = the tree root, the pinned `-c`), or with `package` a whole-tests run: its own
    pytest from that package dir, `-c <package>/pyproject.toml` only when it exists, the package dir FIRST on the path
    (so `from tests import x` finds its own `tests`), and only the plugins installed for it."""
    pkg = Path(root) / package if package else None
    conf = (pkg / "pyproject.toml" if pkg.joinpath("pyproject.toml").is_file() else None) if pkg else (Path(root) / cfg.pytest_config if cfg.pytest_config else None)
    cfgfile = ["-c", str(conf)] if conf else []
    plugins = [x for p in cfg.pytest_plugins for x in ("-p", p)]
    paths = [str(Path(root) / p) for p in cfg.python_path]
    if pkg:
        paths.insert(0, str(pkg))
        plugins = [x for p in cfg.pytest_plugins if importlib.util.find_spec(p) for x in ("-p", p)]
    args = ["-q", "-p", "no:cacheprovider", "-x", *cfgfile, *plugins, *files]
    # review 5 N5 + review 6 R1: `python -I` (no PYTHONPATH, no cwd); the tree's folders go in RIGHT AFTER the site-packages
    # directory: after it, so a planted src/pluggy.py shadows no installed package, and before what its .pth files add,
    # so an editable install never replaces the commit under test. (`_isolated` for guards inserts before site-packages.)
    # THE LIMIT: tests run the worker's own code, so a green is never proof against a hostile worker (a test file can
    # always exit 0). The reviewer is the wall; land_tool.risky_paths makes it name the files that forge a green cheaply.
    # a throwaway pycache prefix per rung (`-I` ignores PYTHON* env vars): pytest's assertion-rewrite cache keys on mtime
    # seconds + size, so a same-size edit in the same second would otherwise run the PREVIOUS rung's bytecode of a test
    # (the already-built red-on-base test flaked 1 in 3 on 2026-11-01)
    code = ("import sys, shutil, tempfile; i = next((n for n, p in enumerate(sys.path) if p.endswith('site-packages')), len(sys.path) - 1) + 1; "
            f"sys.path[i:i] = {paths!r}\n"
            "sys.pycache_prefix = tempfile.mkdtemp(prefix='check-pyc-')\n"
            f"import pytest; rc = pytest.main({args!r}); shutil.rmtree(sys.pycache_prefix, ignore_errors=True); sys.exit(rc)")
    return [_py(cfg), "-I", "-c", code]


def pytest_rung(root, files: list[str], cfg: Config = Config(), timeout_s: float = 1800) -> dict:  # noqa: B008
    """Named test files only (the env gives a fresh base path, so a run never opens real data)."""
    if not files:
        return run_command("pytest", [sys.executable, "-c", "import sys; sys.exit('no test files named')"], root, 5)
    # safe-path for the test run only: the cwd is not on sys.path, so a worker's pytest.py shadows nothing. The ready and
    # guard rungs run the project's own pinned scripts, which import helpers beside them (first real check, 2026-11-01).
    return _run("pytest", pytest_argv(root, files, cfg), root, timeout_s, cfg, {"PYTHONSAFEPATH": "1"}, remote=True)


def whole_tests_rung(root, tests_dir: str, cfg: Config = Config(), timeout_s: float = 1800) -> dict:  # noqa: B008
    """One [check.whole_tests] dir run whole as ITS OWN pytest, the way its suite runs everywhere else: cwd = its package
    dir (the tests dir's parent), so a sibling `tests` package in another project never shadows its `from tests import x`."""
    package = str(Path(tests_dir).parent)
    cwd = Path(root) / package
    argv = pytest_argv(root, [str(Path(root) / tests_dir)], cfg, package=package)
    return _run("pytest", argv, root, timeout_s, cfg, {"PYTHONSAFEPATH": "1"}, cwd=cwd, remote=True)


def green_runs(tree, files: list[str], whole: tuple, cfg: Config, timeout_s: float) -> dict:
    """The green run: the engine-shaped pytest over the changed test files, then each whole-tests dir as its own pytest.
    One row: the first red (or the last green) as the row's own fields, `runs` = every command and its tail."""
    runs = []
    groups: dict[str, list[str]] = {}  # one pytest per top-level package: two `tests` dirs in one run shadow each other
    for f in files:
        groups.setdefault(Path(f).parts[0] if len(Path(f).parts) > 1 else "", []).append(f)
    for fs in groups.values():
        if runs and not runs[-1]["ok"]:
            break
        runs.append(pytest_rung(tree, fs, cfg, timeout_s))
    for d in whole:
        if runs and not runs[-1]["ok"]:
            break
        runs.append(whole_tests_rung(tree, d, cfg, timeout_s))
    row = next((r for r in runs if not r["ok"]), runs[-1])
    return {**row, "runs": [{k: r[k] for k in ("argv", "exit_code", "ok", "seconds", "stdout_tail", "stderr_tail")} for r in runs]}


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
    found = [s for s in sorted(root.glob(cfg.guard_glob)) if s.stem not in cfg.guard_skip]  # review-2 H10: skipped ones do not count
    if len(found) < cfg.min_guards:
        return {"ok": False, "reason": f"fewer than {cfg.min_guards} guards to run ({len(found)}): blind is not green",
                "results": []}
    results = []
    for s in found:
        r = _run(s.stem, _isolated(s, root, cfg), root, cfg.guard_timeout_s, cfg)
        r["argv"] = [str(s)]
        results.append(r)
    return {"ok": all(r["ok"] for r in results), "reason": "", "results": results}


def contract_current(root, changed: list[str], cfg: Config, timeout_s: float = 300) -> dict:
    """The project's contract guards, only when the diff touches its contract paths."""
    if not cfg.contract_guards or not any(f.startswith(cfg.contract_paths) for f in changed):
        return {"ok": True, "skipped": True, "results": []}
    root = Path(root)
    results = [_run(Path(g).stem, _isolated(root / g, root, cfg), root, timeout_s, cfg)
               for g in cfg.contract_guards]
    return {"ok": all(r["ok"] for r in results), "skipped": False, "results": results}


def since_guards(root, since: str, changed: list[str], cfg: Config, timeout_s: float = 300) -> dict:
    """Each `[check].since_guards` guard whose prefix the diff touches, run in the scratch tree with `--since <base>`: its
    question about this range only (#6318: the SwiftLint ratchet's `--since`, which the gate ran and the ladder did not)."""
    todo = [g for g, prefix in cfg.since_guards.items() if any(f.startswith(prefix) for f in changed)]
    if not todo:
        return {"ok": True, "skipped": True, "results": []}
    root = Path(root)
    results = [_run(Path(g).stem, [*_isolated(root / g, root, cfg), "--since", since], root, timeout_s, cfg) for g in todo]
    return {"ok": all(r["ok"] for r in results), "skipped": False, "results": results}


def build_names(root, since: str, head: str) -> list[str]:
    """Changed paths for the build rung: added, modified AND deleted (a deleted Swift file still referenced must fail the
    build, review 1 M7); the other rungs keep their added-or-modified list."""
    return [f for _s, _m, f in _changes(root, since, head, "--diff-filter=AMD")]


def build(root, changed: list[str], cfg: Config) -> dict:
    """The project's build-only compile, only when the diff touches its build paths; one at a time under the lock
    (owner 2026-11-01: a Swift change nobody compiled reached the land gate; builds stay serial on this machine)."""
    if not cfg.build or not any(f.startswith(cfg.build_paths) for f in changed):
        return {"ok": True, "skipped": True, "results": []}
    lock = None
    if cfg.build_lock:  # ~ = the owner's own state dir (review 1 N3); the owner's process takes it, the build itself runs jailed
        lp = Path(os.path.expanduser(cfg.build_lock))
        lp.parent.mkdir(parents=True, exist_ok=True)
        lock = open(lp, "a")
    try:
        if lock is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        r = _run("build", list(cfg.build), root, cfg.build_timeout_s, cfg)
    finally:
        if lock is not None:
            lock.close()
    return {"ok": r["ok"], "skipped": False, "results": [r]}


def _git_argv(root, args) -> list[str]:
    """git with hooks, fsmonitor, every filter driver and external diff the repo's own config names switched off
    (review 2 B2: a worker's .git/config must run no code at checkout or diff)."""
    r = subprocess.run(["git", "config", "--local", "--name-only", "--get-regexp", r"^filter\."], cwd=str(root),
                       capture_output=True, text=True, env=_git_env())
    names = {k.split(".")[1] for k in r.stdout.split() if k.count(".") >= 2}
    off = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "diff.external=",
           "-c", "core.attributesFile=/dev/null"]
    for n in sorted(names):
        off += ["-c", f"filter.{n}.smudge=", "-c", f"filter.{n}.clean=", "-c", f"filter.{n}.process=",
                "-c", f"filter.{n}.required=false"]
    return ["git", *off, *args]


def _git_env() -> dict:
    return {"PATH": os.environ.get("PATH", ""), "HOME": tempfile.gettempdir(), "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_ATTR_NOSYSTEM": "1"}


def _git(root, *args, timeout_s: float = 60) -> dict:
    return run_command("git", _git_argv(root, args), root, timeout_s, _git_env(), as_jail=False)  # the engine's own repo


def _lines(root, *args) -> list[str] | None:
    """git stdout, whole (the typed result's tail is capped); None on failure."""
    r = subprocess.run(_git_argv(root, args), cwd=str(root), capture_output=True, text=True, env=_git_env())
    return r.stdout.splitlines() if r.returncode == 0 else None


def _changes(root, since: str, head: str, *extra: str) -> list[tuple[str, str, str]]:
    """[(status, new mode, path)] of since...head, NUL-separated so no path is ever quoted or split (review 4 B6)."""
    r = subprocess.run(_git_argv(root, ["diff", "--raw", "-z", "--no-renames", "--no-abbrev", *extra, f"{since}...{head}"]),
                       cwd=str(root), capture_output=True, env=_git_env())
    if r.returncode:
        return []
    tok = r.stdout.decode("utf-8", "surrogateescape").split("\0")
    out = []
    for i in range(0, len(tok) - 1, 2):
        meta = tok[i].lstrip(":").split()
        if len(meta) >= 5:
            out.append((meta[4][0], meta[1], tok[i + 1]))
    return out


def diff_bound(root, since: str, head: str, cfg: Config, maintainer: bool = False) -> dict:
    """The diff since the item's start stays inside a size bound (files and added+removed lines). A maintainer batch is
    not bound (owner 2026-11-02: the bound is for a jailed worker's range; review splits a big batch by size); its row
    still shows the size. ponytail: a size bound only; a per-folder scope bound if workers wander."""
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
    if maintainer:
        return {**r, "name": "diff-bound", "ok": True, "stdout_tail": f"maintainer batch, not bound: {len(rows)} files, {lines} lines", "stderr_tail": ""}
    return {**r, "name": "diff-bound", "ok": not msg, "stderr_tail": msg}


def data_only(root, since: str, head: str, f: str) -> bool:
    """A test file on base whose test functions are all unchanged at head (only module-level data, such as a registration
    set, changed): it owes no red, since its tests are the ones already there (manager 2026-11-02, #6325's OWNER_ONLY_GETS)."""
    def defs(rev):
        t = "\n".join(_lines(root, "show", f"{rev}:{f}") or [])
        try:
            tree = ast.parse(t)
        except SyntaxError:
            return None
        # every top-level function and class (a class with its methods), not only test_*: a changed fixture or helper can hollow
        # a test out while the test functions look unchanged (review 2026-11-02); module-level data is what may differ
        return [ast.dump(n) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    old, new = defs(since), defs(head)
    return bool(old) and old == new


def red_on_base(root, since: str, head: str, files: list[str], cfg: Config = Config(), timeout_s: float = 600,  # noqa: B008
                head_tree=None, also_green: tuple = (), approve_red: bool = False) -> dict:
    """The failing run: each changed test file, copied onto a scratch tree at `since`, must FAIL there on its
    own, and all must PASS at `head`. A test that passes on base proves nothing."""
    root = Path(root)

    approved: list[str] = []

    def red(msg: str) -> dict | None:  # the manager's approve (an alert) records the refusal and goes on to the green run
        if approve_red:
            approved.append(msg)
            return None
        return {"name": "red-on-base", "argv": [], "exit_code": 1, "ok": False, "timed_out": False, "seconds": 0,
                "stdout_tail": "", "stderr_tail": msg + "\nneeds-approval"}
    if not files and (r := red("no test file changed: a source change needs a test (red on base, green on the branch)")):
        return r
    sha = _git(root, "rev-parse", head)["stdout_tail"].strip()  # `HEAD` inside the scratch tree would be `since`
    base = _mkdtemp("check-base-tree-", readable=True)
    try:
        if not _git(root, "worktree", "add", "--detach", "-q", base, since)["ok"]:
            return red(f"could not make a scratch tree at {since[:9]}")
        _git(base, "checkout", sha, "--", *files)  # a new file is not on base; checkout still copies it
        have = already_built_files(root, since, head, cfg)  # a proving test of a behaviour already there passes on base by design
        data_skipped: set[str] = set()
        for f in files:
            if f not in have and data_only(root, since, head, f):
                data_skipped.add(f)
                continue  # its tests are base's own; it runs in the green run
            r = pytest_rung(base, [f], cfg, timeout_s)
            if f in have and not r["ok"] and (x := red(f"{f} says Already built but fails on base at {since[:9]}: it owes a red like any test")):
                return x
            if f not in have and r["ok"] and (x := red(f"NOT RED ON BASE: {f} passes at {since[:9]}, so it proves nothing")):
                return x
        changed = _lines(root, "diff", "--name-only", f"{since}...{head}") or []
        source = [n for n in changed if not any(fnmatch.fnmatch(Path(n).name, g) for g in cfg.test_globs) and (not cfg.red_paths or n.startswith(cfg.red_paths))]
        if source and files and set(files) <= have | data_skipped and (x := red(
                f"{source[0]} changed and every changed test says Already built" + (" or changes only module data" if data_skipped else "")
                + ": the change owes a red")):
            return x  # a data-only edit to an existing test excuses no source change (review 2026-11-02)
        here = green_runs(head_tree or root, files, also_green, cfg, timeout_s) if files or also_green else _skipped("red-on-base")
        return {**here, "name": "red-on-base", **({"stdout_tail": "approved by the manager: " + "; ".join(approved) + "\n" + here.get("stdout_tail", "")} if approved else {})}
    finally:
        _git(root, "worktree", "remove", "--force", base)


ALREADY_BUILT = re.compile(r"^Already built:?\s*#\d+\s+(\S+?)::\w+", re.M | re.I)


def already_built_files(root, since: str, head: str, cfg: Config = Config()) -> set[str]:  # noqa: B008
    """Files touched ONLY by commits of since..head that prove a behaviour already in place: the message has an `Already
    built: #N <path>::<test>` line, the named file is in the commit, and the commit changes test files and nothing else. The
    worker writes the message, so a line on a commit that also changes source earns nothing. Any other commit's file owes its red."""
    have, other = set(), set()
    for sha in _lines(root, "rev-list", f"{since}..{head}") or []:
        msg = "\n".join(_lines(root, "log", "-n1", "--format=%B", sha) or [])
        touched = set(_lines(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha) or [])
        named = ALREADY_BUILT.findall(msg)
        test_only = all(any(fnmatch.fnmatch(Path(f).name, g) for g in cfg.test_globs) for f in touched)
        (have if named and test_only and set(named) <= touched else other).update(touched)
    return have - other


def _no_activity(**kw) -> None:
    return None


ACTIVITY = _no_activity  # `builder check` and the chain set this to a journal writer (console view A); tests write nowhere
_KEY: list = [""]  # the running ladder's key, for its rung rows


def ladder(rungs: list) -> dict:
    """Run (name, callable) rungs in order and stop at the first red, so the worker gets one failure at a time."""
    out = []
    for name, fn in rungs:
        ACTIVITY(kind="check", key=_KEY[0], state="rung-start", rung=name)
        r = {"name": name, **fn()}
        ACTIVITY(kind="check", key=_KEY[0], state="rung", rung=name, ok=bool(r.get("ok")), seconds=r.get("seconds"))
        out.append(r)
        if not r["ok"]:
            return {"ok": False, "failed": name, "rungs": out}
    return {"ok": True, "failed": "", "rungs": out}


BYPASS_NAMES = ("sitecustomize.py", "usercustomize.py")
# pinned by NAME anywhere, any status: pytest reads these from whatever directory it finds them in (review 4 B6)
PINNED_NAMES = ("conftest.py", "pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "pyproject.toml", "tox.ini",
                "setup.cfg", ".gitattributes", "ruff.toml", ".ruff.toml")  # every name pytest's findpaths reads (review 6)


def pinned_violations(root, since: str, head: str, cfg: Config, pinned) -> list[str]:
    """What the diff may not do: change or delete a pinned check file, add or touch a file pytest or Python would
    obey before or instead of the checks (sitecustomize, .pth, a pinned NAME anywhere, a pytest.py / _pytest shadow, a
    dist-info plugin), add any symlink, or touch .claude/. Adding a new guard is allowed. Paths come from `git diff -z`."""
    pinned_set = {f for f in (_lines(pinned, "ls-files") or []) if f.startswith(cfg.check_paths)}
    bad = []
    for status, mode, f in _changes(root, since, head):
        parts = Path(f).parts
        name = parts[-1]
        if f in pinned_set:
            bad.append(f"{f}: a pinned check file was {'deleted' if status == 'D' else 'changed'}")
        elif f.startswith(".claude/"):
            bad.append(f"{f}: .claude/ changed")
        elif status == "D":
            if name in PINNED_NAMES:
                bad.append(f"{f}: a pinned-name file was deleted")
        elif mode == "120000":
            bad.append(f"{f}: a symlink (the checks read through it)")
        elif name in PINNED_NAMES:
            bad.append(f"{f}: {name} is pinned by name anywhere (it changes what pytest does)")
        elif name in BYPASS_NAMES or name.endswith(".pth") or name == "pytest.py" or "_pytest" in parts or any(
                x.endswith((".dist-info", ".egg-info")) for x in parts):
            bad.append(f"{f}: would run before, instead of, or inside the checks")
        elif status == "A" and f.startswith(cfg.check_paths) and not (cfg.guard_glob and fnmatch.fnmatch(f, cfg.guard_glob)):
            bad.append(f"{f}: a new file under a pinned path (only a new guard may be added there)")
    return bad


SKIP_LINE = r"(?m)^\s*(?:@pytest\.mark\.(?:skip|skipif|xfail)\b|pytestmark\b.*\bpytest\.mark\.(?:skip|skipif|xfail)\b|pytest\.(?:skip|xfail)\()"


def weakened_tests(root, since: str, head: str, cfg: Config) -> list[str]:
    """Existing test files the diff weakens: a test function removed, fewer `assert`s, or more skip/xfail markers
    (conftest.py counts: it can skip everything). New test files are free. Ported from the frozen pipeline.
    ponytail: counts per file by regex; a renamed file is not compared; an AST diff if a worker games the counts."""
    base = (_lines(root, "merge-base", since, head) or [since])[0]

    def counts(rev, f):
        t = "\n".join(_lines(root, "show", f"{rev}:{f}") or [])
        return (set(re.findall(r"(?m)^\s*(?:async )?def (test_\w+)", t)), len(re.findall(r"\bassert\b", t)),
                len(re.findall(SKIP_LINE, t)))
    bad = []
    for _s, _m, f in _changes(root, since, head, "--diff-filter=MD"):
        if not (f.endswith(".py") and (f.endswith("conftest.py") or any(fnmatch.fnmatch(Path(f).name, g) for g in cfg.test_globs))):
            continue
        (t0, a0, s0), (t1, a1, s1) = counts(base, f), counts(head, f)
        if t0 - t1 or a1 < a0 or s1 > s0:
            bad.append(f)
    return bad


TAG_RE = re.compile(r"\[(?:OK|PARTIAL|MISSING|GAP|BROKEN|PROPOSED)[^\]]*\]|\(#\d+\)")


def _acceptance_lines(text: str, ids) -> list[str]:
    """The behaviour bullets (`- \\`area.id\\``, continuation lines included) that name one of `ids`, with status
    tags and `(#N)` removed, so flipping [PROPOSED] to [OK] or adding the issue number is not a change."""
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s*- `[a-z][a-z0-9-]*\.[a-z0-9.-]+`", line) and any(f"`{x}`" in line for x in ids):
            block = [line]
            for nxt in lines[i + 1:]:
                if not (nxt.startswith("  ") and not nxt.lstrip().startswith("- ")):
                    break
                block.append(nxt)
            out.append(" ".join(b.strip() for b in block))
    return [re.sub(r"\s+", " ", TAG_RE.sub("", s)).strip() for s in out]


def acceptance_changed(root, since: str, head: str, cfg: Config, ids) -> list[str]:
    """Lines of the item's own acceptance that differ between `since` and `head` in a changed spec file: a worker
    may not rewrite what it is judged on (it asks instead). A tag flip or an added (#N) is not a change.
    ponytail: stricter than the frozen pipeline (no [OK]-flip-with-prose rule); a flip that also edits prose asks."""
    if not cfg.spec_dir or not ids:
        return []
    hits = []
    for _s, _m, f in _changes(root, since, head, "--diff-filter=MD"):
        if not (f.startswith(cfg.spec_dir.rstrip("/") + "/") and f.endswith(".md")):
            continue
        before = _acceptance_lines("\n".join(_lines(root, "show", f"{since}:{f}") or []), ids)
        after = _acceptance_lines("\n".join(_lines(root, "show", f"{head}:{f}") or []), ids)
        if before != after:
            hits += [f"{f}: - {x[:160]}" for x in before if x not in after] + [f"{f}: + {x[:160]}" for x in after if x not in before]
    return hits


def _scratch_tree(root, head: str, pinned, cfg: Config) -> str:
    """A detached worktree of `head` with the pinned copy's check files laid over it: the checks judge the worker's
    committed code, never its uncommitted edits and never its own copies of the checks."""
    sha = (_lines(root, "rev-parse", head) or [""])[0]
    tree = _mkdtemp("check-tree-", readable=True)
    r = _git(root, "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach", "-q", tree, sha)  # no repo hook runs as the owner
    if not r["ok"]:
        raise RuntimeError(f"scratch tree failed: {r['stderr_tail']}")
    for f in _lines(pinned, "ls-files") or []:
        if f.startswith(cfg.check_paths):
            src, dest = Path(pinned) / f, Path(tree) / f
            if src.is_symlink():
                raise RuntimeError(f"pinned file {f} is a symlink: refused")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.parent.resolve().is_relative_to(Path(tree).resolve()):
                raise RuntimeError(f"{f} resolves outside the scratch tree: refused")
            dest.unlink(missing_ok=True)  # never write through a worker-committed symlink (review 4 H1)
            dest.write_bytes(src.read_bytes())
            dest.chmod(src.stat().st_mode)
    return tree


class EmptyRange(RuntimeError):
    """since equals head: a landing branch that never got its commit judged green on nothing (2026-11-02)."""


def ladder_over(root, since_sha: str, head: str, pinned, protected_ids=(), maintainer: bool = False, approve_weakened: bool = False,
                approve_red: bool = False, approve_pinned_new: bool = False) -> dict:
    """The one way `builder check` and `builder work` run the ladder: an empty range is refused, never judged."""
    if since_sha == head:
        raise EmptyRange(f"{since_sha[:9]}..{head[:9]} is empty: nothing to check")
    return run_ladder(root, since_sha, head, pinned, list(protected_ids), maintainer=maintainer, approve_weakened=approve_weakened, approve_red=approve_red,
                      approve_pinned_new=approve_pinned_new)


def run_ladder(root, since: str, head: str, pinned, protected_ids=(), jail_required: bool = True, maintainer: bool = False,
               approve_weakened: bool = False, approve_red: bool = False, approve_pinned_new: bool = False) -> dict:
    """The project's whole ladder over the diff since..head, judged by the PINNED copy (an engine-owned checkout
    outside the worker's tree; its harness.toml is the config): pinned-checks, ready, diff bound, red-on-base for
    the changed test files (its green run is the pytest rung), guards, contract. Stops at the first red.
    `protected_ids`: the behaviour ids of the item, whose spec acceptance the worker may not rewrite.
    `maintainer`: a maintainer batch changes pinned files on purpose; the pinned-checks row records which and the
    ladder runs on (weakened tests and a rewritten acceptance still refuse)."""
    global _JAIL
    from . import jail as _jailmod
    if jail_required and (problems := rules_problems(pinned)):  # review 4 B5: the start's own checks, here too
        raise _jailmod.JailMissing("rules file refused: " + "; ".join(problems))
    j = _jailmod.load(pinned)
    if j is None and jail_required:  # review 3 B5: no [jail] means refuse, never run as the owner
        raise _jailmod.JailMissing("no [jail] in the rules file: the ladder will not run as the owner")
    if j is not None:  # [jail] in the rules file = the ladder runs as that user, and refuses if it is not there
        j.require()
        if wall := j.probe():
            raise _jailmod.JailMissing("the jail leaks: " + "; ".join(wall))
    _JAIL = j
    _KEY[0] = f"check {since[:9]}..{str(head)[:9]}"
    ACTIVITY(kind="check", key=_KEY[0], state="start")
    ended: dict = {}
    try:
        ended = _run_ladder(root, since, head, pinned, protected_ids, maintainer, approve_weakened, approve_red, approve_pinned_new)
        return ended
    finally:
        ACTIVITY(kind="check", key=_KEY[0], state="end", ok=bool(ended.get("ok")), failed=ended.get("failed", "?"))
        _JAIL = None
        if _SHIPPED or _DOWN:
            _drop_remote(load(pinned))


def _needs_red(names: list[str], tests: list[str], cfg: Config) -> bool:
    """By path (spec): with red_paths set, only a diff touching them (or changing a test) owes a red-on-base run."""
    return not cfg.red_paths or bool(tests) or any(n.startswith(cfg.red_paths) for n in names)


def _whole_tests(names: list[str], cfg: Config) -> tuple:
    """Tests dirs the green run takes whole: a changed source can break an old test its own new test never imports."""
    return tuple(sorted({d for p, d in cfg.whole_tests.items() if any(n.startswith(p) for n in names)}))


def _no_red_row(tree, whole: tuple, cfg: Config) -> dict:
    """No red-on-base owed; a change under a whole_tests prefix (a deletion too) still runs those dirs whole."""
    if whole:
        return green_runs(tree, [], whole, cfg, 1800)
    return {**_skipped("red-on-base"), "stdout_tail": "not required: no changed path is under [check].red_paths"}


def _run_ladder(root, since: str, head: str, pinned, protected_ids=(), maintainer: bool = False, approve_weakened: bool = False,
                approve_red: bool = False, approve_pinned_new: bool = False) -> dict:
    cfg = load(pinned)
    bad = pinned_violations(root, since, head, cfg, pinned)
    noted = ""
    if maintainer:  # only "a pinned check file was changed/deleted" is noted; a symlink, sitecustomize/.pth, .claude/, a new pinned-path file still refuse
        changed = [b for b in bad if b.endswith((": a pinned check file was changed", ": a pinned check file was deleted"))]
        if changed:
            noted, bad = "maintainer batch: " + "; ".join(changed), [b for b in bad if b not in changed]
    if approve_pinned_new:  # the manager answered the alert with approve: a new file under a pinned path, recorded, not refused
        new = [b for b in bad if b.endswith(": a new file under a pinned path (only a new guard may be added there)")]
        if new:
            noted, bad = (noted + "; " if noted else "") + "approved new pinned files: " + "; ".join(new), [b for b in bad if b not in new]
    if weak := weakened_tests(root, since, head, cfg):
        if approve_weakened:  # the manager answered the alert with approve (an owner ruling renamed or dropped them): recorded, not refused
            noted = (noted + "; " if noted else "") + f"approved weakened tests: {', '.join(weak[:5])}"
        else:
            bad.append(f"the diff deletes or weakens existing tests ({', '.join(weak[:5])})")
    bad += [f"the diff rewrites the item's own acceptance ({h})" for h in acceptance_changed(root, since, head, cfg, protected_ids)[:8]]
    if bad:
        r = {"name": "pinned-checks", "argv": [], "exit_code": 1, "ok": False, "timed_out": False, "seconds": 0,
             "stdout_tail": "", "stderr_tail": "\n".join(bad) + "\nneeds-maintainer"}
        return {"ok": False, "failed": "pinned-checks", "rungs": [r]}
    names = [f for _s, _m, f in _changes(root, since, head, "--diff-filter=AM")]
    whole = _whole_tests([f for _s, _m, f in _changes(root, since, head)], cfg)  # a deletion under the prefix counts too
    tests = [f for f in names if any(fnmatch.fnmatch(Path(f).name, g) for g in cfg.test_globs)]
    if cfg.base_ref and not _git(root, "rev-parse", "--verify", "-q", f"refs/remotes/{cfg.base_ref}")["ok"]:
        _git(root, "update-ref", f"refs/remotes/{cfg.base_ref}", since)  # a remote-less clone: ready checks diff against it
    tree = _scratch_tree(root, head, pinned, cfg)
    try:
        ok_pin = {"name": "pinned-checks", "argv": [], "exit_code": 0, "ok": True, "timed_out": False, "seconds": 0,
                  "stdout_tail": (noted + "\n" if noted else "") + f"checks from the pinned copy over {head}", "stderr_tail": ""}
        out = ladder([
            ("ready", lambda: ready(tree, cfg)),
            ("diff-bound", lambda: diff_bound(root, since, head, cfg, maintainer)),
            ("red-on-base", lambda: red_on_base(root, since, head, tests, cfg, head_tree=tree, also_green=whole, approve_red=approve_red) if _needs_red(names, tests, cfg)
             else _no_red_row(tree, whole, cfg)),
            ("guards", lambda: guards(tree, cfg)),
            ("contract-current", lambda: contract_current(tree, names, cfg)),
            ("since-guards", lambda: since_guards(tree, since, names, cfg)),
            ("build", lambda: build(tree, build_names(root, since, head), cfg)),
        ])
    finally:
        _git(root, "worktree", "remove", "--force", tree)
    return {**out, "rungs": [ok_pin, *out["rungs"]]}
