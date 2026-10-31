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
