"""The check tool: plain argv commands, each with a cwd and a timeout, typed results.

(dev-workflows.tool.check, #6116.) No shell, no route yet. Rungs ported from the frozen pipeline/checks.py:
`ready`, `pytest_rung`, `guards`, `contract_current`. A red or missing program is a result, never a raise.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MIN_GUARDS = 20
GUARD_TIMEOUT_S = 60

# Guards the nightly gate runs instead, each with its reason in pipeline/projects/fichero.toml [ladder.skip].
DEFAULT_SKIP = frozenset({
    "check_closed_issues_landed", "check_unmerged_work", "check_merged_worktrees", "check_no_orphan_stashes",
    "check_coverage_ratchet", "check_embedded_engine_signing", "check_hang_ratchet", "check_mac_app_store_target",
    "check_release_staples_app", "check_sparkle_update_ready", "check_swiftlint_warning_ratchet",
    "check_test_plans_runnable", "check_engine_imports_bundled", "check_release_size_ratchet", "check_docs_paths",
})

CONTRACT_GUARDS = ("check_openapi_route_set_current", "check_contract_identity_current", "check_mcp_generated_current")


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


def _env(root, extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TERM", "LANG")}
    root = Path(root)
    env["PYTHONPATH"] = ":".join(str(root / p) for p in ("fichero-server/src", "fichero-cli/src", "fichero-mcp/src"))
    env.update(extra or {})
    return env


def ready(root, timeout_s: float = 600) -> dict:
    return run_command("ready", [str(Path(root) / "scripts/lane_ready_check.sh"), "HEAD"], root, timeout_s)


def pytest_rung(root, files: list[str], timeout_s: float = 1800) -> dict:
    """Named test files only; a fresh base path so the run never opens a real library."""
    if not files:
        return run_command("pytest", [sys.executable, "-c", "import sys; sys.exit('no test files named')"], root, 5)
    env = _env(root, {"FICHERO_FEATURE_TIER": "dev", "OMP_NUM_THREADS": "2",
                      "FICHERO_BASE_PATH": tempfile.mkdtemp(prefix="check-base-")})
    return run_command("pytest", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", *files],
                       root, timeout_s, env)


def _isolated(script: Path, root: Path) -> list[str]:
    """`python -I` so a planted sitecustomize/.pth is never imported; the tree's paths go in after site."""
    paths = [str(script.parent), *[str(root / p) for p in ("fichero-server/src", "fichero-cli/src", "fichero-mcp/src")]]
    code = ("import sys, runpy; i = next((n for n, p in enumerate(sys.path) if 'site-packages' in p), len(sys.path)); "
            f"sys.path[i:i] = {paths!r}; runpy.run_path({str(script)!r}, run_name='__main__')")
    return [sys.executable, "-I", "-c", code]


def guards(root, skip=DEFAULT_SKIP, timeout_s: float = GUARD_TIMEOUT_S) -> dict:
    """Every scripts/check_*.py not in `skip`. Fewer than 20 found = blind = not green."""
    root = Path(root)
    found = sorted((root / "scripts").glob("check_*.py"))
    if len(found) < MIN_GUARDS:
        return {"ok": False, "reason": f"fewer than {MIN_GUARDS} guards found ({len(found)}): blind is not green", "results": []}
    results = []
    for s in found:
        if s.stem in skip:
            continue
        r = run_command(s.stem, _isolated(s, root), root, timeout_s, _env(root))
        r["argv"] = [str(s)]
        results.append(r)
    return {"ok": all(r["ok"] for r in results), "reason": "", "results": results}


def contract_current(root, changed: list[str], timeout_s: float = 300) -> dict:
    """The three contract guards, only when the diff touches the engine source."""
    if not any(f.startswith("fichero-server/src/") for f in changed):
        return {"ok": True, "skipped": True, "results": []}
    root = Path(root)
    results = [run_command(g, _isolated(root / "scripts" / f"{g}.py", root), root, timeout_s, _env(root)) for g in CONTRACT_GUARDS]
    return {"ok": all(r["ok"] for r in results), "skipped": False, "results": results}


def _git(root, *args, timeout_s: float = 60) -> dict:
    # hooks and fsmonitor off, as the frozen pipeline ran every git
    return run_command("git", ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args], root, timeout_s)


def diff_bound(root, since: str, head: str = "HEAD", max_files: int = 25, max_lines: int = 1500) -> dict:
    """The diff since the item's start stays inside a size bound (files and added+removed lines).
    ponytail: a size bound only; a per-folder scope bound if workers wander."""
    r = _git(root, "diff", "--numstat", f"{since}...{head}")
    if not r["ok"]:
        return {**r, "name": "diff-bound"}
    rows = [ln.split("\t") for ln in r["stdout_tail"].splitlines() if ln.count("\t") == 2]
    lines = sum(int(a) + int(d) for a, d, _ in rows if a.isdigit() and d.isdigit())
    msg = ""
    if len(rows) > max_files:
        msg = f"diff bound: {len(rows)} files, over {max_files}"
    elif lines > max_lines:
        msg = f"diff bound: {lines} lines, over {max_lines}"
    return {**r, "name": "diff-bound", "ok": not msg, "stderr_tail": msg}


def red_on_base(root, since: str, head: str, files: list[str], timeout_s: float = 600) -> dict:
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
            r = pytest_rung(base, [f], timeout_s)
            if r["ok"]:
                return red(f"NOT RED ON BASE: {f} passes at {since[:9]}, so it proves nothing")
        here = pytest_rung(root, files, timeout_s)
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
