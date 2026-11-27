"""The check tool: plain argv commands, each with a cwd and a timeout, typed results.

(dev-workflows.tool.check, #6116.) No shell, no route yet. Nothing here names a project: what to run comes from the
project's `harness.toml` `[check]` table (`load`), Fichero being the first project. Rungs: `ready`, `pytest_rung`,
`guards`, `contract_current`, `diff_bound`, `red_on_base`, composed by `run_ladder`. A red or missing program is a
result, never a raise.
"""

from __future__ import annotations

import ast
import contextlib
from concurrent.futures import ThreadPoolExecutor
import difflib
import fcntl
import fnmatch
import functools
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from fichero_builder import actions, client, journal


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
    since_guards: dict = field(default_factory=dict)  # {guard path: path prefix, or a list of prefixes}: a diff under the prefix runs the guard with `--since <base>`
    spec_dir: str = ""                  # folder of the specs whose item acceptance a worker may not rewrite ("" = none)
    check_paths: tuple = ()             # files/folders that judge a diff: run from the pinned copy, never the worker's
    red_paths: tuple = ()               # a diff touching these (prefixes) needs a failing-on-base test; () = any file
    whole_tests: dict = field(default_factory=dict)  # {path prefix: tests dir | [dirs or test files]}: a diff under the prefix runs them in the green run
    test_globs: tuple = ("test_*.py", "*_test.py")
    auto: tuple = ()                    # rule classes the ladder decides by itself, each named here (AUTO_RULES) and journalled as an `auto` row
    pytest_config: str = ""             # the pinned pytest config file (relative to the tree), passed as `-c`; "" = pytest's own search
    pytest_plugins: tuple = ()          # plugins loaded by -p; autoload is OFF, so a dist-info entry point in the tree loads nothing
    max_files: int = 25
    max_lines: int = 1500
    max_commits: int = 100  # lane_ready_check.sh reads it from harness.toml: a hard-coded 60 had to be raised by hand in the pinned copy (2026-11-03)
    build_paths: tuple = ()             # a diff touching these (prefixes) runs the build rung; () = no build rung
    product_paths: tuple = ()           # a landed batch touching these (prefixes) earns the post-landing dev build; () = every landing builds
    build: tuple = ()                   # argv of a build-only compile (never a test run), run in the scratch tree
    build_timeout_s: float = 1800
    build_lock: str = ""                # a lock file: one build at a time on the machine ("" = no lock)
    build_tree: str = ""                # a STABLE worktree path the build runs in, so xcodebuild is incremental ("" = the scratch tree)
    daily_tests: tuple = ()  # test files run once a day on the loop's checkout (every tree-scanning guardrail test, 2026-11-08)
    daily_builds: dict = field(default_factory=dict)  # {name: xcodebuild argv}: once a day on build_remote, never here (#6390)
    build_remote: str = ""              # "host:dir": the build rung runs on that Mac (its own derived data under dir), off the owner's;
                                        # unreachable = the build here, as before ("" = here)
    routes_file: str = ""               # an OpenAPI JSON at head whose paths are the engine's routes (the guard-data-added-routes rule)
    generated: tuple = ()               # generated files a rebase may re-bake itself (the contract identity): never hand-merged
    rebake: tuple = ()                  # argv run in the worktree to re-bake them from the merged sources ("{python}" = [check].python)
    rebake_issue: str = ""              # the issue a re-bake commit cites, e.g. "#4705"
    autofix: tuple = ()                 # rule classes the loop applies itself to a managed lane's red (autofix.CLASSES), each one `autofix` row
    regen: tuple = ()                   # shell lines that regenerate every generated file (contracts, embed list), run after each rebase
                                        # that moved the lane and committed when they changed a tracked file ("{python}" = [check].python)
    remote: str = ""                    # "host:dir": the engine pytest runs go over ssh to that machine ("" = here); unreachable = an alert, then the next in `remotes`, then here
    remotes: tuple = ()                 # [check].remote as a LIST ("imac:~/g", "air:~/g"): tried in order; one alert per runner that is down
    remote_python: str = ""             # the interpreter there ("" = <dir>/venv/bin/python)
    guard_inputs: dict = field(default_factory=dict)  # {guard stem: [path prefixes it reads]}: its cache key (speed 5); undeclared = the whole tree
    remote_guards: bool | str = False   # the guards too (they call git, and the shipped tree has no .git: off by default); "auto": a guard
                                        # that names git, subprocess, swiftlint or xcodebuild stays here, the rest go to the runners
    guards_by_diff: bool = False        # a lane's guards rung skips a guard whose [check.guard_inputs] the batch does not touch: the nightly
                                        # runs every guard (2026-11-26, owner: per step only what changed); off = every guard, as before
    remote_min_free_gb: float = 5       # less free on the remote = unreachable (an alert, the run here)
    parallel: int = 2                   # ladders at once (speed 3), never two whose batches share a file; 1 = one at a time
    reuse_fix_verdicts: bool = False    # local.check.fix-round-reuses-verdicts: a fix commit keeps the green rungs it cannot change; off = every rung runs
    slots_from_runners: bool = False    # local.flow.check-slots-from-runners: count the ladder slots each tick from the runners' rows, `parallel` a ceiling; off = `parallel`
    slots_per_runner: int = 1           # the slots one [check].remote entry gives while it is fit
    runner_max_load: float = 1.0        # 1-minute load per core above this: the runner gives no slot
    runner_min_free_ram_gb: float = 4   # less free memory than this: the runner gives no slot
    perf: dict = field(default_factory=dict)      # [check.perf] (#6600): the engine perf rung: enforce, tests, timeout_s, dirs, declared
    security: dict = field(default_factory=dict)  # [check.security] (#6600): the security rung: enforce, where, pins, timeout_s, dirs
    always_tests: tuple = ()            # test files the unit rung always runs (contract tests, smoke set); () = no unit rung (speed-tests-1)
    ui_tests: tuple = ()                # -only-testing ids of the segment editor's UI tests; () = no ui rung
    ui_runner: str = ""                 # "host:dir" with a logged-in GUI session; "" = build_remote
    ui: dict = field(default_factory=dict)  # [check.ui]: enforce (report-only until three green runs)
    swift_test_target: str = ""         # the Swift unit-test target ("" = the train runs the whole suite): with it, `swift_affected` picks
    swift_test_dir: str = ""            # the suites under this dir the train's Swift diff can affect, as -only-testing:<target>/<suite>
    swift_tests: tuple = ()             # the build tool's argv up to the action (project, scheme, destination, -testPlan fichero): `swift_tests()` appends build-for-testing, then test-without-building
    rungs: tuple = ()                   # [check].rungs: the rungs to run, in this order, by name (RUNGS and the [[check.rung]] names); () = every RUNGS rung
    rung: tuple = ()                    # [[check.rung]]: {name, argv, timeout_s}: a rung that runs argv in the scratch tree, green on exit 0
    actions: tuple = ()                 # [check].actions: rungs a GitHub Actions run of the batch head may supply (only "unit"); () = all on the Macs
    actions_timeout_s: float = 1500     # how long to wait for that run before the rung runs on the Macs
    engine_repo: str = ""               # the engine-owned repository check and land judge from: outside every home dir, readable by the jailed user ("" = the caller names one)


def newer_code_knows(root, keys: list[str]) -> str:
    """The cause, when the builder package that came with these rules declares every unknown [check] key as a Config field
    (2026-11-25 16:42, alerts 1902-1909: a landing added `[check].swift_tests`, the loop re-pinned the new rules, and its older
    code refused every check for 80 minutes as "unknown keys"): '' when it does not, or there is no such package."""
    f = Path(root) / client.package_dir(root) / "check_tool.py"
    try:
        text = f.read_text() if f.resolve() != Path(__file__).resolve() else ""
    except OSError:
        return ""
    if not text or not all(re.search(rf"^    {re.escape(k)}\s*:", text, re.M) for k in keys):
        return ""
    return (f": a NEWER builder knows them (the package beside these rules, {f.parent}, declares them), so this process runs older "
            "code than its pinned rules; update the loop's checkout to the landed commit and it re-execs")


def load(root) -> Config:
    """`<root>/harness.toml` [check]; no file = the default Config."""
    f = Path(root) / "harness.toml"
    if not f.is_file():
        return Config()
    doc = tomllib.loads(f.read_text())
    c = doc.get("check", {})
    if unknown := sorted(set(c) - {x.name for x in fields(Config)} - {"test_env"}):  # fail closed (review 3, spec item 2)
        raise ValueError(f"harness.toml [check]: unknown keys {unknown}" + newer_code_knows(root, unknown))
    if unknown := sorted(set(doc) - KNOWN_TABLES):
        # forward compatible (manager 2026-11-02: a [machines] table stopped the running loop): the loop and the rules file can
        # differ by a batch, so a NEW table is ignored here and named once by `rules_warnings`; a table that is a near-miss of
        # a known one is a misspelling and still refuses, as an unknown key in [check] does
        if misspelt := [u for u in unknown if difflib.get_close_matches(u, KNOWN_TABLES, 1, 0.75)]:
            raise ValueError(f"harness.toml: unknown tables {misspelt}")
    brief = doc.get("brief", {})
    if unknown := sorted(set(brief) - {"rules", "template"}):
        raise ValueError(f"harness.toml [brief]: unknown keys {unknown}")
    if not isinstance(brief.get("rules", ""), str):
        raise ValueError("harness.toml [brief]: rules must be text")
    if c.get("regen") and not c.get("python"):  # review: a regen line must never run whatever python3 is on the PATH
        raise ValueError("harness.toml [check]: regen needs [check].python (the interpreter `{python}` names)")
    from fichero_builder import autofix
    if bad := [x for x in c.get("autofix", ()) if x not in autofix.CLASSES]:
        raise ValueError(f"harness.toml [check]: unknown autofix classes {bad}; known: {list(autofix.CLASSES)}")
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
        max_lines=c.get("max_lines", d.max_lines), max_commits=c.get("max_commits", d.max_commits), build_paths=tuple(c.get("build_paths", d.build_paths)), product_paths=tuple(c.get("product_paths", d.product_paths)),
        build=tuple(c.get("build", d.build)), build_timeout_s=c.get("build_timeout_s", d.build_timeout_s),
        build_lock=c.get("build_lock", d.build_lock), build_tree=c.get("build_tree", d.build_tree), build_remote=c.get("build_remote", d.build_remote), daily_builds={k: tuple(v) for k, v in c.get("daily_builds", {}).items()}, daily_tests=tuple(c.get("daily_tests", ())), routes_file=c.get("routes_file", d.routes_file), generated=tuple(c.get("generated", d.generated)), rebake=tuple(c.get("rebake", d.rebake)), rebake_issue=c.get("rebake_issue", d.rebake_issue), regen=tuple(c.get("regen", d.regen)), autofix=tuple(c.get("autofix", d.autofix)), engine_repo=c.get("engine_repo", d.engine_repo), actions=tuple(c.get("actions", d.actions)), actions_timeout_s=float(c.get("actions_timeout_s", d.actions_timeout_s)), perf=dict(c.get("perf", {})), security=dict(c.get("security", {})),
        always_tests=tuple(c.get("always_tests", ())), ui_tests=tuple(c.get("ui_tests", ())), ui_runner=c.get("ui_runner", d.ui_runner), ui=dict(c.get("ui", {})), swift_tests=tuple(c.get("swift_tests", ())), swift_test_target=c.get("swift_test_target", d.swift_test_target), swift_test_dir=c.get("swift_test_dir", d.swift_test_dir),
        remote=(c["remote"][0] if c["remote"] else "") if isinstance(c.get("remote"), list) else c.get("remote", d.remote),
        remotes=tuple(c["remote"]) if isinstance(c.get("remote"), list) else d.remotes, remote_python=c.get("remote_python", d.remote_python),
        remote_guards=c.get("remote_guards", d.remote_guards), guard_inputs=dict(c.get("guard_inputs", {})), guards_by_diff=bool(c.get("guards_by_diff", d.guards_by_diff)), remote_min_free_gb=c.get("remote_min_free_gb", d.remote_min_free_gb),
        rungs=tuple(c.get("rungs", d.rungs)), rung=tuple(dict(x) for x in c.get("rung", d.rung)),
        parallel=max(1, int(c.get("parallel", d.parallel))), auto=_auto_rules(c.get("auto", ())),
        reuse_fix_verdicts=bool(c.get("reuse_fix_verdicts", d.reuse_fix_verdicts)), slots_from_runners=bool(c.get("slots_from_runners", d.slots_from_runners)), slots_per_runner=int(c.get("slots_per_runner", d.slots_per_runner)),
        runner_max_load=float(c.get("runner_max_load", d.runner_max_load)), runner_min_free_ram_gb=float(c.get("runner_min_free_ram_gb", d.runner_min_free_ram_gb)))


# speed batch 1 (manager 2026-11-03): narrow rule classes the ladder resolves without a person, each opted in by name in
# [check].auto and journalled with that name, so the manager audits instead of approving
AUTO_RULES = {
    "red-on-base-pure-move": "a changed test file that is a pure rename (R100, content unchanged) of a file on base owes no red on base: its old copy already runs there; it still runs green on head, and a move with any edit keeps the red owed (manager 2026-11-25)",
    "red-on-base-timeout-only": "a changed test file whose diff touches ONLY timeout numbers (`timeout...=N`, `pytest.mark.timeout(N)`), "
                                "whole `pytest.mark.timeout` lines or comments owes no red on base: a time bound proves nothing there; any "
                                "other changed line keeps the red owed (manager 2026-11-05)",
    "red-on-base-tests-only": "a batch whose every changed path (a deletion or rename too) is a test file, a file in a tests directory or a "
                              "Markdown file, and none is under [check].red_paths, owes no red on base: there is no source change for a red to "
                              "prove, and every changed test still runs green on head; code outside red_paths is source, "
                              "and with red_paths unset the rule never applies",
    "red-on-base-trim-only": "a changed test file whose diff adds no assert and no new test function (a renamed one is a rename) "
                             "owes no red on base: it can only have lost checks, and it still runs green on head",
    "weakened-tests-of-a-deleted-module": "a changed test file whose head is its base with whole top-level tests removed, each of which "
                                          "called a module this diff deletes (`m.<attr>`, m imported), or a deleted test file whose every "
                                          "test called one, is not refused; anything else is",
    "approval-carry-same-file-diffs": "an approve (red-on-base, weakened tests, guard data) carries to the step's new head when each file it "
                                      "named has the same diff from its base (patch-id) at both heads: commits only added elsewhere, or a rebase "
                                      "whose range-diff of those files is empty; any other approval kind never carries",
    "allowlist-entries-only-removed": "a pinned guard's allowlist (a top-level literal named KNOWN/ALLOW/BASELINE/EXEMPT/DEBT, or a "
                                      "known-gaps/allowlist JSON) that only lost entries, every other statement identical, makes the guard "
                                      "stricter: not a pinned-file refusal, and the ladder judges with head's copy of that file (2026-11-14)",
    "guard-data-added-routes": "a guard-data stop on a *_known_gaps.json keyed by routes resolves itself when the batch only ADDS entries "
                               "(no key removed, no existing text changed), each added key is a route in [check].routes_file at head, and "
                               "each added reason names an issue (#N) or a step",
}


def _auto_rules(names) -> tuple:
    if unknown := sorted(set(names) - set(AUTO_RULES)):
        raise ValueError(f"harness.toml [check].auto: unknown rules {unknown} (known: {sorted(AUTO_RULES)})")
    return tuple(names)


KNOWN_TABLES = {"check", "jail", "policy", "land", "brief", "spend", "models", "triage", "queue", "loop", "machines", "perf", "harness", "nightly", "train", "flow", "review", "ci"}


def live_vs_pinned(root, base: str) -> list[str]:
    """local.rules.which-file: the loop reads [loop], [queue], [train], [nightly], [models] and [land] from its own checkout's
    harness.toml, but every ladder and train rung reads [check] from the pinned copy of the land branch's commit. Each [check] key
    whose live value differs from the pinned one at `base` (a hand edit the rungs never see), as one line; [] = none or no pinned copy.
    2026-11-26: swift_test_target was set live and every train still ran the whole Swift suite."""
    try:
        live = tomllib.loads((Path(root) / "harness.toml").read_text())
        pinned = Path(live["land"]["pinned_dir"]) / f"pinned-{base[:7]}" / "harness.toml"
        ours, theirs = live.get("check", {}), tomllib.loads(pinned.read_text()).get("check", {})
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [f"[check].{k} differs from the pinned {pinned.parent.name}: live {json.dumps(ours.get(k))[:120]}, pinned {json.dumps(theirs.get(k))[:120]}"
            " (the rungs read the pinned one: commit the change)" for k in sorted(set(ours) | set(theirs)) if ours.get(k) != theirs.get(k)]


def pinned_root(root) -> Path:
    """The pinned copy of the land branch's commit that the rungs read [check] from (local.rules.which-file); `root` when there is none."""
    from . import land_tool
    try:
        live = tomllib.loads((Path(root) / "harness.toml").read_text())
        base = land_tool.resolve_branch(live["check"]["engine_repo"], live["land"]["branch"])
        p = Path(live["land"]["pinned_dir"]) / f"pinned-{base[:7]}"
        return p if (p / "harness.toml").is_file() else Path(root)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        return Path(root)


def rules_warnings(root) -> list[str]:
    """What this code ignores in the rules file: tables newer than it (a warning, never a refusal)."""
    f = Path(root) / "harness.toml"
    doc = tomllib.loads(f.read_text()) if f.is_file() else {}
    new = sorted(u for u in set(doc) - KNOWN_TABLES if not difflib.get_close_matches(u, KNOWN_TABLES, 1, 0.75))
    return [f"harness.toml: unknown tables {new} (newer than this code?)"] if new else []


EMPTY_OK = ("ready", "contract_guards", "check_paths", "contract_paths", "pytest_config")  # may be declared empty (builder.client.empty-rungs)


def not_configured(name: str, why: str) -> dict:
    """A rung a declared-empty key turns off: NOT RUN with the reason, never a green and never a crash (builder.client.empty-rungs)."""
    return {"name": name, "argv": [], "exit_code": 0, "ok": True, "timed_out": False, "seconds": 0, "skipped": True, "not_run": True,
            "stdout_tail": f"NOT RUN: {why}", "stderr_tail": "", "results": []}


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
    if j is None:  # an ABSENT [jail] refuses; only `[jail].enabled = false` runs unjailed (builder.client.jail-optional)
        out.append("harness.toml has no [jail]: nothing runs unjailed (set [jail].enabled = false to run as yourself)")
    elif not j.enabled:  # unjailed on purpose: no user, no deny_read, no probe; each run journals an `unjailed` row
        if not j.workroot:
            out.append("[jail].workroot is not set: unjailed runs still keep their worktrees, scratch and state there")
    elif not j.user:
        out.append("[jail].user is not set")
    elif not j.deny_read:
        out.append("[jail].deny_read is empty: the probe needs paths to prove unreadable")
    declared = tomllib.loads(f.read_text()).get("check", {})
    for name, val in (("python", c.python), ("ready", c.ready), ("guard_glob", c.guard_glob), ("min_guards", c.min_guards),
                      ("contract_guards", c.contract_guards), ("check_paths", c.check_paths), ("contract_paths", c.contract_paths),
                      ("pytest_config", c.pytest_config)):  # review-2 H10: an unlisted key must not fail open
        # builder.client.empty-rungs: these may be declared EMPTY (`ready = []`): the rung that needs one is then a NOT RUN row
        # naming why; left out of the file they still refuse
        if not val and not (name in EMPTY_OK and name in declared):
            out.append(f"harness.toml [check].{name} is not declared")
    if c.python and not Path(c.python).is_absolute():
        out.append(f"[check].python {c.python!r} must be an absolute path (no PATH lookup, no shim)")
    if c.engine_repo and not (Path(c.engine_repo) / ".git").exists():  # first real check 2026-11-01: a tree under ~ is unreadable to the jailed user
        out.append(f"[check].engine_repo {c.engine_repo!r} is not a git repository (clone the owner's repo there, readable by the jailed user)")
    land = tomllib.loads(f.read_text()).get("land", {})
    if unknown := sorted(set(land) - {"branch", "boundary", "pinned_dir", "worktree_grace_hours", "repo", "release_branch"}):
        out.append(f"harness.toml [land]: unknown keys {unknown}")
    if not land.get("branch"):
        out.append("harness.toml [land].branch is not declared")
    try:  # local.ci.caps-and-fallback: hosted CI with no Xcode Cloud cap, or `required` before report rows earned it
        from . import ci as _ci
        cic = _ci.load(tomllib.loads(f.read_text()))
        out += _ci.problems(cic, journal.read() if cic.train == "required" and journal.path().exists() else [])  # the journal only when it decides
    except ValueError as e:
        out.append(str(e))
    if "boundary" in land and not land["boundary"]:  # left out = today's patterns (land_tool.DEFAULT_BOUNDARY); declared empty = no boundary, refused
        out.append("harness.toml [land].boundary is empty: leave it out for the default patterns, never turn the boundary off")
    return out


SECURITY_RESULT_PREFIX = "SECURITY-RESULT "
PERF_RESULT_PREFIX = "PERF-RESULT "
SECURITY_RESULT_MAX = 16384  # a final SECURITY-RESULT line longer than this is cut like any other line
FAILURES = re.compile(r"^=+ (?:FAILURES|ERRORS) =+$")
ERRLINE = re.compile(r"^(?:Traceback \(most recent|E\s{2,}\S|\w*(?:Error|Exception)\b.*:)")


def tail(text: str, lines: int = 40, chars: int = 4000, line_chars: int = 300) -> str:
    """The last lines, bounded. A `PERF-RESULT {json}` line is kept whole under the same rule (#6600: a first run lists every figure,
    the line passed 300 characters, lost its closing brace and the rung read no result). A `SECURITY-RESULT {json}` line that is the output's final line is never cut to `line_chars`
    (#6589 item 15: a 326-byte line lost its closing brace and the rung read it as absent): it is the scan's one machine-read
    line. Only that one final line is kept so, once, and only up to SECURITY_RESULT_MAX; any rung can print such lines, so
    earlier ones and longer ones get the normal cut."""
    stripped = (text or "").strip().splitlines()
    if stripped and stripped[-1].startswith((SECURITY_RESULT_PREFIX, PERF_RESULT_PREFIX)) and len(stripped[-1]) <= SECURITY_RESULT_MAX:
        head = _tail_lines("\n".join(stripped[:-1]), max(lines - 1, 1), chars, line_chars)
        return (head + "\n" if head else "") + stripped[-1]
    return _tail_lines(text, lines, chars, line_chars)


def _tail_lines(text: str, lines: int, chars: int, line_chars: int) -> str:
    """The bounded cut of `tail`: a pytest failure section is kept whatever follows it: its end (the `E` lines) plus the run's
    end, half the bound each; 40 lines of warnings once pushed the failure out of a red rung."""
    all_lines = [ln[:line_chars] for ln in (text or "").strip().splitlines()]
    start = next((i for i, ln in enumerate(all_lines) if FAILURES.match(ln)), None)
    last = all_lines[-lines:]
    if start is None and len(all_lines) > lines:  # no pytest failure section: keep the first exception lines the window drops (2026-11-02: an importlib stat error vanished)
        first = [ln for ln in all_lines[:-lines] if ERRLINE.match(ln)][:8]
        if first:
            return ("\n".join(first) + "\n...\n" + "\n".join(last[-(lines - len(first) - 1):]))[-chars:]
    if start is None or start >= len(all_lines) - lines:
        return "\n".join(last)[-chars:]
    stop = next((i for i in range(start + 1, len(all_lines)) if all_lines[i].startswith("=")), len(all_lines))
    failure = "\n".join(all_lines[start:stop][-(lines // 2):])[-(chars // 2):]
    return failure + "\n...\n" + "\n".join(all_lines[-(lines // 2 - 1):])[-(chars // 2):]


_JAIL = None  # module state set by run_ladder for the length of one ladder
_JAIL_USERS = [0]  # ladders using _JAIL now: two run at once (speed 3), and the first to end must not unjail the other
_JAIL_LOCK = threading.Lock()


def _jail_enter(j) -> None:
    global _JAIL
    with _JAIL_LOCK:
        _JAIL_USERS[0] += 1
        if j is not None:  # a ladder with no jail must not clear the neighbour's: it runs under the jail already in force (the safe side)
            _JAIL = j


def _jail_exit() -> None:
    global _JAIL
    with _JAIL_LOCK:
        _JAIL_USERS[0] -= 1
        if _JAIL_USERS[0] <= 0:
            _JAIL_USERS[0], _JAIL = 0, None


def _mkdtemp(prefix: str, readable: bool = False) -> str:
    if _JAIL is not None:
        d = _JAIL.mkdtemp(prefix)  # under the shared workroot, writable by the jailed user
    else:
        d = tempfile.mkdtemp(prefix=prefix)
    if readable:
        os.chmod(d, 0o755)  # a tree the jailed user reads (public repo content only)
    return d


def run_command(name: str, argv: list[str], cwd, timeout_s: float, env: dict | None = None, as_jail: bool = True, log=None) -> dict:
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
        deadline = time.time() + timeout_s
        while True:
            try:
                out, err = p.communicate(timeout=max(0.1, min(2.0, deadline - time.time())))
                code = p.returncode
                break
            except subprocess.TimeoutExpired:
                cancelled = cancel_requested()  # a `builder done` at a newer head wrote cancel-<head> (the loop is another process)
                if not cancelled and time.time() < deadline:
                    continue
                timed_out = not cancelled
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                out, err = p.communicate()
                if cancelled:
                    err = "cancelled: superseded by a newer head\n" + (err or "")
                break
    res = {"name": name, "argv": list(argv), "exit_code": code, "ok": code == 0 and not timed_out,
           "timed_out": timed_out, "seconds": round(time.time() - t, 1),
           "stdout_tail": tail(out), "stderr_tail": tail(err)}
    if log and not res["ok"]:  # a red one: every `error:` line in the row and the whole output on disk (a 3 KB tail lost xcodebuild's errors, manager 2026-11-03)
        res["errors"] = error_lines(f"{out or ''}\n{err or ''}")
        try:
            Path(log).parent.mkdir(parents=True, exist_ok=True)
            Path(log).write_text(f"$ {' '.join(map(str, argv))}\n{out or ''}\n--- stderr ---\n{err or ''}")
            res["log"] = str(log)
        except OSError as e:  # the rung's result stands; only the file is missing
            res["log"] = f"not written: {e}"
    return res


ERROR_LINE = re.compile(r"\berror:|\*\* BUILD FAILED \*\*|Killed: 9|Terminated|Segmentation fault|out of memory", re.I)


def error_lines(text: str, cap: int = 60) -> str:
    """Each distinct line naming an error (`path:line:col: error: ...`, BUILD FAILED, a kill or an OOM), in order, up to `cap`."""
    seen, out = set(), []
    for ln in text.splitlines():
        ln = ln.strip()[:400]
        if ERROR_LINE.search(ln) and ln not in seen:
            seen.add(ln), out.append(ln)
    return "\n".join(out[:cap]) + (f"\n... {len(out) - cap} more in the log" if len(out) > cap else "")


def cancel_file(head: str) -> Path:
    return journal.STATE / f"cancel-{head[:9]}"


def sweep_cancels(max_age_s: float = 86400) -> None:
    """A cancel marker outlives its ladder when `builder done` wrote it after the old check had ended: drop the old ones."""
    for p in journal.STATE.glob("cancel-*"):
        try:
            if time.time() - p.stat().st_mtime > max_age_s:
                p.unlink()
        except OSError:
            pass


def cancel_requested() -> bool:
    """The running ladder's head (its key ends `..<head9>`) has a cancel marker: its batch was superseded."""
    key = _KEY[0] or ""
    return ".." in key and cancel_file(key.rsplit("..", 1)[1]).exists()


def _env(root, cfg: Config, extra: dict | None = None) -> dict:
    # a scratch HOME: no gh token, no ~/.gitconfig credential helper, no user settings reach a check or a worker's conftest
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "TERM", "LANG")}
    if cfg.path:
        env["PATH"] = cfg.path
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"  # review 4 B6: only [check].pytest_plugins load, never a tree's entry points
    env["RUFF_NO_CACHE"] = "true"                 # the scratch tree is owner-made and read-only to the jailed user: no caches in it
    env["HOME"] = _mkdtemp("check-home-")  # jailed: a scratch dir in the workroot, which `Jail.argv` passes as HOME: the jail user's REAL home (its Library/Application Support/Fichero) is never a test's, so the real-state guard (#5530) has nothing to trip on (2026-11-03)
    if _JAIL is not None:  # the jail user's real ~/.gitconfig is not read any more (H, 2026-11-03): its trust of the owner-made check trees, and a committer for scratch commits, come from here
        gc = Path(env["HOME"]) / ".gitconfig"
        gc.write_text("[user]\n\tname = Claude\n\temail = noreply@anthropic.com\n[safe]\n\tdirectory = *\n")
        gc.chmod(0o644)
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


_SHIPPED: dict = {}  # local tree -> its copy on [check].remote; removed by the ladder that shipped it at its end (_drop_remote)
_MINE = threading.local()  # the local trees THIS thread's ladder shipped: two ladders run at once (speed 3) and one's end must not delete the other's copy
_DOWN: list = []  # a remote failed in this ladder (one alert per runner); with every runner down the runs are here
_DEAD: dict = {}  # runner -> when it failed: not tried again for DEAD_S, or until a retry finds it back
DEAD_S = 300  # 2026-11-27: the set was cleared only when no ladder ran; with ladders always running, the Air stayed out from 12:52 on


def _dead(rem: str) -> bool:
    """Is this runner marked down? A mark older than DEAD_S has expired: the runner is tried again."""
    t = _DEAD.get(rem)
    if t is not None and time.time() - t >= DEAD_S:
        _DEAD.pop(rem, None)
        return False
    return t is not None
_ALERTED: set = set()  # the runners already alerted in this ladder: one alert each, even when a retry finds one back and it fails again


def _runners(cfg: Config) -> tuple:
    return cfg.remotes or ((cfg.remote,) if cfg.remote else ())


def _runners_for_slot(cfg: Config) -> tuple:
    """The runners in the order THIS thread's ladder tries them: started at its ladder slot's own runner (slot i, runner i mod n).
    2026-11-27: every ladder tried [check].remote in the same order, so all four slots queued on the first runner that answered
    (the iMac's first gate dir, behind its heavy lock) while imac:~/fichero-gate2 and m4 had no run all day."""
    r = _runners(cfg)
    if not r:
        return r
    i = SLOT[0] % len(r)
    ring = r[i:] + r[:i]
    if not _dead(ring[0]):
        return ring
    # its own runner is down: the next FREE gate dir first, one no other held slot owns (2026-11-27 18:17-18:57: the Air was down and
    # its slot queued on imac:~/fichero-gate behind slot 1's run while imac:~/fichero-gate2 was idle)
    owned = {r[j % len(r)] for j in HELD if j != SLOT[0]}
    rest = ring[1:]
    return (ring[0], *[x for x in rest if x not in owned], *[x for x in rest if x in owned])


def _runners_for_base(cfg: Config) -> tuple:
    """The runners in order for red-on-base's base runs: the first one holds the head run (its heavy lock), so the base runs start
    on the next one; with one runner they wait on it."""
    r = _runners_for_slot(cfg)
    return r[1:] + r[:1]


PROBE = r"""sysctl -n hw.ncpu; sysctl -n vm.loadavg | tr -d '{}' | awk '{print $1}'
vm_stat | awk '/page size/ {ps=$8} /Pages (free|inactive|speculative)/ {sub(/\./, "", $NF); n+=$NF} END {printf "%.1f\n", n*ps/1073741824}'
df -g BASE /tmp | awk 'NR>1 {print $4}' | sort -n | head -1"""


def probe_runner(remote: str) -> dict:
    """One `runner` row's facts for a [check].remote entry: reachable, cores, 1-minute load, free memory and free disk (GiB), one ssh."""
    host, _, base = remote.partition(":")
    r = _ssh(host, PROBE.replace("BASE", base or "."), 30)
    vals = r.stdout.decode(errors="replace").split()
    try:
        cores, load, ram, disk = int(vals[0]), float(vals[1]), float(vals[2]), float(vals[3])
    except (IndexError, ValueError):
        return {"runner": remote, "reachable": False, "detail": (r.stderr.decode(errors="replace").strip() or "no answer")[-200:]}
    return {"runner": remote, "reachable": True, "cores": cores, "load": load, "free_ram_gb": ram, "free_gb": disk}


def runner_slots(rows: dict, cfg: Config, now: float, tick_s: float) -> tuple[int, dict]:
    """local.flow.check-slots-from-runners: the ladders that may run at once, from each runner's latest row (`rows`: runner -> row
    with `at`), and why each counts or not. A runner gives `slots_per_runner` while its row is under three ticks old, reachable, its
    load per core at most `runner_max_load`, free memory at least `runner_min_free_ram_gb` and free disk at least `remote_min_free_gb`.
    `parallel` is a ceiling; no runner counted is one ladder on the loop's machine."""
    why = {}
    for name in _runners(cfg):
        r = rows.get(name)
        if r is None or now - r.get("at", 0) >= 3 * tick_s:
            why[name] = "no row in three ticks"
        elif not r.get("reachable"):
            why[name] = f"unreachable: {r.get('detail', '')}"
        elif r["load"] / max(1, r["cores"]) > cfg.runner_max_load:
            why[name] = f"load {r['load']:g} on {r['cores']} cores is over {cfg.runner_max_load:g} a core"
        elif r["free_ram_gb"] < cfg.runner_min_free_ram_gb:
            why[name] = f"{r['free_ram_gb']:g} GiB free memory, under {cfg.runner_min_free_ram_gb:g}"
        elif r["free_gb"] < cfg.remote_min_free_gb:
            why[name] = f"{r['free_gb']:g} GiB free disk, under {cfg.remote_min_free_gb:g}"
        else:
            why[name] = f"counts {cfg.slots_per_runner}"
    n = sum(cfg.slots_per_runner for w in why.values() if w.startswith("counts"))
    return max(1, min(n, cfg.parallel)), why


def _ssh(host: str, script: str, timeout_s: float, stdin=None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script], input=stdin,
                              capture_output=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError) as e:
        return subprocess.CompletedProcess([], 255, b"", str(e).encode())


def _ship(root, cfg: Config, remote: str = "") -> str:
    """The tree's files (tracked and the overlay's untracked ones, never .git) into a fresh dir on the remote; its absolute path."""
    remote = remote or cfg.remote
    root = str(root)
    if not hasattr(_MINE, "roots"):
        _MINE.roots = set()
    _MINE.roots.add((root, remote))
    if (root, remote) in _SHIPPED:
        return _SHIPPED[(root, remote)]
    host, _, base = remote.partition(":")
    free = _ssh(host, f"df -g {base or '.'} /tmp | awk 'NR>1 {{print $4}}' | sort -n | head -1", 30).stdout.decode().strip()
    if free.isdigit() and int(free) < cfg.remote_min_free_gb:  # the iMac is 98% full: never fill it
        raise OSError(f"{host}: {free} GiB free, under {cfg.remote_min_free_gb:g}")
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
    _SHIPPED[(root, remote)] = rdir
    return rdir


def _drop_remote(cfg: Config) -> None:
    """Remove the remote copies THIS thread's ladder shipped, never another running ladder's (review 2026-11-02); the down flag
    is cleared when no ladder runs."""
    for key in list(getattr(_MINE, "roots", ())):
        if rdir := _SHIPPED.pop(key, None):
            _ssh(key[1].partition(":")[0], f"rm -rf {shlex.quote(rdir)}", 120)
    _MINE.roots = set()
    if _JAIL_USERS[0] <= 0:
        _DOWN.clear()
        _DEAD.clear()
        _ALERTED.clear()


_LOCK_CODE = ("import fcntl, os, subprocess, sys; f = open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX); "
              "sys.exit(subprocess.call(['/bin/sh', '-c', sys.argv[2]]))")


def _remote_heavy(py: str, lock: str, script: str) -> str:
    """`script` on the remote under that machine's own one-heavy-job lock (a flock file in its gate dir, held while the script runs;
    macOS has no flock(1), so the remote python takes it). Owner order 2026-11-02: one heavy job at a time per machine."""
    return shlex.join([py, "-c", _LOCK_CODE, lock, script])


SECURITY_PATH = ("/opt/homebrew/bin", "~/.local/bin")  # semgrep and gitleaks (brew), bandit (a uv tool); overridden by `[check.security].path`
GATE = "<gate>"  # stands for the runner's absolute gate dir in an argv built before the ssh that learns it


def _gate_python(cfg: Config, gate: str) -> str:
    """The one default for the interpreter on a runner: [check].remote_python, else the gate venv (<gate dir>/venv/bin/python)."""
    return cfg.remote_python or f"{gate}/venv/bin/python"


def _remote_run(name, argv, root, timeout_s, cfg: Config, extra: dict | None, cwd, remote: str = "") -> dict | None:
    """The same pytest command on [check].remote over the shipped tree: local paths become the copy's, the interpreter the
    remote's, the env the rung's own keys (a fresh base dir there). None when the remote cannot be reached: one alert row,
    and the caller runs it here (progress never waits on that machine). ponytail: the remote runs the tests unjailed as the
    ssh user; that machine holds nothing but its gate dir."""
    remote = remote or cfg.remote
    host, _, base = remote.partition(":")
    try:
        rdir = _ship(root, cfg, remote)
    except OSError as e:
        return _remote_down(cfg, str(e), remote)
    py = _gate_python(cfg, rdir.rsplit('/', 1)[0])
    sub = lambda x: str(x).replace(str(root), rdir)  # noqa: E731
    cmd = [py if a == _py(cfg) else sub(a) for a in argv]
    env = {k: sub(v) for k, v in _env(root, cfg, extra).items() if k not in ("HOME", "PATH", "TERM", cfg.base_path_env)}
    kv = " ".join(shlex.quote(f"{k}={v}") for k, v in env.items())
    bp = f'{cfg.base_path_env}="$B" ' if cfg.base_path_env else ""
    # ponytail: the runner's own TMPDIR is NOT passed through env -i: the M4's Dev Disk name holds spaces, and builder tests
    # build shell lines from unquoted tmp paths (38 red under a spaced TMPDIR, 2026-11-16; #6589 item 14). Quote them first.
    script = (f'cd {shlex.quote(sub(cwd or root))} && B=$(mktemp -d) && env -i HOME="$HOME" PATH=/usr/bin:/bin {kv} {bp}'
              f'{shlex.join(cmd)}; rc=$?; rm -rf "$B"; exit $rc')
    script = _remote_heavy(py, f"{rdir.rsplit('/', 1)[0]}/heavy.lock", script)  # the iMac's own lock
    r = run_command(name, ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script], root, timeout_s, None, as_jail=False)
    if r["exit_code"] == 255:  # ssh's own failure, never pytest's
        return _remote_down(cfg, r["stderr_tail"][-200:], remote)
    _remote_back(remote)
    return {**r, "remote": host, "runner": remote}  # the gate dir too: imac:~/fichero-gate and ~/fichero-gate2 read apart


def _outages() -> Path:
    return journal.STATE / "runners-down.json"


def _remote_back(remote: str) -> None:
    """A runner that answered again ends its outage: the outage's alert is answered `runner back` and the next outage alerts anew."""
    with journal.Lock("runners"):
        down = json.loads(_outages().read_text()) if _outages().is_file() else {}
        if remote not in down:
            return
        aid = down.pop(remote).get("alert", "")
        _outages().write_text(json.dumps(down))
    journal.append("alert-answer", id=aid, action="runner-back", ok=True, detail=f"{remote} answered again")


def _remote_down(cfg: Config, why: str, remote: str = "") -> None:
    from . import queue
    remote = remote or cfg.remote
    _DOWN.append(why)
    _DEAD[remote] = time.time()
    left = [r for r in _runners(cfg) if not _dead(r)]
    if remote in _ALERTED:
        return None
    _ALERTED.add(remote)
    # one alert per OUTAGE, not per ladder (speed batch 4, manager 2026-11-03: 40 alerts in a day while the iMac was off); the
    # outage is kept in the state dir across ladders and ends when the runner answers (_remote_back)
    with journal.Lock("runners"):
        down = json.loads(_outages().read_text()) if _outages().is_file() else {}
        if remote in down:
            return None
        aid = queue.alert("check", "remote", f"the check runner {remote} is unreachable; " + (f"trying {left[0]}" if left else "the tests ran here")
                          + f"; one alert for this outage, answered when it is back: {why}", remote, [])
        down[remote] = {"since": time.strftime("%Y-%m-%dT%H:%M:%S"), "alert": aid}
        _outages().parent.mkdir(parents=True, exist_ok=True)
        _outages().write_text(json.dumps(down))
    return None


def _run(name, argv, root, timeout_s, cfg: Config, extra: dict | None = None, cwd=None, remote: bool = False, log=None) -> dict:
    """run_command with a fresh scratch env, its HOME and base dirs removed afterwards (no litter per rung). `remote`: an
    engine pytest run, sent to the first reachable of [check].remote when one is set; a red that appears only because the runner
    changed (the first choice was down, or the run fell back here) is retried ONCE on a runner it did not run on before it counts
    (manager 2026-11-03: the iMac was off and the tests went red on the jail user's own home); nothing is told to a lane about it."""
    if not remote:
        return _local(name, argv, root, timeout_s, cfg, extra, cwd, log)
    order = lambda: _runners_for_base(cfg) if BASE_RUN[0] else _runners_for_slot(cfg)  # noqa: E731
    runners, res, used, tried = order(), None, "", set()
    while (rem := next((x for x in order() if x not in tried and not _dead(x)), None)) is not None:  # re-read: a runner that just failed
        tried.add(rem)  # moves its slot to the next free gate dir
        if (res := _remote_run(name, argv, root, timeout_s, cfg, extra, cwd, rem)) is not None:
            used = rem
            break
    if res is None:
        res = _local(name, argv, root, timeout_s, cfg, extra, cwd)
    if runners and not res.get("ok") and used != runners[0] and _KEY[0] not in RED_STOOD:  # the first choice did not run it
        for rem in runners:
            if rem == used:
                continue
            if _dead(rem) and _ssh(rem.partition(":")[0], "true", 15).returncode == 0:
                _DEAD.pop(rem, None)  # it is back
            if not _dead(rem) and (again := _remote_run(name, argv, root, timeout_s, cfg, extra, cwd, rem)) is not None:
                journal.append("runner-retry", rung=name, first=used or "here", retried=rem, ok=bool(again.get("ok")))
                if not again.get("ok"):  # red on a second gate dir too: the runner was not the cause; this ladder retries no more
                    RED_STOOD.add(_KEY[0])  # 2026-11-27 18:34-18:38: six retries in four minutes, every one red again
                return again if again.get("ok") else res
    return res


def _local(name, argv, root, timeout_s, cfg: Config, extra: dict | None, cwd, log=None) -> dict:
    env = _env(root, cfg, extra)
    try:
        return run_command(name, argv, cwd or root, timeout_s, env, log=log)
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
        return not_configured("ready", "[check].ready is empty: no ready check is declared")
    argv = [str(Path(root) / cfg.ready[0]) if "/" in cfg.ready[0] and not cfg.ready[0].startswith("/") else cfg.ready[0],
            *cfg.ready[1:]]
    return _run("ready", argv, root, timeout_s, cfg)


def _top_package(root, f: str) -> bool:
    """True when `f` sits under a top-level folder of the tree that is itself an importable package (pipeline/)."""
    try:
        top = (Path(f).resolve().relative_to(Path(root).resolve()) if Path(f).is_absolute() else Path(f)).parts[0]
    except (ValueError, IndexError):
        return False
    return (Path(root) / top / "__init__.py").is_file()


def pytest_argv(root, files: list[str], cfg: Config, package: str = "") -> list[str]:
    """The engine-shaped command (cwd = the tree root, the pinned `-c`), or with `package` a whole-tests run: its own
    pytest from that package dir, `-c <package>/pyproject.toml` only when it exists, the package dir FIRST on the path
    (so `from tests import x` finds its own `tests`), and only the plugins installed for it."""
    pkg = Path(root) / package if package else None
    conf = (pkg / "pyproject.toml" if pkg.joinpath("pyproject.toml").is_file() else None) if pkg else (Path(root) / cfg.pytest_config if cfg.pytest_config else None)
    cfgfile = ["-c", str(conf)] if conf else []
    plugins = [x for p in cfg.pytest_plugins for x in ("-p", p)]
    paths = [str(Path(root) / p) for p in cfg.python_path]
    if not pkg and any(_top_package(root, f) for f in files):  # a test of a top-level package (pipeline/tests) imports it from the tree root
        paths.append(str(root))
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
    # #6589: resolved where it runs: a gate dir that is a link (the M4's, the iMac's ~/fichero-gate) gives pytest a real
    # cwd, and a `-c` or a folder named through the link roots the test ids outside their folders, so one folder's
    # autouse conftest fixture ran under every test of the run.
    conf_at = args.index("-c") + 1 if "-c" in args else -1
    code = ("import os, sys, shutil, tempfile; R = os.path.realpath; i = next((n for n, p in enumerate(sys.path) if p.endswith('site-packages')), len(sys.path) - 1) + 1; "
            f"sys.path[i:i] = [R(p) for p in {paths!r}]\n"
            "sys.pycache_prefix = tempfile.mkdtemp(prefix='check-pyc-')\n"
            f"a = {args!r}; c = {conf_at!r}\n"
            "if c > 0: a[c] = R(a[c])\n"
            "import pytest; rc = pytest.main(a); shutil.rmtree(sys.pycache_prefix, ignore_errors=True); sys.exit(rc)")
    return [_py(cfg), "-I", "-c", code]


def pytest_rung(root, files: list[str], cfg: Config = Config(), timeout_s: float = 1800) -> dict:  # noqa: B008
    """Named test files only (the env gives a fresh base path, so a run never opens real data)."""
    if not files:
        return run_command("pytest", [sys.executable, "-c", "import sys; sys.exit('no test files named')"], root, 5)
    # safe path comes from `python -I` in pytest_argv (it implies -P): the cwd is not on sys.path, so a worker's pytest.py shadows
    # nothing. NOT a PYTHONSAFEPATH env var: `-I` ignores it for pytest, and every child a test starts inherited it, so a guard
    # script a test runs lost its own dir from sys.path (2026-11-05: test_guardrails_scan_floor red in every safe-path rung)
    return _run("pytest", pytest_argv(root, files, cfg), root, timeout_s, cfg, None, remote=True)


def whole_tests_rung(root, tests_dir: str, cfg: Config = Config(), timeout_s: float = 1800) -> dict:  # noqa: B008
    """One [check.whole_tests] dir run whole as ITS OWN pytest, the way its suite runs everywhere else: cwd = its package
    dir (the tests dir's parent), so a sibling `tests` package in another project never shadows its `from tests import x`."""
    package = str(Path(tests_dir).parent)
    cwd = Path(root) / package
    argv = pytest_argv(root, [str(Path(root) / tests_dir)], cfg, package=package)
    return _run("pytest", argv, root, timeout_s, cfg, None, cwd=cwd, remote=True)  # safe path from -I, as pytest_rung


LOAD_FLAKE = re.compile(r"TransactionException: .*Cannot CHECKPOINT|OSError|_path_stat|Too many open files")


def _load_flake(r: dict) -> bool:
    """A red pytest run whose only trouble is ERROR lines (no FAILED test) of a load kind: a teardown/import OSError or a DuckDB
    CHECKPOINT TransactionException (manager 2026-11-02: two of these on one lane under load ~35, neither a test failing)."""
    out = (r.get("stdout_tail") or "") + (r.get("stderr_tail") or "")
    return (not r["ok"] and not r.get("timed_out") and not re.search(r"^FAILED ", out, re.M) and bool(re.search(r"^ERROR ", out, re.M))
            and bool(LOAD_FLAKE.search(out)))


def _retry_flake(run_it, r: dict, what: str) -> dict:
    """Once, alone: the same run again; the retry is a journal row either way, and the second result stands."""
    if not _load_flake(r):
        return r
    journal.append("check", state="retry", rung=what, detail="a load flake (only ERROR lines of a teardown/import OSError or a CHECKPOINT TransactionException): re-run once alone")
    return {**run_it(), "retried": True}


def _heavy(what: str, local_only: bool = False):
    """The machine's one-heavy-job lock around a rung; local_only: a Config with [check].remote runs it on the iMac, whose own lock it takes."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapped(*a, **k):
            cfg = next((x for x in (*a, *k.values()) if isinstance(x, Config)), None)
            if local_only and cfg is not None and _runners(cfg):
                return fn(*a, **k)
            with journal.heavy(what):
                return fn(*a, **k)
        return wrapped
    return deco


@_heavy("the full engine suite", local_only=True)
def green_runs(tree, files: list[str], whole: tuple, cfg: Config, timeout_s: float) -> dict:
    """The green run: the engine-shaped pytest over the changed test files, then each whole-tests dir as its own pytest.
    One row: the first red (or the last green) as the row's own fields, `runs` = every command and its tail."""
    runs = []
    # a whole_tests FILE (a tree-scanning guardrail test, 2026-11-08) runs engine-shaped beside the changed tests; a dir runs whole
    files = list(dict.fromkeys([*files, *(d for d in whole if d.endswith(".py"))]))
    whole = tuple(d for d in whole if not d.endswith(".py"))
    groups: dict[str, list[str]] = {}  # one pytest per top-level package: two `tests` dirs in one run shadow each other
    for f in files:
        groups.setdefault(Path(f).parts[0] if len(Path(f).parts) > 1 else "", []).append(f)
    for fs in groups.values():
        if runs and not runs[-1]["ok"]:
            break
        runs.append(_retry_flake(lambda fs=fs: pytest_rung(tree, fs, cfg, timeout_s), pytest_rung(tree, fs, cfg, timeout_s), "green-run"))
    for d in whole:
        if runs and not runs[-1]["ok"]:
            break
        runs.append(_retry_flake(lambda d=d: whole_tests_rung(tree, d, cfg, timeout_s), whole_tests_rung(tree, d, cfg, timeout_s), "green-run"))
    row = next((r for r in runs if not r["ok"]), runs[-1])
    if not row["ok"] and (m := re.search(r"ERROR collecting (\S+).*?\n(?:.*\n)*?(E\s+\w+Error[^\n]*)", row.get("stdout_tail") or "")):
        # a collection error is not a red test (manager 2026-11-02): say which file could not be collected and why
        row = {**row, "stderr_tail": f"could not collect {m.group(1)}: {m.group(2).lstrip('E ').strip()}\n" + (row.get("stderr_tail") or "")}
    return {**row, "runs": [{k: r[k] for k in ("argv", "exit_code", "ok", "seconds", "stdout_tail", "stderr_tail")} for r in runs]}


def _isolated(script: Path, root: Path, cfg: Config) -> list[str]:
    """`python -I` so a planted sitecustomize/.pth is never imported; the tree's paths go in after site."""
    paths = [str(script.parent), *[str(root / p) for p in cfg.python_path]]
    code = ("import sys, runpy; i = next((n for n, p in enumerate(sys.path) if 'site-packages' in p), len(sys.path)); "
            f"sys.path[i:i] = {paths!r}; runpy.run_path({str(script)!r}, run_name='__main__')")
    return [_py(cfg), "-I", "-c", code]


def guards(root, cfg: Config, changed: list[str] | None = None) -> dict:
    """The guards rung: the guards that run HERE under their OWN lock (speed batch 3, manager 2026-11-03: never behind the machine's
    heavy lock, where it waited 65 min for a dev build). The ones sent to a runner go outside it (2026-11-26: the lock held across the
    remote batch made every lane's guards wait on one another, 2 h of waits a day with three runners free). `changed`: the batch's
    paths, for `[check].guards_by_diff`; None (verify, the nightly) = every guard."""
    return _guards(root, cfg, changed)


STALE_ENTRY = re.compile(r"no longer occur", re.I)  # a shrink-only allowlist's red: an entry the tree no longer has


def guards_on_current_base(root, since: str, head: str, pinned, cfg: Config, tree, **scratch) -> dict:
    """local.check.stale-base-guards (#6589): the guards over `tree` (head on its own base). When every red is a shrink-only allowlist's
    "no longer occurs" and the lane's base is older than the pinned copy's (integration now), the guards run again over head merged with
    that tip: integration's allowlist names code the old base never had, so the merge is what lands and what is judged. Green there =
    green, with the reason said; a conflict or a red there keeps the first red."""
    changed = _lines(root, "diff", "--name-only", "--no-renames", f"{since}...{head}") if cfg.guards_by_diff else None
    by = (changed,) if changed is not None else ()
    r = guards(tree, cfg, *by)
    reds = [x for x in r.get("results") or [] if not x.get("ok")]
    if r["ok"] or not reds or not all(STALE_ENTRY.search(f"{x.get('stdout_tail', '')}\n{x.get('stderr_tail', '')}") for x in reds):
        return r
    tip = (_lines(pinned, "rev-parse", "HEAD") or [""])[0]
    if not tip or tip.startswith(since) or _git(root, "merge-base", "--is-ancestor", tip, head)["ok"]:
        return r  # the lane already has integration's tip: a real red
    tree_id = (_lines(root, "merge-tree", "--write-tree", head, tip) or [""])[0]  # None (a conflict, exit 1) = no tree
    who = ("-c", "user.name=builder", "-c", "user.email=builder@localhost")  # a throwaway commit object, never on a branch
    merged = (_lines(root, *who, "commit-tree", tree_id, "-p", head, "-p", tip, "-m", "check: head merged with the current base") or [""])[0] if tree_id else ""
    if not merged:
        return {**r, "reason": (r.get("reason") or "") + f" (head does not merge cleanly with {tip[:9]}: the stale-base re-run was not possible)"}
    mtree = _scratch_tree(root, merged, pinned, cfg, **scratch)
    try:
        again = guards(mtree, cfg, *by)
    finally:
        drop_tree(root, mtree)
    if not again["ok"]:
        return r
    names = ", ".join(x.get("name", "?") for x in reds)
    journal.append("check", state="stale-base-guards", rung="guards", head=head, base=tip, detail=f"{names}: green on head merged with {tip[:9]}")
    return {**again, "reason": f"{names} reported allowlist entries that no longer occur on the lane's older base; on head merged with "
                               f"the current base {tip[:9]} every guard is green (the current base still needs those entries)", "stale_base": True}


def untouched_guards(found: list[Path], root: Path, cfg: Config, changed: list[str]) -> set[Path]:
    """The guards with declared inputs (`[check.guard_inputs]`) that no changed path is under, and whose own script did not change:
    their verdict is base's, which the nightly's full gate judges. A guard with no declared inputs reads the whole tree: it runs."""
    def under(n: str, p: str) -> bool:
        p = p.rstrip("/")
        return n == p or n.startswith(p + "/")
    out = set()
    for s in found:
        ins = cfg.guard_inputs.get(s.stem)
        own = str(s.relative_to(root)) if s.is_relative_to(root) else str(s)
        if ins and own not in changed and not any(under(n, p) for n in changed for p in ins):
            out.add(s)
    return out


def _guards(root, cfg: Config, changed: list[str] | None = None) -> dict:
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
    skip = untouched_guards(found, root, cfg, changed) if cfg.guards_by_diff and changed is not None else set()
    if skip:
        journal.append("check", state="guards-by-diff", rung="guards", skipped=len(skip), ran=len(found) - len(skip),
                       detail="guards whose declared inputs the batch does not touch: base's verdict, the nightly runs them")
    cache = _guard_cache_load()
    keys = {s: _guard_key(root, s, cfg) if GUARD_CACHE[0] else "" for s in found if s not in skip}
    away = [s for s in keys if not (keys[s] and keys[s] in cache) and _guard_away(s, cfg)]
    there = _remote_guard_batch(away, root, cfg) if away else None  # ONE ssh for all of them; None = no runner: they run here
    with journal.Lock("guards", what="the guards rung"):  # only the ones run here; the remote batch above ran outside it
        _guards_here(found, skip, keys, cache, there, results, root, cfg)
    _guard_cache_save(cache)
    return {"ok": all(r["ok"] for r in results), "reason": "", "results": results}


def _guards_here(found, skip, keys, cache, there, results, root, cfg) -> None:
    for s in found:
        if s in skip:
            results.append({"name": s.stem, "argv": [str(s)], "ok": True, "seconds": 0, "exit_code": 0, "skipped": "inputs untouched",
                            "stdout_tail": "", "stderr_tail": ""})
            continue
        key = keys[s]
        if key and key in cache:  # the same guard, the same inputs, the same tools: its green is reused (speed 5)
            results.append({**cache[key], "name": s.stem, "argv": [str(s)], "seconds": 0, "cached": True})
            continue
        r = (there or {}).get(s.stem) or _run(s.stem, _isolated(s, root, cfg), root, cfg.guard_timeout_s, cfg)
        if not r["ok"] and r.get("remote"):  # a red over there may be the runner's (no .git, no tool): it counts only if red here
            journal.append("check", state="retry", rung="guards", detail=f"{s.stem} red on {r['remote']}: re-run here before it counts")
            r = {**_run(s.stem, _isolated(s, root, cfg), root, cfg.guard_timeout_s, cfg), "rerun_here": True}
        if r.get("timed_out"):  # a load flake (manager 2026-11-03: a guard printed all-ok, then hit the timeout at load 35): once more
            journal.append("check", state="retry", rung="guards", detail=f"{s.stem} timed out after {cfg.guard_timeout_s:g} s: re-run once")
            r = {**_run(s.stem, _isolated(s, root, cfg), root, cfg.guard_timeout_s, cfg), "retried": True}
        r["argv"] = [str(s)]
        results.append(r)
        if key and r["ok"]:  # only a green is kept: a red always runs again
            cache[key] = {k: r[k] for k in ("exit_code", "ok", "timed_out", "stdout_tail", "stderr_tail")}


_HERE_ONLY = re.compile(r"\b(subprocess|git|swiftlint|xcodebuild)\b")


def _guard_away(script: Path, cfg: Config) -> bool:
    """Whether this guard runs on a [check].remote runner (manager 2026-11-06: the Pro, where the owner's Xcode runs, sat at load 30 to
    57 under the ladders). `remote_guards = "auto"`: only a guard that needs nothing the shipped tree lacks (it names no git, subprocess,
    swiftlint or xcodebuild) goes; true sends every guard, false none.
    ponytail: a name match, not an analysis; a guard that needs the Pro and is sent anyway is caught by the re-run here on a red."""
    if cfg.remote_guards == "auto":
        try:
            return not _HERE_ONLY.search(script.read_text(errors="replace"))
        except OSError:
            return False
    return bool(cfg.remote_guards)


_GUARD_DRIVER = """
import json, os, shutil, subprocess, sys, tempfile, time
p = json.load(sys.stdin)
out = {}
for name, argv in p["jobs"]:
    b = tempfile.mkdtemp()
    env = {"HOME": os.environ["HOME"], "PATH": "/usr/bin:/bin", **p["env"], **({p["bp"]: b} if p["bp"] else {})}
    t = time.time()
    try:
        c = subprocess.run(argv, cwd=p["cwd"], env=env, capture_output=True, text=True, timeout=p["timeout"])
        rc, o, e, to = c.returncode, c.stdout, c.stderr, False
    except subprocess.TimeoutExpired as x:
        rc, o, e, to = -9, str(x.stdout or ""), str(x.stderr or ""), True
    shutil.rmtree(b, ignore_errors=True)
    out[name] = {"exit_code": rc, "ok": rc == 0 and not to, "timed_out": to, "seconds": round(time.time() - t, 1),
                 "stdout_tail": o[-4000:], "stderr_tail": e[-4000:]}
print(json.dumps(out))
"""


def _remote_guard_batch(scripts: list, root, cfg: Config) -> dict | None:
    """{guard name: result} for `scripts`, all run in ONE ssh on the first reachable [check].remote over the shipped tree, each with
    its own timeout and base dir, under no heavy lock there (guards are light; behind a pytest run they would time out). None when no
    runner is reachable: the caller runs them here."""
    for rem in _runners_for_slot(cfg):
        if _dead(rem):
            continue
        host = rem.partition(":")[0]
        try:
            rdir = _ship(root, cfg, rem)
        except OSError as e:
            _remote_down(cfg, str(e), rem)
            continue
        py = _gate_python(cfg, rdir.rsplit('/', 1)[0])
        sub = lambda x: str(x).replace(str(root), rdir)  # noqa: E731
        jobs = [[s.stem, [py if a == _py(cfg) else sub(a) for a in _isolated(s, root, cfg)]] for s in scripts]
        env = {k: sub(v) for k, v in _env(root, cfg).items() if k not in ("HOME", "PATH", "TERM", cfg.base_path_env)}
        payload = json.dumps({"jobs": jobs, "env": env, "cwd": rdir, "timeout": cfg.guard_timeout_s, "bp": cfg.base_path_env})
        r = _ssh(host, f"{shlex.quote(py)} -I -c {shlex.quote(_GUARD_DRIVER)}", cfg.guard_timeout_s * len(jobs) + 60, payload.encode())
        try:
            out = json.loads(r.stdout.decode().strip().splitlines()[-1]) if r.returncode == 0 else None
        except (ValueError, IndexError):
            out = None
        if out is None:
            _remote_down(cfg, f"guard batch: exit {r.returncode}: {r.stderr.decode(errors='replace')[-200:]}", rem)
            continue
        _remote_back(rem)
        journal.append("check", state="remote-guards", rung="guards", runner=host, guards=len(jobs))
        return {n: {**out[n], "name": n, "argv": a, "remote": host} for n, a in jobs if n in out}
    return None


GUARD_CACHE: list = [None]  # the cache file, set by the chain and `builder check`; None (tests) = no cache
_VERSIONS: list = []


def _versions(cfg: Config) -> str:
    """The interpreter and the linters a guard may call: a new version is a new key."""
    if not _VERSIONS:
        out = []
        for argv in ([_py(cfg), "--version"], ["ruff", "--version"], ["swiftlint", "version"]):
            try:
                out.append(subprocess.run(argv, capture_output=True, text=True, timeout=30).stdout.strip())
            except (OSError, subprocess.TimeoutExpired):
                out.append("-")
        _VERSIONS.append("|".join(out))
    return _VERSIONS[0]


def _guard_key(root, script: Path, cfg: Config) -> str:
    """sha256 of the guard's own bytes, the git tree ids of the inputs it declares (or of the whole tree), and the tools'
    versions; '' (no cache, it runs) when any part cannot be read. Any doubt = run."""
    import hashlib
    try:
        h = hashlib.sha256(script.read_bytes())
    except OSError:
        return ""
    prefixes = cfg.guard_inputs.get(script.stem) or [""]
    for pre in prefixes:
        tid = (_lines(root, "rev-parse", f"HEAD:{pre}".rstrip("/").rstrip(":") if pre else "HEAD^{tree}") or [""])[0]
        if not tid:
            return ""
        h.update(f"{pre}={tid};".encode())
    # what is not in the tree id: the pinned overlay and anything uncommitted (its diff and its status)
    h.update("\n".join((_lines(root, "diff", "HEAD") or []) + (_lines(root, "status", "--porcelain", "--untracked-files=all") or [])).encode())
    h.update(_versions(cfg).encode())
    return h.hexdigest()


def _guard_cache_load() -> dict:
    try:
        return json.loads(Path(GUARD_CACHE[0]).read_text()) if GUARD_CACHE[0] else {}
    except (OSError, ValueError):
        return {}


def _guard_cache_save(cache: dict) -> None:
    if GUARD_CACHE[0]:
        try:
            tmp = Path(f"{GUARD_CACHE[0]}.{threading.get_ident()}")  # two ladders at once: never a half-written file
            tmp.write_text(json.dumps(dict(list(cache.items())[-2000:])))
            tmp.replace(GUARD_CACHE[0])
        except OSError:
            pass


def contract_current(root, changed: list[str], cfg: Config, timeout_s: float = 300) -> dict:
    """The project's contract guards, only when the diff touches its contract paths."""
    if not cfg.contract_guards:
        return not_configured("contract-current", "[check].contract_guards is empty: no contract guard is declared")
    if not cfg.contract_paths:
        return not_configured("contract-current", "[check].contract_paths is empty: no path makes the contract guards run")
    if not any(f.startswith(cfg.contract_paths) for f in changed):
        return {"ok": True, "skipped": True, "results": []}
    root = Path(root)
    results = [_run(Path(g).stem, _isolated(root / g, root, cfg), root, timeout_s, cfg)
               for g in cfg.contract_guards]
    return {"ok": all(r["ok"] for r in results), "skipped": False, "results": results}


def since_guards(root, since: str, changed: list[str], cfg: Config, timeout_s: float = 300) -> dict:
    """Each `[check].since_guards` guard whose prefix the diff touches, run in the scratch tree with `--since <base>`: its
    question about this range only (#6318: the SwiftLint ratchet's `--since`, which the gate ran and the ladder did not)."""
    todo = [g for g, prefix in cfg.since_guards.items()
            if any(f.startswith(tuple([prefix] if isinstance(prefix, str) else prefix)) for f in changed)]
    if not todo:
        return {"ok": True, "skipped": True, "results": []}
    root = Path(root)
    results = [_run(Path(g).stem, [*_isolated(root / g, root, cfg), "--since", since], root, timeout_s, cfg) for g in todo]
    return {"ok": all(r["ok"] for r in results), "skipped": False, "results": results}


def build_names(root, since: str, head: str) -> list[str]:
    """Changed paths for the build rung: added, modified AND deleted (a deleted Swift file still referenced must fail the
    build, review 1 M7); the other rungs keep their added-or-modified list."""
    return [f for _s, _m, f in _changes(root, since, head, "--diff-filter=AMD")]


# manager 2026-11-03: a build rung went red once on this alone (a killed build's xcodebuild still held the jail's derived dir)
BUILD_DB_LOCKED = re.compile(r"build\.db.*database is locked|database is locked.*two concurrent builds", re.S)
# 2026-11-05: four red builds in a night were all real source errors (`X.swift:157:13: error: ...`), and each clean retry rebuilt from
# nothing for 6 to 9 min only to say the same, leaving the next build cold too. A red naming a Swift source error is the code's: no retry.
SOURCE_ERROR = re.compile(r"\.swift:\d+:\d+: error: ")
BUILD_RETRY_WAIT_S = 30  # ponytail: one fixed wait; the other build's end is not watched


SHARED_DERIVED = ("build", "test", "ui")  # these share the runner's one `<gate>/derived`, kept between checks so a build is incremental
STALE_CACHE = re.compile(r"No such module '|module '[^']+' not found|PCM|precompiled module|was compiled with module cache path|module file '[^']+' is out of date")
TEST_FAILED = re.compile(r"\*\* TEST FAILED \*\*|Test [Cc]ase '[^']+' failed|^Failing tests:[ \t]*\n[ \t]+\S|✘ Test run with \d+ tests?|^[ \t]+\S+\(\)[ \t]*\n\s*\*\* TEST EXECUTE FAILED \*\*", re.M)
# a failing test is the code's red, not the runner's: XCTest's lines, Swift Testing's run line and xcodebuild's `Failing tests:` list,
# which end in "** TEST EXECUTE FAILED **" (2026-11-26, the train: 14 failing cases were labelled "the runner could not run the tests")
FAILING_LIST = re.compile(r"^Failing tests:[ \t]*\n((?:[ \t]+\S.*(?:\n|$))+)", re.M)


def failing_cases(out: str) -> list[str]:
    """The failing test cases a Swift test run names: XCTest's `Test Case '...' failed` and xcodebuild's `Failing tests:` list."""
    names = set(re.findall(r"Test [Cc]ase '([^']+)' failed", out))
    for block in FAILING_LIST.findall(out):
        names |= {ln.strip() for ln in block.splitlines() if ln.strip()}
    return sorted(names)
WARNING_PLATFORMS = {"build": "mac", "ios-sim": "ios"}  # the remote build rung holds the mac count, the iOS daily build the iOS count (the Swift test target holds none; iPad waits for a scheme that carries the iPad plan)
RATCHET_SCRIPT = client.scripts_dir() / "check_xcode_warning_ratchet.py"  # the harness's own copy judges: a batch's own script never runs, jailed or not


def _warning_ratchet(tree: Path, host: str, bundle: str, name: str, r: dict) -> None:
    """#6610 `perf-sweep.warnings.ratchet`: the green build's result bundle, read over there with xcresulttool, held against the tree's
    `scripts/xcode_warning_baseline.json` by `scripts/check_xcode_warning_ratchet.py --hold-only`. Exit 1 turns the row red with the ratchet's
    lines (it is the code's, never the runner's); exit 2 (BLIND: no baseline yet, an unreadable bundle) is a journal note, never a red and
    never a silent green. Only a build the rung ran: the rung's own tree is read, nothing is written."""
    if not RATCHET_SCRIPT.is_file():
        return
    got = _ssh(host, f"xcrun xcresulttool get build-results --path {shlex.quote(bundle)}", 300)
    if got.returncode or not got.stdout:
        journal.append("check", state="warnings-blind", rung=name, detail=got.stderr.decode(errors="replace")[-200:] or "no build results")
        return
    fd, tmp = tempfile.mkstemp(prefix=f"{name}-", suffix=".warnings.json")  # removed below: nothing accumulates in build-logs
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(got.stdout)
        p = subprocess.run([sys.executable, str(RATCHET_SCRIPT), "--platform", WARNING_PLATFORMS[name], "--bundle", tmp, "--hold-only",
                            "--baseline", str(Path(tree) / "scripts" / "xcode_warning_baseline.json")], capture_output=True, text=True, timeout=120)
    finally:
        Path(tmp).unlink(missing_ok=True)
    if p.returncode == 1:
        r["ok"] = False
        r["warnings_grew"] = True
        r["stdout_tail"] = ((r.get("stdout_tail") or "") + "\n" + p.stdout)[-6000:]
    elif p.returncode:
        journal.append("check", state="warnings-blind", rung=name, detail=(p.stderr or p.stdout)[-200:])


def with_result_bundle(argv, path) -> list[str]:
    """#6610 `perf-sweep.warnings.from-the-result-bundle`: the Xcode command with `-resultBundlePath <path>` before its action, so the
    warnings are read from the bundle and never a regex over the log alone. A path already there is replaced; any other command is left alone."""
    b = list(argv)
    if not b or Path(b[0]).name != "xcodebuild":
        return b
    if "-resultBundlePath" in b[:-1]:
        b[b.index("-resultBundlePath") + 1] = str(path)
        return b
    return [*b[:-1], "-resultBundlePath", str(path), b[-1]]


def build(root, changed: list[str], cfg: Config) -> dict:
    """The project's build-only compile, only when the diff touches its build paths; one at a time under the lock
    (owner 2026-11-01: a Swift change nobody compiled reached the land gate; builds stay serial on this machine). The skip is decided
    BEFORE the heavy lock (2026-11-06: a docs-only or harness batch waited hours on the owner's Xcode hold just to learn it builds nothing)."""
    if not cfg.build or not any(f.startswith(cfg.build_paths) for f in changed):
        return {"ok": True, "skipped": True, "results": []}
    if cfg.build_remote and (r := _remote_build(root, cfg)) is not None and not r.get("remote_env_red"):
        return r  # an env-red there (not the code's) builds here, as before
    return _build_locked(root, changed, cfg)  # ponytail: the remote down under the owner's hold waits here, holding its slot


def _remote_arg(path: str) -> str:
    """`path` as one argument of a remote shell command; a leading `~/` still expands there."""
    return "~/" + shlex.quote(path[2:]) if path.startswith("~/") else shlex.quote(path)


BUILD_ENV_RED_ALERT_AFTER = 3
_BUILD_RAN = {"build-remote-env-red": False, "build-remote-crash": False, "build-remote": True}  # journal state -> did the build run there


def _build_env_red(host: str, name: str, why: str) -> None:
    """Called just after the env-red's journal row is written. The count is read from the journal (each ladder is its own process), the
    consecutive env-reds of that runner since its last build that ran: the third raises one alert naming the runner and the last error
    (the build then runs here, as before, but no longer quietly)."""
    rows = journal.read()
    start, run = 0, 0  # `start`: where this runner's streak began (after its last build that ran); `run`: its env-reds since
    for i, r in enumerate(rows):
        if r.get("event") == "check" and r.get("runner") == host and r.get("state") in _BUILD_RAN:
            start, run = (i + 1, 0) if _BUILD_RAN[r["state"]] else (start, run + 1)
    already = any(r.get("event") == "alert" and r.get("step") == "rung-build-remote" and f" on {host} " in r.get("what", "") for r in rows[start:])
    if run >= BUILD_ENV_RED_ALERT_AFTER and not already:  # a streak already past three (older rows) alerts now, once per streak
        _rung_alert("build-remote", f"the remote {name} on {host} env-red {run} times in a row; last error: {why}")


def _remote_build(root, cfg: Config, cmd: tuple = (), name: str = "build", reuse: bool = True, timeout_s: float | None = None) -> dict | None:
    """The build rung on `[check].build_remote` (manager 2026-11-06 t88: the M1 Air, so the Pro stays the owner's; the first step of
    the machine pool, #6356): the stable build tree rsynced (mtimes kept, removed files removed, no .git) to <dir>/build-tree there,
    xcodebuild there with <dir>/derived as its derived data, under that Mac's own one-heavy-job lock. Everything lives under the
    one registered root <dir>. A green key is reused as here. None when that Mac cannot be reached (ssh failed): the build runs here.
    A stale-cache red (module not found, PCM mismatch) there clears that derived dir and builds once more, saying so."""
    host, _, base = cfg.build_remote.partition(":")
    where = _remote_arg(base or ".")
    home = _ssh(host, f"mkdir -p {where} && cd {where} && pwd -P", 30)  # -P: the physical path; Xcode sees one derived-data path, not a symlink's two
    rbase = home.stdout.decode().strip()
    if home.returncode or not rbase.startswith("/"):
        journal.append("check", state="build-remote-down", rung="build", runner=host, detail=home.stderr.decode(errors="replace")[-200:])
        return None
    if name == "security" and not _security_push(root, host, rbase):  # local prep, before the lock
        return None
    # one build at a time over the stable tree here and the one there: a second ladder's rsync must never rewrite a tree mid-build
    with build_lock(cfg):
        return _remote_build_locked(root, cfg, host, rbase, cmd, name, reuse, timeout_s)


def _security_push(root, host: str, rbase: str) -> bool:
    """The batch's history to the runner's persistent bare repo `<rbase>/security.git` (ref `scan`): only the objects it lacks travel, so
    no full clone a run (the scratch tree's own .git is a worktree link or a --shared clone, pointing back at this machine's repo, so
    rsync would ship no history). Done BEFORE the build lock is taken: it is local prep, not a heavy job. False when the runner refused."""
    head = (_lines(root, "rev-parse", "HEAD") or [""])[0]
    bare = f"{rbase}/security.git"
    init = _ssh(host, f"git init --bare -q {shlex.quote(bare)}", 60)
    if not head or init.returncode:
        journal.append("check", state="build-remote-down", rung="security", runner=host, detail=init.stderr.decode(errors="replace")[-200:] or "no HEAD")
        return False
    env = {**_git_env(), "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=10"}
    push = run_command("security-push", _git_argv(root, ("push", "-q", "--force", f"{host}:{bare}", f"{head}:refs/heads/scan")), root, SCRATCH_CHECKOUT_S, env, as_jail=False)
    if not push["ok"]:
        journal.append("check", state="build-remote-down", rung="security", runner=host, detail=f"push: {push['stderr_tail'][-200:]}")
    return push["ok"]


def _remote_build_locked(root, cfg: Config, host: str, rbase: str, cmd: tuple = (), name: str = "build", reuse: bool = True, timeout_s: float | None = None) -> dict | None:
    if name == "security":  # a worktree of this run's own head commit (pushed under `scan`) in its own folder there (the build rung's tree is untouched); history comes with it
        return _remote_build_synced(root, cfg, host, rbase, cmd, name, reuse, str(root), True, timeout_s)
    return _remote_build_synced(root, cfg, host, rbase, cmd, name, reuse, _stable_build_tree(root, cfg) if cfg.build_tree else str(root), False, timeout_s)


def _remote_build_synced(root, cfg: Config, host: str, rbase: str, cmd: tuple, name: str, reuse: bool, src: str, keep_git: bool, timeout_s: float | None = None) -> dict | None:
    key = _build_key(src, cfg, cmd) if reuse else ""  # a measurement is never reused: the same tree on another night is another figure
    if key and (hit := _build_results().get(key)):
        journal.append("check", state="build-reused", rung=name, detail=f"green at {hit.get('head', '?')[:9]} {hit.get('ts', '')}: {key[:12]}")
        return {"ok": True, "skipped": False, "results": [{"name": "build", "ok": True, "exit_code": 0, "timed_out": False, "seconds": 0,
                                                           "stdout_tail": f"reused: the same build key built green at {hit.get('head', '?')[:9]}", "stderr_tail": "", "reused": key}]}
    tree, derived = f"{rbase}/{'security-tree' if keep_git else 'build-tree'}", f"{rbase}/derived" + ("" if name in SHARED_DERIVED else f"-{name}")  # a daily build: its own derived data
    if keep_git:
        # the exact commit, never the shared `scan` ref: another ladder's push may have moved it since this run's push
        head = (_lines(root, "rev-parse", "HEAD") or [""])[0]
        g, t = shlex.quote(f"{rbase}/security.git"), shlex.quote(tree)
        sync = run_command("security-checkout", ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
                           f"git --git-dir={g} worktree prune; rm -rf {t}; git --git-dir={g} worktree add -q -f --detach {t} {shlex.quote(head)}"], src, 300, None, as_jail=False)
    else:
        sync = run_command("build-sync", ["rsync", "-a", "--delete", "--exclude", ".git", "-e", "ssh -o BatchMode=yes -o ConnectTimeout=10",
                                          f"{src}/", f"{host}:{_remote_arg(tree)}/"], src, 900, None, as_jail=False)
    if not sync["ok"]:
        journal.append("check", state="build-remote-down", rung=name, runner=host, detail=f"{'checkout' if keep_git else 'rsync'}: {sync['stderr_tail'][-200:]}")
        return None
    b = [a.replace(GATE, rbase) for a in (cmd or cfg.build)]
    if "-derivedDataPath" in b[:-1]:
        b[b.index("-derivedDataPath") + 1] = derived
    b = [a for a in b if a != "-disableAutomaticPackageResolution"]  # its first build there resolves the packages into its own derived data
    bundle = f"{rbase}/results/{name}.xcresult"  # a build only: Xcode refuses a bundle path that exists, so it is removed first
    b = with_result_bundle(b, bundle)
    pre = f"rm -rf {shlex.quote(bundle)} && mkdir -p {shlex.quote(rbase + '/results')} && " if "-resultBundlePath" in b else ""
    script = _remote_heavy(f"{rbase}/venv/bin/python", f"{rbase}/heavy.lock", f"{pre}cd {shlex.quote(tree)} && {shlex.join(b)}")
    log = journal.STATE / "build-logs" / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}-{host}.log"
    r = run_command(name, ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script], src, timeout_s or cfg.build_timeout_s, None,
                    as_jail=False, log=log)
    if r["exit_code"] == 255:
        journal.append("check", state="build-remote-down", rung=name, runner=host, detail=r["stderr_tail"][-200:])
        return None
    if not r["ok"] and not r.get("timed_out") and name != "perf" and STALE_CACHE.search((r.get("errors") or "") + (r.get("stdout_tail") or "") + (r.get("stderr_tail") or "")):
        # a stale module cache (a module not found, a PCM mismatch) is the runner's kept DerivedData, not the code: clear it, build once more
        journal.append("check", state="retry", rung=name, runner=host, detail=f"stale-cache signature: {derived} cleared, built once more")
        _ssh(host, f"rm -rf {shlex.quote(derived)}/* {shlex.quote(derived)}/.[!.]* 2>/dev/null; true", 300)
        r = {**run_command(name, ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, script], src, timeout_s or cfg.build_timeout_s, None,
                           as_jail=False, log=log.with_suffix(".clean.log")), "retried": "clean"}
        r["stdout_tail"] = f"retried once with {derived} cleared (a stale-cache signature)\n" + (r.get("stdout_tail") or "")
        if r["exit_code"] == 255:
            journal.append("check", state="build-remote-down", rung=name, runner=host, detail=r["stderr_tail"][-200:])
            return None
    if not r["ok"] and not r.get("timed_out") and name == "perf":
        # a perf run that exits non-zero crashed over there: its stderr is the row, never "unreachable"
        journal.append("check", state="build-remote-crash", rung=name, runner=host, detail=(r.get("stderr_tail") or "")[-200:])
        _build_env_red(host, name, (r.get("stderr_tail") or "")[-200:])
        return {"ok": False, "skipped": False, "crashed": True, "remote_env_red": True, "remote": host, "results": [r]}
    if not r["ok"] and name != "perf" and not SOURCE_ERROR.search((r.get("errors") or "") + (r.get("stdout_tail") or "")) \
            and not (name in ("test", "ui") and TEST_FAILED.search(r.get("stdout_tail") or "")):
        # a red that names no Swift source error is that Mac's (a missing component, a package fetch, a timeout), never the code's
        journal.append("check", state="build-remote-env-red", rung=name, runner=host, detail=(r.get("stderr_tail") or "")[-200:])
        _build_env_red(host, name, (r.get("stderr_tail") or "")[-200:])
        return {"ok": False, "skipped": False, "remote_env_red": True, "remote": host, "results": [r]}  # the row stays: its stderr says why
    r["remote"] = host
    if r["ok"] and name in WARNING_PLATFORMS and not keep_git:
        _warning_ratchet(Path(src), host, bundle, name, r)
    journal.append("check", state="build-remote", rung=name, runner=host, ok=r["ok"], seconds=r.get("seconds"))
    if r["ok"] and key:
        _build_result_put(key, (_lines(src, "rev-parse", "HEAD") or [""])[0])
    return {"ok": r["ok"], "skipped": False, "results": [r]}



def daily_builds(root, cfg: Config) -> list[tuple[str, dict | None]]:
    """#6390 (owner 2026-11-07): what the build rung never compiles (the iOS app, the Swift test target), built once a day on
    `[check].build_remote` from the stable tree at the loop's checkout, each with its own derived data there, under the same
    locks; a green key is reused. None for a name = it could not run there (down, or a red that names no Swift source).
    Never on this Mac (the owner's): no remote = nothing runs."""
    if not cfg.build_remote:
        return []
    out = []
    for name, argv in cfg.daily_builds.items():
        r = _remote_build(root, cfg, tuple(argv), name)
        out.append((name, None if r and r.get("remote_env_red") else r))  # could not run there: as before
    return out

BUILD_YIELD_S = 2.0  # a lane's build rung that took the build lock while a train waits for it lets go and tries again this much later


def _train_waiting(lp: Path) -> bool:
    """A train of a live process waits for the build lock (its `<lock>.train-<pid>-<thread>` file); a dead process's file is removed."""
    for w in lp.parent.glob(lp.name + ".train-*"):
        try:
            os.kill(int(w.name.rsplit(".train-", 1)[1].split("-")[0]), 0)
            return True
        except (ValueError, ProcessLookupError):
            w.unlink(missing_ok=True)
        except PermissionError:
            return True
    return False


@contextlib.contextmanager
def build_lock(cfg: Config, train: bool | None = None):
    """local.train.build-lock-first: `[check].build_lock` held for one build. A merge train's build (its rung key starts `train `) says it
    waits first, so a lane's build rung that gets the lock meanwhile lets go at once and tries again: the train takes the next turn."""
    if not cfg.build_lock:
        yield
        return
    lp = Path(os.path.expanduser(cfg.build_lock))
    lp.parent.mkdir(parents=True, exist_ok=True)
    train = str(_KEY[0]).startswith("train ") if train is None else train
    with open(lp, "a") as f:
        if train:
            want = lp.with_name(f"{lp.name}.train-{os.getpid()}-{threading.get_ident()}")
            want.write_text(str(_KEY[0]))
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
            finally:
                want.unlink(missing_ok=True)
        else:
            said = False
            while True:
                fcntl.flock(f, fcntl.LOCK_EX)
                if not _train_waiting(lp):
                    break
                fcntl.flock(f, fcntl.LOCK_UN)
                if not said:
                    said = True
                    journal.append("check", state="build-lock-yield", rung="build", detail="a merge train waits for the build lock: it builds first")
                time.sleep(BUILD_YIELD_S)
        yield


def build_lock_free(cfg: Config) -> bool:
    """No build holds `[check].build_lock` now (local.train.second-train-on-the-first: a second train starts only then)."""
    if not cfg.build_lock:
        return True
    lp = Path(os.path.expanduser(cfg.build_lock))
    if not lp.exists():
        return True
    with open(lp, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
    return not _train_waiting(lp)


@_heavy("xcodebuild (the build rung)")
def _build_locked(root, changed: list[str], cfg: Config) -> dict:
    with build_lock(cfg):  # ~ = the owner's own state dir (review 1 N3); the owner's process takes it, the build itself runs jailed
        src = _stable_build_tree(root, cfg) if cfg.build_tree else str(root)
        key = _build_key(src, cfg)
        if key and (hit := _build_results().get(key)):  # the same fichero/ tree, command and Xcode built green before: reused
            journal.append("check", state="build-reused", rung="build", detail=f"green at {hit.get('head', '?')[:9]} {hit.get('ts', '')}: {key[:12]}")
            return {"ok": True, "skipped": False, "results": [{"name": "build", "ok": True, "exit_code": 0, "timed_out": False, "seconds": 0,
                                                               "stdout_tail": f"reused: the same build key built green at {hit.get('head', '?')[:9]}", "stderr_tail": "", "reused": key}]}
        log = journal.STATE / "build-logs" / f"build-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**9:09d}.log"  # only a red build writes it; ponytail: never rotated, prune by age if the dir grows
        r = _run("build", cfg.build, src, cfg.build_timeout_s, cfg, log=log)
        if not r["ok"] and BUILD_DB_LOCKED.search((r.get("stdout_tail") or "") + (r.get("stderr_tail") or "") + (r.get("errors") or "")):
            journal.append("check", state="retry", rung="build", detail="XCBuildData build.db was locked by another build in the same derived dir: re-run once")
            time.sleep(BUILD_RETRY_WAIT_S)
            r = {**_run("build", cfg.build, src, cfg.build_timeout_s, cfg, log=log.with_suffix(".retry.log")), "retried": True}
        if not r["ok"] and not r.get("timed_out") and cfg.build_tree and (dd := _derived_dir(cfg)) and not SOURCE_ERROR.search(r.get("errors") or ""):
            # an incremental red can be stale build state, not the code (memory: a stale incremental build): once more from a
            # clean derived dir, and the second result stands (manager 2026-11-03)
            journal.append("check", state="retry", rung="build", detail=f"an incremental build was red: {dd} cleared, built once more from clean")
            _clear_dir(dd)
            r = {**_run("build", cfg.build, src, cfg.build_timeout_s, cfg, log=log.with_suffix(".clean.log")), "retried": "clean"}
        if r["ok"] and key:
            _build_result_put(key, (_lines(src, "rev-parse", "HEAD") or [""])[0])
    return {"ok": r["ok"], "skipped": False, "results": [r]}




ROUTE_KEY = re.compile(r"^(GET|POST|PUT|PATCH|DELETE) (/\S*)$")
REASON_REF = re.compile(r"#\d+|\b[Ss]tep \d")


def known_gaps_added_only(repo, since: str, head: str, f: str, cfg: Config) -> str:
    """`guard-data-added-routes`: '' when `f` (a *_known_gaps.json of route keys) only gains entries whose key is a route in
    `[check].routes_file` at head and whose reason names an issue or a step; otherwise why not (the stop stays the manager's)."""
    if not f.endswith("_known_gaps.json") or not cfg.routes_file:
        return "not a known-gaps file, or no [check].routes_file"
    try:
        old = json.loads("\n".join(_lines(repo, "show", f"{since}:{f}") or ["x"]))
        new = json.loads("\n".join(_lines(repo, "show", f"{head}:{f}") or ["x"]))
        api = json.loads("\n".join(_lines(repo, "show", f"{head}:{cfg.routes_file}") or ["x"]))
    except ValueError:
        return "a file did not read as JSON at one of the heads"
    if not (isinstance(old, dict) and isinstance(new, dict)) or any(not ROUTE_KEY.match(k) for k in old):
        return "not a dict keyed by routes"
    if removed := [k for k in old if k not in new]:
        return f"removes {removed[:3]}"
    if edited := [k for k in old if new[k] != old[k]]:
        return f"changes the text of {edited[:3]}"
    routes = {(m.upper(), p) for p, ops in (api.get("paths") or {}).items() for m in (ops or {})}
    for k in [k for k in new if k not in old]:
        m = ROUTE_KEY.match(k)
        if not m or (m.group(1), m.group(2)) not in routes:
            return f"{k!r} is not a route of the engine at head"
        if not isinstance(new[k], str) or not REASON_REF.search(new[k]):
            return f"{k!r} gives no issue (#N) or step in its reason"
    return ""

def _stable_build_tree(root, cfg: Config) -> str:
    """`[check].build_tree`: ONE worktree of the engine repo at a fixed path (the jail's workroot), checked out at the scratch
    tree's head and cleaned, so xcodebuild's records (absolute paths) match the last build and it compiles only what changed
    (2026-11-03: every ladder built in a new path, median 8.5 min for any change). Only the build rung and build-check use it,
    under the build and heavy locks; never the owner's own Xcode derived data."""
    sha = (_lines(root, "rev-parse", "HEAD") or [""])[0]
    common = (_lines(root, "rev-parse", "--path-format=absolute", "--git-common-dir") or [""])[0]
    repo = str(Path(common).parent) if common.endswith("/.git") else common
    tree = Path(cfg.build_tree)
    if not (tree / ".git").exists():
        tree.parent.mkdir(parents=True, exist_ok=True)
        _git(repo, "worktree", "prune")
        r = _git(repo, "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach", "-q", str(tree), sha, timeout_s=SCRATCH_CHECKOUT_S)
        if not r["ok"]:
            raise RuntimeError(f"build tree failed: {r['stderr_tail']}")
        os.chmod(tree, 0o755)
    else:
        for args in (("-c", "core.hooksPath=/dev/null", "checkout", "-q", "--detach", "-f", sha), ("clean", "-fdxq")):
            r = _git(str(tree), *args)
            if not r["ok"]:
                raise RuntimeError(f"build tree {' '.join(args[-3:])} failed: {r['stderr_tail']}")
    return str(tree)


def _derived_dir(cfg: Config) -> str:
    """The build's `-derivedDataPath`, only when it lies under the build tree's own parent (the jail's workroot): never a path
    the owner's Xcode or app uses, never one a clear could reach outside the workroot. '' = no clean retry."""
    b = list(cfg.build)
    d = b[b.index("-derivedDataPath") + 1] if "-derivedDataPath" in b[:-1] else ""
    if not d or not cfg.build_tree:
        return ""
    root = Path(cfg.build_tree).resolve().parent
    return d if Path(d).resolve().is_relative_to(root) and Path(d).resolve() != root else ""


def _clear_dir(d: str) -> None:
    """The derived dir's contents removed, as the jail user who wrote them (the dir itself stays)."""
    run_command("clean-derived", ["/bin/sh", "-c", f'rm -rf "{d}"/* "{d}"/.[!.]* 2>/dev/null; true'], "/", 600)


_XCODE: list = []


def _build_key(tree, cfg: Config, cmd: tuple = ()) -> str:
    """What a build reads: the tree hash of each [check].build_paths dir, the build command, and the Xcode version. A harness
    change never reuses a Swift result across a different tree hash; '' = no key (nothing is reused)."""
    trees = [(_lines(tree, "rev-parse", f"HEAD:{p.rstrip('/')}") or [""])[0] for p in cfg.build_paths]
    if not all(trees):
        return ""
    if not _XCODE:
        try:
            _XCODE.append(subprocess.run(["xcodebuild", "-version"], capture_output=True, text=True, timeout=60).stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            _XCODE.append("")
    return hashlib.sha256(json.dumps([trees, list(cmd or cfg.build), _XCODE[0]]).encode()).hexdigest()


def _build_results() -> dict:
    f = journal.STATE / "build-results.json"
    try:
        return json.loads(f.read_text()) if f.is_file() else {}
    except ValueError:
        return {}


def _build_result_put(key: str, head: str) -> None:
    """A GREEN build's key, owner-side (a red never counts from the cache: it always builds). Kept to the last 200."""
    with journal.Lock("build-results"):
        d = _build_results()
        d[key] = {"head": head, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        f = journal.STATE / "build-results.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(list(d.items())[-200:])))
        tmp.replace(f)

def _git_argv(root, args) -> list[str]:
    """git with hooks, fsmonitor, every filter driver and external diff the repo's own config names switched off
    (review 2 B2: a worker's .git/config must run no code at checkout or diff)."""
    r = subprocess.run(["git", "config", "--local", "--name-only", "--get-regexp", r"^filter\."], cwd=str(root),
                       capture_output=True, text=True, env=_git_env())
    names = {k.split(".")[1] for k in r.stdout.split() if k.count(".") >= 2}
    off = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "diff.external=",
           "-c", "core.attributesFile=/dev/null", "-c", "safe.directory=*"]  # #6507: the jail user's tree, read as the owner with the global config off
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


CHECK_LINE = re.compile(r"\bassert\b|\braises\(|\bfail\(")
TEST_DEF = re.compile(r"^\s*(?:async )?def test_\w+")


def pure_moves(root, since: str, head: str) -> dict[str, str]:
    """{new path: old path} of each file the range renames with its content unchanged (`git diff -M100%`: R100 only); {} on failure.
    A moved test passes on base where its old copy already runs: that proves nothing and owes nothing (`red-on-base-pure-move`)."""
    out = {}
    for ln in _lines(root, "diff", "-M100%", "--name-status", "--diff-filter=R", f"{since}...{head}") or []:
        parts = ln.split("\t")
        if len(parts) == 3 and parts[0] == "R100":
            out[parts[2]] = parts[1]
    return out


def trim_only(root, since: str, head: str, f: str) -> bool:
    """`red-on-base-trim-only`: a test file on base whose diff adds no check line (assert, raises, fail) and no new test
    function (as many `def test_` added as removed: a rename) can only have lost checks, so it proves nothing on base either way."""
    if not _git(root, "cat-file", "-e", f"{since}:{f}")["ok"]:
        return False  # a new file is never trim-only
    diff = _lines(root, "diff", "--no-ext-diff", "--unified=0", f"{since}...{head}", "--", f)  # diff.external= is off: a patch needs --no-ext-diff
    if diff is None:
        return False  # unreadable: fail closed, the red stays owed
    added = [ln[1:] for ln in diff if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln[1:] for ln in diff if ln.startswith("-") and not ln.startswith("---")]
    return (not any(CHECK_LINE.search(a) for a in added)
            and sum(bool(TEST_DEF.match(a)) for a in added) <= sum(bool(TEST_DEF.match(r)) for r in removed))


TIMEOUT_NUM = re.compile(r"(\btimeout\w*\s*=\s*|\.timeout\(\s*)\d+(?:\.\d+)?")
TIMEOUT_LINE = re.compile(r"^\s*@pytest\.mark\.timeout\([^)]*\)\s*(#.*)?$")
COMMENT_LINE = re.compile(r"^\s*(#.*)?$")


def timeout_only(root, since: str, head: str, f: str) -> bool:
    """`red-on-base-timeout-only`: a test file on base whose every changed line is a comment, a whole `@pytest.mark.timeout(...)` line,
    or the same line with only its timeout numbers changed. Anything else (a new assert, a call, a changed argument) keeps the red."""
    if not _git(root, "cat-file", "-e", f"{since}:{f}")["ok"]:
        return False  # a new file is never timeout-only
    diff = _lines(root, "diff", "--no-ext-diff", "--unified=0", f"{since}...{head}", "--", f)
    if diff is None:
        return False  # unreadable: fail closed
    # per hunk, in order, indentation kept (review 106: sorted and stripped, a moved or re-indented assert read as timeout-only)
    hunks: list[tuple[list[str], list[str]]] = []
    for ln in diff:
        if ln.startswith("@@"):
            hunks.append(([], []))
        elif hunks and ln.startswith("-") and not ln.startswith("---"):
            hunks[-1][0].append(ln[1:])
        elif hunks and ln.startswith("+") and not ln.startswith("+++"):
            hunks[-1][1].append(ln[1:])

    def norm(lines):
        return [TIMEOUT_NUM.sub(r"\1N", ln).rstrip() for ln in lines if not (COMMENT_LINE.match(ln) or TIMEOUT_LINE.match(ln))]
    return bool(hunks) and all(norm(old) == norm(new) for old, new in hunks)


def deleted_modules(root, since: str, head: str, cfg: Config) -> set[str]:
    """The DOTTED module paths of non-test Python files this diff deletes: repo-relative and relative to each [check].python_path
    root (`fichero-builder/fichero_builder/watch.py` is `fichero_builder.watch`), never a bare file name (review -72: a deleted
    `api/routes/ai/models.py` must not excuse tests of `fichero_builder.models`)."""
    out = set()
    for _s, _m, f in _changes(root, since, head, "--diff-filter=D"):
        if not f.endswith(".py") or any(fnmatch.fnmatch(Path(f).name, g) for g in cfg.test_globs):
            continue
        out.add(f[:-3].replace("/", "."))
        for r in cfg.python_path:
            if f.startswith(r.rstrip("/") + "/"):
                out.add(f[len(r.rstrip("/")) + 1:-3].replace("/", "."))
    return out


def _bindings(tree) -> dict:
    """{name the file binds: the full dotted module it is}, for `import m`, `import a.b as m`, `from a.b import m [as y]`; a relative
    import or `import a.b` (which binds only `a`) maps to no module, so it never matches a deleted one."""
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.asname:
                    out[a.asname] = a.name
                elif "." not in a.name:
                    out[a.name] = a.name
        elif isinstance(n, ast.ImportFrom) and not n.level and n.module:
            for a in n.names:
                out[a.asname or a.name] = f"{n.module}.{a.name}"
    return out


def _uses(fn, bound: dict) -> set:
    """The full dotted modules a function calls through `m.<attr>` (a local variable named like a module is not the module)."""
    return {bound[x.value.id] for x in ast.walk(fn) if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id in bound}


def weakened_by_a_deleted_module(root, since: str, head: str, f: str, gone: set[str]) -> bool:
    """`weakened-tests-of-a-deleted-module`, kept narrow on purpose (reviews -63, -65, -67: every counting rule had a way round it):
    a changed test file is excused only when its head IS its base with whole top-level test functions removed, each of which called
    a module this diff deletes (imports may change); a deleted test file only when every test in it called one. A cut inside a
    surviving test, any change to a class, a helper or a marker, or anything else: refused as before, for the manager."""
    if not gone:
        return False
    try:
        old = ast.parse("\n".join(_lines(root, "show", f"{since}:{f}") or []))
        alive = _git(root, "cat-file", "-e", f"{head}:{f}")["ok"]
        new = ast.parse("\n".join(_lines(root, "show", f"{head}:{f}") or [])) if alive else None
    except SyntaxError:
        return False
    imported = _bindings(old)
    if new is None:
        tests = [n for n in ast.walk(old) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
        return bool(tests) and all(_uses(n, imported) & gone for n in tests)
    is_test = lambda n: isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")  # noqa: E731
    kept = {n.name for n in new.body if is_test(n)}
    removed = [n for n in old.body if is_test(n) and n.name not in kept]
    body = lambda tree, drop=(): [ast.dump(n) for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom)) and n not in drop]  # noqa: E731

    def names(tree) -> set:  # every imported name with what it is bound to: an `import mod` swapped for a mock is a change (review -70)
        return {(type(n).__name__, getattr(n, "module", None) or "", a.name, a.asname or "") for n in tree.body
                if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    dropped = {x for x in names(old) - names(new) if (f"{x[1]}.{x[2]}" if x[0] == "ImportFrom" else x[2]) in gone}  # only the deleted module's own import may go
    imports_ok = names(new) == names(old) - dropped
    return bool(removed) and imports_ok and all(_uses(n, imported) & gone for n in removed) and body(new) == body(old, removed)


def _MINE_ROOTS() -> set:
    if not hasattr(_MINE, "roots"):
        _MINE.roots = set()
    return _MINE.roots


def _in_thread(shipped: set, key: str, fn, *a, slot: int = 0):
    """`fn` in a helper thread: the remote copies it ships are recorded in `shipped`, for the calling ladder's thread to drop."""
    _MINE.roots = shipped
    _KEY[0] = key  # the ladder's key: cancel_requested() reads it, so a superseded check stops this run too
    SLOT[0] = slot  # the ladder's runner order
    return fn(*a)


def red_on_base(root, since: str, head: str, files: list[str], cfg: Config = Config(), timeout_s: float = 1800,  # noqa: B008
                head_tree=None, also_green: tuple = (), approve_red: bool | tuple = False) -> dict:
    """The failing run: each changed test file, copied onto a scratch tree at `since`, must FAIL there on its
    own, and all must PASS at `head`. A test that passes on base proves nothing."""
    root = Path(root)

    approved: list[str] = []
    not_red: list[str] = []  # every file that passes on base goes in ONE alert (2026-11-25, app-bugs nightly-green-1: three files,
    # three approves at one head, a ladder each, because the rung stopped at the first)

    def red(msg: str) -> dict | None:  # the manager's approve (an alert) records the refusal and goes on to the green run
        # True: every refusal; a tuple: only one naming an approved test file (an approve binds to the tests its alert named)
        # 2026-11-22: a refusal naming no test file ("no test file changed", a red run naming only a report) is excused by any
        # approve at this head; a tuple of files only narrows refusals that name files (kg-conf conf-2 looped on the same sha)
        names_a_test = bool(re.search(r"[\w./-]+\.py\b", msg))
        if approve_red is True or (isinstance(approve_red, tuple) and (not names_a_test or any(t in msg for t in approve_red))):
            approved.append(msg)
            return None
        return {"name": "red-on-base", "argv": [], "exit_code": 1, "ok": False, "timed_out": False, "seconds": 0,
                "stdout_tail": "", "stderr_tail": msg + "\nneeds-approval"}
    if not files and (r := red("no test file changed: a source change needs a test (red on base, green on the branch)")):
        return r
    sha = _git(root, "rev-parse", head)["stdout_tail"].strip()  # `HEAD` inside the scratch tree would be `since`
    base = _mkdtemp("check-base-tree-", readable=True)
    # the head's green run and the base runs go at once, each from its own shipped copy (its own gate dir): 2026-11-24 throughput
    # review, the two ran in a row. The base runs take the runners after the head run's (_runners_for_base); one runner's heavy lock
    # still lets one pytest at a time there.
    # The pool's exit waits for the head run, so a refusal returns with no run left going.
    shipped = _MINE_ROOTS()  # the head thread records its remote copies here: this thread's set, dropped when the ladder ends
    pool = ThreadPoolExecutor(max_workers=1)
    here_f = pool.submit(_in_thread, shipped, _KEY[0], green_runs, head_tree or root, files, also_green, cfg, timeout_s, slot=SLOT[0]) if files or also_green else None
    try:
        r0 = _git(root, "worktree", "add", "--detach", "-q", base, since, timeout_s=SCRATCH_CHECKOUT_S)
        if not r0["ok"]:  # infra, never a code verdict: an approve would skip the proof (manager 2026-11-07, alert 416)
            why = r0["stderr_tail"].strip() or (f"timed out after {SCRATCH_CHECKOUT_S:g} s" if r0.get("timed_out") else f"exit {r0.get('exit_code')}")
            raise RuntimeError(f"scratch tree failed: could not make the base tree at {since[:9]}: {why}")
        _git(base, "checkout", sha, "--", *files)  # a new file is not on base; checkout still copies it
        have = already_built_files(root, since, head, cfg)  # a proving test of a behaviour already there passes on base by design
        data_skipped: set[str] = set()
        moved = pure_moves(root, since, head) if "red-on-base-pure-move" in cfg.auto else {}
        for f in files:
            if f in moved:  # 2026-11-25, app-bugs nightly-green-1 (alert 1932): 11 tests moved whole into the mirroring folder
                journal.append("auto", rule="red-on-base-pure-move", head=sha, file=f, detail=f"a pure move of {moved[f]} (R100): passing on base is expected; it runs green on head")
                data_skipped.add(f)  # like data-only: a source change still owes a red from some other test
                continue
            if f not in have and data_only(root, since, head, f):
                data_skipped.add(f)
                continue  # its tests are base's own; it runs in the green run
            if f not in have and "red-on-base-trim-only" in cfg.auto and trim_only(root, since, head, f):
                journal.append("auto", rule="red-on-base-trim-only", head=sha, file=f, detail="adds no check and no new test: no red owed; it runs green on head")
                data_skipped.add(f)  # like data-only: a source change still owes a red from some other test
                continue
            if f not in have and "red-on-base-timeout-only" in cfg.auto and timeout_only(root, since, head, f):
                journal.append("auto", rule="red-on-base-timeout-only", head=sha, file=f, detail="only timeout numbers, timeout marks or comments changed: no red owed; it runs green on head")
                data_skipped.add(f)
                continue
            BASE_RUN[0] = True
            try:
                r = pytest_rung(base, [f], cfg, timeout_s)
            finally:
                BASE_RUN[0] = False
            if f in have and not r["ok"] and (x := red(f"{f} says Already built but fails on base at {since[:9]}: it owes a red like any test")):
                return x
            if f not in have and r["ok"]:
                # 2026-11-06 (lane-sharing batch-27): a NOT RED that did not reproduce, and nothing said where or how the base ran: the
                # refusal names the runner, the base tree and pytest's last lines, and one `red-on-base-base` row keeps the whole tail
                where = r.get("remote") or "here"
                tail = " | ".join(ln.strip() for ln in (r.get("stdout_tail") or "").splitlines() if ln.strip())[-300:]
                journal.append("red-on-base-base", head=sha, since=since, file=f, runner=where, tree=base, stdout_tail=(r.get("stdout_tail") or "")[-3000:])
                if x := red(f"NOT RED ON BASE: {f} passes at {since[:9]}, so it proves nothing (base ran on {where}, tree {base}: {tail})"):
                    not_red.append(x["stderr_tail"].removesuffix("\nneeds-approval"))
        if not_red and (x := red("\n".join(not_red))):  # each line names an unapproved file: still refused
            return x
        changed = _lines(root, "diff", "--name-only", f"{since}...{head}") or []
        source = [n for n in changed if not any(fnmatch.fnmatch(Path(n).name, g) for g in cfg.test_globs) and (not cfg.red_paths or n.startswith(cfg.red_paths))]
        if source and files and set(files) <= have | data_skipped and (x := red(
                f"{source[0]} changed and every changed test says Already built" + (" or changes only module data" if data_skipped else "")
                + ": the change owes a red")):
            return x  # a data-only edit to an existing test excuses no source change (review 2026-11-02)
        here = here_f.result() if here_f else _skipped("red-on-base")
        return {**here, "name": "red-on-base", **({"stdout_tail": "approved by the manager: " + "; ".join(approved) + "\n" + here.get("stdout_tail", "")} if approved else {})}
    finally:
        pool.shutdown(wait=True)
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


class _PerThread(threading.local):
    """A one-slot list of its own in each thread: two ladders run at once in the loop's chain threads (speed 3)."""

    def __init__(self, v=None):
        self.v = [v]

    def __getitem__(self, i):
        return self.v[i]

    def __setitem__(self, i, x):
        self.v[i] = x


HEAD_GREEN_ONLY = _PerThread(False)  # a kept rebase: red-on-base runs only its head-green half (the base run stood on the old base)
SKIP_RUNGS = _PerThread(())  # rung names this thread's ladder does not run: the merge train runs them once per train (work.do_check sets it)
ON_RUNG = _PerThread(None)  # (name, ok, rungs so far) after each rung: the chain starts the review early (speed 2)
ACTIVITY = _no_activity  # `builder check` and the chain set this to a journal writer (console view A); tests write nowhere
BASE_RUN = _PerThread(False)  # this thread runs red-on-base's base tests: _run takes the runners after the head run's
_KEY = _PerThread("")  # the running ladder's key, for its rung rows
HELD: set = set()  # the ladder slots held in this process now (work.ladder_slot adds and removes them): whose runner is busy
RED_STOOD: set = set()  # ladder keys whose retried red stood on another runner: the reds are the code's, so no more retries in that ladder
SLOT = _PerThread(0)  # this thread's ladder slot (0 = `ladder`, 1 = `ladder-2`, ...): its first runner (_runners_for_slot); work.ladder_slot sets it
REUSE = _PerThread(None)  # {rung name: its green row} from the SAME head, base and pinned copy: an approve resumes there, it does not start over



def _load() -> float | None:
    """The 1-minute load average, rounded; None where the OS has none."""
    try:
        return round(os.getloadavg()[0], 1)
    except OSError:
        return None

# ---- the perf and security rungs (#6600, Step 2.30): readers and judges are perf_rung.py and security_rung.py, the figures and
# findings are the tools', the decision rule is scripts/perf_trial.py's. REPORT-ONLY until real batches have measured the budget
# (`[check.perf].enforce` / `[check.security].enforce` = false): a red is shown, journalled as an alert, and the rung stays green.
PERF_MISSING = re.compile(r"No such file or directory: '?((?:\./)?(?:scripts/perf_baseline\.json|(?:fichero-server/)?tests/perf[^\s':]*))")
PERF_LINE = re.compile(r"^PERF-RESULT (\{.*\})\s*$", re.M)
SECURITY_LINE = re.compile(r"^SECURITY-RESULT (\{.*\})\s*$", re.M)
# the scanned directories are the project's: `[check.security].dirs` in harness.toml
WAIVER_RE = r"#[[:space:]]*nosec|nosemgrep"
APPROVED_LABEL = "security-waiver-approved"


def _rung_alert(name: str, detail: str) -> None:
    """A rung's alert, in the queue's shape (id, lane `harness`, step `rung-<name>`, what) so the console can answer it (#6589: 69
    id-less rows could never be dismissed). One open alert per rung and text: a check that says the same again adds nothing."""
    rows = journal.read()
    answered = {r.get("id") for r in rows if r.get("event") == "alert-answer" and r.get("ok")}
    step, what = f"rung-{name}", detail[:300]
    if any(r.get("event") == "alert" and r.get("step") == step and r.get("what") == what and r.get("id") not in answered for r in rows):
        return
    n = sum(1 for r in rows if r.get("event") == "alert") + 1
    journal.append("alert", id=f"harness-{step}-{n}", lane="harness", step=step, what=what, evidence="", actions=["dismiss"],
                   rung=name, detail=what)


def _report_only(name: str, cfg_table: dict, ok: bool, lines: list[str], extra: dict | None = None) -> dict:
    """A rung row. Enforcing, a red is red; report-only, it stays green and says what it would have said, and an alert row is journalled.
    The perf rung is red whenever it measured nothing (REFUSED / not-run lines), enforcing or not."""
    enforce = bool(cfg_table.get("enforce", False))
    if not ok and not enforce:
        _rung_alert(name, f"{name} (report-only) would be red: " + "; ".join(lines))
    refused = any(x.startswith(("REFUSED", "not run", "not-run")) for x in lines)  # a refused rung measured nothing: "not run", never green
    missing = refused and name == "perf"  # #6600: report-only forgives a slow figure, never a missing one: a perf run that measured nothing is red
    return {"ok": (ok or not enforce) and not missing, "skipped": False, "enforced": enforce, "stdout_tail": "\n".join(lines)[-3500:], "stderr_tail": "",
            "results": [], **({"not_run": True} if refused else {}), **(extra or {})}


def _timed_out_row(name: str, r: dict) -> dict | None:
    """A timeout is ONE `alert` row naming the rung, never a red (perf-method budget)."""
    if r.get("timed_out"):
        _rung_alert(name, f"{name} timed out after {r.get('seconds')} s: over twice its budget, not a red")
        return {"ok": True, "skipped": False, "stdout_tail": f"alert: the {name} rung timed out ({r.get('seconds')} s)", "stderr_tail": "", "results": [r]}
    return None


def _not_run(name: str, cfg_table: dict, reason: str, detail: str = "", extra: dict | None = None, also: list[str] = ()) -> dict:
    """A rung that measured nothing: `not-run: <reason>` with the remote stderr, a journal row (state not-run, an id) and never green
    (`perf-sweep.rung.not-run-is-visible`); the ladder still passes while `enforce` is off."""
    detail = (detail or "").strip()[-300:]
    rid = f"{name}-not-run-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"  # unique without reading the journal
    journal.append("check", state="not-run", rung=name, id=rid, reason=reason, detail=detail)
    return {**_report_only(name, cfg_table, False, [f"not-run: {reason}", *([detail] if detail else []), *also], extra), "not_run": True, "not_run_id": rid}


def _perf_engine(root, since: str, changed: list[str], cfg: Config) -> dict:
    """The engine half of the perf rung: `scripts/perf_engine_run.py` (pytest-benchmark under pyinstrument and /usr/bin/time -l, du before
    and after) on `[check].build_remote`, NEVER on this Mac, then its figures judged against scripts/perf_baseline.json by perf_trial.
    Skipped as "not required" for a batch with no engine path; skipped as not configured with no `[check.perf]` or no build_remote."""
    from . import perf_rung
    if not cfg.perf:
        return {"ok": True, "skipped": True, "stdout_tail": "skipped: not configured", "results": []}
    if why := perf_rung.required(changed):
        return {"ok": True, "skipped": True, "stdout_tail": why, "stderr_tail": "", "results": []}
    if not cfg.build_remote:
        return {"ok": True, "skipped": True, "stdout_tail": "not run: no [check].build_remote (a measurement never runs on the manager's Mac)", "stderr_tail": "", "results": []}
    py = _gate_python(cfg, GATE)  # the gate venv beside the build tree (resolved on the runner)
    argv = (py, "scripts/perf_engine_run.py", "--baseline", perf_rung.BASELINE, *cfg.perf.get("args", ()))
    r = _remote_build(root, cfg, argv, "perf", reuse=False)
    if r is None:
        return _not_run("perf", cfg.perf, "runner down", "the build runner is unreachable: the engine perf rung did not run (never run here)")
    row = r["results"][0]
    if r.get("crashed") or r.get("remote_env_red"):
        tail = (row.get("stderr_tail") or row.get("stdout_tail") or "")[-300:]
        if (m := PERF_MISSING.search(tail)) and "No module named" not in tail:
            reason = f"{m.group(1)} missing on the runner"
        else:
            reason = "perf tool refused"
        return _not_run("perf", cfg.perf, reason, f"{r.get('remote')} exit {row.get('exit_code')}: {tail}", {"results": [row]})
    if (t := _timed_out_row("perf", row)) is not None:
        return t
    m = PERF_LINE.search(row.get("stdout_tail") or "")
    if not m:
        return _report_only("perf", cfg.perf, False, ["REFUSED: the perf run printed no PERF-RESULT line (a gate that cannot read its input fails)",
                                                       (row.get("stderr_tail") or "")[-300:]], {"results": [row]})
    res = json.loads(m.group(1))
    if res.get("void"):  # a busy or throttled machine: neither pass nor fail, an alert row for a person (not a red)
        _rung_alert("perf", f"perf run {res['void']}")
    lines = [*res.get("reds", []), *[f"finding: new own frame in the top ten: {f}" for f in res.get("findings", [])],
             *[f"falls: {f}" for f in res.get("falls", [])], *[f"change: {c}" for c in res.get("changes", [])],
             *[f"recorded (report-only, commit to scripts/perf_baseline.json): {k} = {v['median']:g}" for k, v in (res.get("recorded") or {}).items()], *([res["void"]] if res.get("void") else []), *res.get("notes", [])]
    return _report_only("perf", cfg.perf, bool(res.get("ok")), lines or ["engine perf: every figure within its tolerance"], {"results": [row]})


def _perf_swift(root, cfg: Config) -> dict:
    """The Swift half of the perf rung (#6600): `[check.perf].swift_test` run under `/usr/bin/time -l` on `[check].build_remote` (never here),
    recording wall seconds and the largest process's peak RSS. No `swift_test` is a "no workload yet" row and one alert a day; a run that
    exits non-zero or prints no readable figure is REFUSED."""
    from . import perf_rung
    test = cfg.perf.get("swift_test")
    if not test:
        msg = "Swift perf: no workload yet (#6600)"
        _rung_alert("perf", f"{msg} {time.strftime('%Y-%m-%d')}")
        return {"ok": True, "skipped": False, "not_run": True, "stdout_tail": msg, "stderr_tail": "", "results": []}
    if not cfg.build_remote:
        return _not_run("perf", cfg.perf, "no build_remote", "Swift perf never runs on the manager's Mac")
    argv = ("/usr/bin/time", "-l", *cfg.build[:-1], f"-only-testing:{test}", "test")
    r = _remote_build(root, cfg, argv, "perf", reuse=False)
    if r is None:
        return _not_run("perf", cfg.perf, "runner down", "the build runner is unreachable: the Swift perf rung did not run (never run here)")
    row = r["results"][0]
    if (t := _timed_out_row("perf", row)) is not None:
        return t
    text = row.get("stderr_tail") or ""
    real = re.search(r"^\s*([\d.]+)\s+real\b", text, re.M)
    try:
        if row.get("exit_code") != 0 or not real:
            raise ValueError(f"exit {row.get('exit_code')}, " + ("no `real` line" if not real else "the test failed"))
        mb = perf_rung.read_peak_rss_mb(text)
    except ValueError as e:
        return _report_only("perf", cfg.perf, False, [f"REFUSED: the Swift perf run for {test} measured nothing ({e})", text[-300:]], {"results": [row]})
    line = f"Swift perf: {test} {float(real.group(1)):g} s, peak {mb:.0f} MB (the largest process /usr/bin/time saw)"
    return _report_only("perf", cfg.perf, True, [line], {"results": [row]})


def unit(root, changed: list[str], cfg: Config, tests_run_elsewhere: bool = True, everything: bool = False) -> dict:
    """The unit rung (speed-tests-1): the tests this batch can affect (`affected.select`: the importers of every changed source file, the
    changed tests, `[check].always_tests`), or the whole suite when a change cannot be placed. A changed test file already ran in
    red-on-base (`tests_run_elsewhere`) and is not run twice, unless the whole suite runs. The nightly `verify-all --full` runs everything.
    Journals how many test files ran, how many tests passed, and why. Off with no `[check].always_tests`. `everything`: the whole suite
    (the merge train's unit tier, once per train)."""
    from . import affected
    if not cfg.always_tests:
        return {"ok": True, "skipped": True, "stdout_tail": "skipped: no [check].always_tests", "results": []}
    blobs = {row.partition("\t")[2]: row.split()[1] for row in _lines(root, "ls-files", "-s", "*.py") or []}  # "<mode> <blob> <stage>\t<path>"
    sel = ({"whole": "the merge train runs the full unit tier", "tests": [], "changed_tests": [], "always": []} if everything
           else affected.select(root, changed, blobs, cfg.test_globs, cfg.python_path, cfg.always_tests, journal.STATE))
    if sel["whole"]:
        whole = tuple(sorted({v for v in cfg.whole_tests.values() if isinstance(v, str)}))
        dirs = sorted(f"{p.parent.name}/tests" for p in Path(root).glob("*/tests") if p.is_dir() and f"{p.parent.name}/tests" not in whole)
        files, why = dirs, f"the whole suite: {sel['whole']}"
    else:
        whole = ()
        files = [t for t in sel["tests"] if not (tests_run_elsewhere and t in sel["changed_tests"])]
        why = f"{len(sel['tests'])} affected test files ({len(sel['changed_tests'])} changed, {len(sel['always'])} always-run)"
    if not files:
        journal.append("check", state="unit-selection", rung="unit", files=0, tests=0, why=why)
        return {"ok": True, "skipped": True, "stdout_tail": f"not required: {why}, none left to run here", "stderr_tail": "", "results": []}
    r = green_runs(root, files, whole, cfg, 1800)
    n = sum(int(m.group(1)) for x in r.get("runs", []) for m in [re.search(r"(\d+) passed", x.get("stdout_tail") or "")] if m)
    journal.append("check", state="unit-selection", rung="unit", files=len(files), tests=n, why=why, ok=r["ok"])
    return {**r, "stdout_tail": f"unit: ran {len(files)} test files, {n} tests passed; {why}\n" + (r.get("stdout_tail") or "")}


UI_VIEW_PATH = "fichero/fichero/Views/Preview"
UI_GREENS_NEEDED = 3


def ui_required(changed: list[str]) -> bool:
    """A batch that changes Swift under Views/Preview or a Swift file named for a segment."""
    return any(f.endswith(".swift") and (f.startswith(UI_VIEW_PATH) or "Segment" in Path(f).name) for f in changed)


def _ui_greens(ok: bool | None = None) -> int:
    """The consecutive green runs of the ui rung, kept in the state dir; `ok` records a run (a red resets it)."""
    f = journal.STATE / "ui-greens.json"
    try:
        n = int(json.loads(f.read_text()).get("greens", 0)) if f.is_file() else 0
    except ValueError:
        n = 0
    if ok is not None:
        n = n + 1 if ok else 0
        journal.STATE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"greens": n}))
    return n


def _ui_not_run(reason: str, detail: str = "") -> dict:
    """A ui rung that could not run: a NOT RUN row with its reason, never a red, enforcing or not."""
    journal.append("check", state="not-run", rung="ui", reason=reason, detail=detail[-300:])
    return {"ok": True, "skipped": False, "not_run": True, "stdout_tail": f"NOT RUN: {reason}" + (f"\n{detail[-300:]}" if detail else ""), "stderr_tail": "", "results": []}


def ui(root, changed: list[str], cfg: Config) -> dict:
    """One UI test pass per batch (speed-tests-1): `[check].ui_tests` (the segment editor's UI tests) on `[check].ui_runner` (default the
    build runner), the Mac with a logged-in GUI session, only when the batch changes the segment editor's Swift. Report-only
    (`[check.ui].enforce` false) until it has run green three times. No GUI session, or an unreachable runner, is NOT RUN, never red."""
    if not cfg.ui_tests:
        return {"ok": True, "skipped": True, "stdout_tail": "skipped: no [check].ui_tests", "results": []}
    if not ui_required(changed):
        return {"ok": True, "skipped": True, "stdout_tail": f"not required: no Swift under {UI_VIEW_PATH} or named Segment changed", "stderr_tail": "", "results": []}
    runner = cfg.ui_runner or cfg.build_remote
    if not runner:
        return _ui_not_run("no runner: neither [check].ui_runner nor [check].build_remote is set")
    host = runner.partition(":")[0]
    gui = _ssh(host, "launchctl print gui/$(id -u) >/dev/null 2>&1", 30)
    if gui.returncode == 255:
        return _ui_not_run(f"runner {host} unreachable", gui.stderr.decode(errors="replace"))
    if gui.returncode:
        return _ui_not_run(f"no logged-in GUI session for the ssh user on {host}")
    argv = (*cfg.build[:-1], *(f"-only-testing:{t}" for t in cfg.ui_tests), "test")
    r = _remote_build(root, replace(cfg, build_remote=runner), argv, "ui", reuse=False)
    if r is None:
        return _ui_not_run(f"runner {host} unreachable")
    row = r["results"][0]
    if r.get("remote_env_red"):
        return _ui_not_run(f"the UI tests could not run on {host} (not a test failure)", row.get("stderr_tail") or "")
    greens = _ui_greens(r["ok"])
    enforce = bool(cfg.ui.get("enforce", False))
    names = sorted(set(re.findall(r"Test [Cc]ase '([^']+)' failed", row.get("stdout_tail") or "")))
    lines = [f"ui: {len(cfg.ui_tests)} UI test filters on {host}: " + ("green" if r["ok"] else "RED " + ", ".join(names)) + f" ({greens}/{UI_GREENS_NEEDED} green runs before enforcing)"]
    if not r["ok"] and not enforce:
        _rung_alert("ui", "ui (report-only) would be red: " + lines[0])
    return {"ok": r["ok"] or not enforce, "skipped": False, "enforced": enforce, "stdout_tail": "\n".join(lines), "stderr_tail": "", "results": [row]}


# 2026-11-26 journal: 296 suites (1006 tests) took 921 and 858 s, the whole plan (5077 tests) 786 to 1246 s, 58 tests 181 s: about
# 140 s + 2.6 s a suite, so near 300 suites -only-testing costs what the whole plan does. ponytail: a fixed 150, from one day's runs;
# the `swift-tests` check rows now carry `suites`, so it can be set again from more of them.
SWIFT_SELECT_MAX = 150  # more suites than this: the whole plan runs
SWIFT_NEUTRAL = (".pbxproj", ".xcfilelist", ".md")  # project bookkeeping: the Swift files the change adds carry the selection
_SUITE = re.compile(r"^(?:@Suite\b[^\n]*\n)?(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:final|public|internal)\s+)*(?:struct|class|actor|enum)\s+(\w+)([^{\n]*)", re.M)


def _suites(text: str) -> list[str]:
    """The test suites a Swift test file declares at top level: a type named ...Test(s), an XCTestCase, or one marked @Suite."""
    out = []
    for m in _SUITE.finditer(text):
        name, rest = m.group(1), m.group(2)
        if name.endswith(("Tests", "Test")) or "XCTestCase" in rest or m.group(0).startswith("@Suite"):
            out.append(name)
    return out


def swift_affected(root, changed: list[str], cfg: Config, contract_types: set | None = None) -> list[str] | None:
    """The `<target>/<suite>` ids of the Swift test suites a diff can affect, the way `affected.select` picks Python tests: a changed
    test file's own suites; for any other changed Swift file, the suites of the test files named after its type or that name it.
    None = run the whole suite: no `[check].swift_test_target`, a changed non-Swift build input (a resource, a setting, a package
    pin), or more suites than SWIFT_SELECT_MAX. The nightly always runs the whole suite (owner 2026-11-26)."""
    if swift_whole_why(changed, cfg, contract_types is not None):
        return None
    built = _swift_built(changed, cfg)
    tests = {str(p.relative_to(root)): p for p in Path(root, cfg.swift_test_dir).rglob("*.swift")}
    texts: dict = {}

    def text(f: str) -> str:
        if f not in texts:
            try:
                texts[f] = tests[f].read_text(errors="replace")
            except OSError:
                texts[f] = ""
        return texts[f]
    picked: set[str] = set()
    for f in (x for x in built if x.endswith(".swift")):
        if f in tests:
            picked.add(f)
            continue
        stem = Path(f).stem.split("+")[0]
        word = re.compile(rf"\b{re.escape(stem)}\b")
        picked |= {t for t, p in tests.items() if p.stem.startswith(stem) or word.search(text(t))}
    if contract_types:  # an openapi.json change: the tests that name a type it changed (generated, so no Swift file of it is in the diff)
        words = re.compile(r"\b(" + "|".join(map(re.escape, sorted(contract_types))) + r")\b")
        picked |= {t for t in tests if words.search(text(t))}
    suites = sorted({f"{cfg.swift_test_target}/{n}" for t in picked for n in _suites(text(t))})
    return None if len(suites) > SWIFT_SELECT_MAX else suites


def _swift_built(changed: list[str], cfg: Config) -> list[str]:
    """The changed files the Swift build reads; a test plan other than the one `[check].swift_tests` runs is not one of them
    (2026-11-26: the iOS UI plan in a train's diff made its unit run the whole suite)."""
    plan = cfg.swift_tests[list(cfg.swift_tests).index("-testPlan") + 1] if "-testPlan" in cfg.swift_tests[:-1] else ""
    built = [f for f in changed if f.startswith(tuple(cfg.build_paths))] if cfg.build_paths else changed
    return [f for f in built if not (f.endswith(".xctestplan") and Path(f).stem != plan)]


CONTRACT_FILE = "openapi.json"  # the API client's generator input: mapped to the suites naming its changed types (contract_types)


def contract_types(repo, base: str, head: str, changed: list[str]) -> set | None:
    """The schema and operation names an `openapi.json` in `changed` adds, drops or changes between base and head: the generated
    client's types (Components.Schemas.<Name>, Operations.<operationId>). None = no contract file changed, or one cannot be read."""
    from . import land_tool
    files = [f for f in changed if Path(f).name == CONTRACT_FILE]
    if not files:
        return None
    names: set = set()
    for f in files:
        try:
            docs = [json.loads(subprocess.run([land_tool.GIT, "-C", str(repo), "show", f"{rev}:{f}"], capture_output=True, text=True).stdout or "{}")
                    for rev in (base, head)]
        except ValueError:
            return None
        old, new = (d.get("components", {}).get("schemas", {}) for d in docs)
        names |= {n for n in set(old) | set(new) if old.get(n) != new.get(n)}
        ops = [{o.get("operationId"): o for p in d.get("paths", {}).values() for o in p.values() if isinstance(o, dict) and o.get("operationId")}
               for d in docs]
        names |= {n for n in set(ops[0]) | set(ops[1]) if ops[0].get(n) != ops[1].get(n)}
    return names


def other_runner(cfg: Config) -> str:
    """Another build runner than [check].build_remote, for one retry (a `[check].remote` entry); the same one when there is no other."""
    return next((r for r in _runners(cfg) if r != cfg.build_remote), cfg.build_remote)


def swift_whole_why(changed: list[str], cfg: Config, contract: bool = False) -> str:
    """Why the train's Swift run is the whole suite ('' = a selection may be made): what the train row says beside the rung.
    `contract`: an openapi.json is mapped to suites (contract_types), never the whole plan; the generator's Package and config still are."""
    if not cfg.swift_test_target or not cfg.swift_test_dir:
        return "no [check].swift_test_target and swift_test_dir in the pinned rules"
    other = [f for f in _swift_built(changed, cfg) if not f.endswith((".swift", *SWIFT_NEUTRAL)) and not (contract and Path(f).name == CONTRACT_FILE)]
    return f"a non-Swift build input changed: {', '.join(other[:3])}" if other else ""


def swift_selectors(names, target: str) -> list[str]:
    """Every `-only-testing` value as `<target>/<Suite>` (train-20261126-210725: a case name `Suite.case()` went to -only-testing
    raw and xcodebuild refused it on both runners). Reads `<target>/<Suite>[/case]`, `Suite/case()`, `Suite.case()`, `Target.Suite.case()`
    and `-[Target.Suite case]`; a name none of these reads is dropped. Sorted, each once."""
    out = set()
    for f in names:
        f = str(f).strip()
        m = (re.fullmatch(rf"{re.escape(target)}/(\w+)(?:/.*)?", f) or re.fullmatch(r"-\[(?:\w+\.)?(\w+) \w+\]", f)
             or re.fullmatch(r"(\w+)/\w+\(.*\)", f) or re.fullmatch(r"(?:\w+\.)?(\w+)\.\w+\(.*\)", f) or re.fullmatch(r"(\w+)", f))
        if m:
            out.add(f"{target}/{m.group(1)}")
    return sorted(out)


NOT_IN_PLAN = re.compile(r"isn.t a member of the specified test plan or scheme")  # xcodebuild refusing a selector: the builder's error, not a runner's


def swift_tests(root, cfg: Config, only: list[str] | tuple = (), timeout_s: float | None = None) -> dict:
    """The Swift unit tests (not a per-step rung; the merge train runs it once per train): `[check].swift_tests` with build-for-testing,
    then test-without-building, on `[check].build_remote` in the runner's one kept DerivedData. A test target that does not compile
    is RED with the compiler errors; failing tests are RED naming them. No runner, or one that cannot run it, is a not-run row (never green)."""
    def not_run(why: str, detail: str = "") -> dict:
        journal.append("check", state="not-run", rung="swift-tests", reason=why, detail=detail[-300:])
        return {"ok": False, "skipped": False, "not_run": True, "stdout_tail": f"NOT RUN: {why}\n{detail[-300:]}".strip(), "stderr_tail": "", "results": []}

    if not cfg.swift_tests:
        return {"ok": True, "skipped": True, "stdout_tail": "skipped: no [check].swift_tests", "results": []}
    if not cfg.build_remote:
        return not_run("no [check].build_remote: the Swift tests never run on the manager's Mac")
    if only and cfg.swift_test_target:
        asked, only = list(only), swift_selectors(only, cfg.swift_test_target)
        if not only:  # never the whole plan for a selection no name of which reads as a suite
            return not_run("no -only-testing selector could be read from the names", ", ".join(asked)[:300])
    t0 = time.time()
    base = cfg.swift_tests if "-derivedDataPath" in cfg.swift_tests else (*cfg.swift_tests, "-derivedDataPath", "derived")  # the runner's kept dir is put in by _remote_build
    b = _remote_build(root, cfg, (*base, "build-for-testing"), "test", reuse=False, timeout_s=timeout_s)
    if b is None:
        return not_run("the build runner is unreachable")
    if b.get("remote_env_red"):
        return not_run("the runner could not build (not a compile error)", b["results"][0].get("stderr_tail") or "")
    if not b["ok"]:
        row = b["results"][0]
        return {"ok": False, "skipped": False, "stdout_tail": "RED: the test target does not compile\n" + (row.get("errors") or row.get("stdout_tail") or "")[-3000:],
                "stderr_tail": row.get("stderr_tail") or "", "results": [row]}
    left = None if timeout_s is None else max(60.0, timeout_s - (time.time() - t0))
    t = _remote_build(root, cfg, (*base, *(f"-only-testing:{x}" for x in only), "test-without-building"), "test", reuse=False, timeout_s=left)
    if t is None:
        return not_run("the build runner became unreachable")
    said = "\n".join((x.get("stderr_tail") or "") + (x.get("stdout_tail") or "") for x in t.get("results") or [])
    if NOT_IN_PLAN.search(said):  # no runner can run what the builder asked for: one alert, never a retry on another runner
        what = next((ln for ln in said.splitlines() if NOT_IN_PLAN.search(ln)), "")[-300:]
        _rung_alert("swift-tests", f"builder error: xcodebuild refused an -only-testing selector: {what}")
        return {"ok": False, "skipped": False, "builder_error": True, "stdout_tail": f"BUILDER ERROR: an -only-testing selector the test plan lacks\n{what}",
                "stderr_tail": "", "results": t.get("results") or []}
    if t.get("remote_env_red"):
        return not_run("the runner could not run the tests (not a test failure)", t["results"][0].get("stderr_tail") or "")
    row = t["results"][0]
    out = (row.get("stdout_tail") or "")
    try:  # the names from the whole log: the tail cut the top of a long `Failing tests:` list (2026-11-26 14:16: 0 names read of 40)
        full = Path(row["log"]).read_text(errors="replace") if row.get("log") and Path(row["log"]).is_file() else out
    except OSError:
        full = out
    ran = re.findall(r"Executed (\d+) tests?, with (\d+) failures?", out)
    names = failing_cases(full)
    count, failed = (int(ran[-1][0]), int(ran[-1][1])) if ran else (int((re.findall(r"Test run with (\d+) tests?", out) or ["0"])[-1]), len(names))
    secs = round(time.time() - t0, 1)
    journal.append("check", state="swift-tests", rung="swift-tests", ok=t["ok"], seconds=secs, tests=count, failures=failed,
                   suites=len(only) if only else "whole")  # the selection's size beside its time: SWIFT_SELECT_MAX is set from these
    head = f"swift-tests: {count} tests, {failed} failed, {secs} s"
    if not t["ok"]:
        return {"ok": False, "skipped": False, "stdout_tail": f"RED: {head}\nfailing: {', '.join(names) or '(no test name read)'}\n" + out[-2000:],
                "stderr_tail": row.get("stderr_tail") or "", "results": [row], "failing": names, "failures": failed}
    return {"ok": True, "skipped": False, "stdout_tail": head, "stderr_tail": "", "results": [row]}


def perf(root, since: str, changed: list[str], cfg: Config) -> dict:
    """The perf rung: the engine half, and, when a changed path is under `fichero/`, the Swift half. ok = both ok; a Swift-only batch is
    never "not required"."""
    from . import perf_rung
    if SCANS_OWED[0]:
        return {"ok": True, "skipped": True, "stdout_tail": "owed to the train: perf runs once on its candidate", "stderr_tail": "", "results": []}
    eng = _perf_engine(root, since, changed, cfg)
    if not cfg.perf or not any(f.startswith(perf_rung.APP_PATHS) for f in changed):
        return eng
    sw = _perf_swift(root, cfg)
    if eng.get("skipped") and "not required" in eng.get("stdout_tail", ""):
        return sw
    return {**eng, "ok": eng["ok"] and sw["ok"], "skipped": False, "stdout_tail": (eng["stdout_tail"] + "\n" + sw["stdout_tail"])[-3500:],
            "results": [*eng.get("results", []), *sw.get("results", [])], **({"not_run": True} if eng.get("not_run") or sw.get("not_run") else {})}


def _grep_waivers(root, rev: str, dirs: tuple[str, ...]) -> tuple[dict[str, int], list[str]]:
    """In-code waiver counts per tool at `rev` over the scanned dirs, and the lines (for the issue numbers)."""
    from . import security_rung
    out = _lines(root, "grep", "-hE", WAIVER_RE, rev, "--", *dirs) or []
    return security_rung.waiver_counts({"all": "\n".join(out)}), out


def _added_lines(root, since: str, head: str, dirs: tuple[str, ...]) -> list[tuple[str, int, str]]:
    """(file, line number, text) of every line the range adds under the scanned dirs (`git diff -U0`)."""
    out, f, n = [], "", 0
    for line in _lines(root, "diff", "-U0", "--no-ext-diff", "--no-color", "--no-renames", f"{since}...{head}", "--", *dirs) or []:
        if line.startswith("+++ "):
            f = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            n = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            n += 1
            out.append((f, n, line[1:]))
    return out


def _issue_is_approved(n: int) -> bool:
    """The issue carries the `security-waiver-approved` label (only the owner or the manager applies it). `gh` unavailable, unauthenticated
    or any error = not approved: a lookup that cannot answer never approves."""
    try:
        r = subprocess.run(["gh", "issue", "view", str(n), "--json", "labels", "--jq", ".labels[].name"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and APPROVED_LABEL in r.stdout.split()


def _entries(doc) -> int:
    """How many findings a baseline file holds: bandit's {"results": [...]} or gitleaks's bare list."""
    return len(doc.get("results", [])) if isinstance(doc, dict) else len(doc)


def security_lints(root, since: str, head: str, approved=None, dirs: tuple[str, ...] = ()) -> list[str]:
    """What the batch's diff may not do (`scan-thresholds-and-waivers`): add a waiver without a rule, a reason and an issue; raise a
    tool's waiver count without an issue carrying the approved label; raise a baseline; write an osv ignore too far out or without a
    reason; write a gitleaks allowlist without a description."""
    from . import security_rung as sr
    out = sr.waiver_lint(_added_lines(root, since, head, dirs))
    base_c, base_lines = _grep_waivers(root, since, dirs)
    head_c, head_lines = _grep_waivers(root, head, dirs)
    issues = sorted({int(i) for line in head_lines if line not in set(base_lines) for i in re.findall(r"\(#(\d+)\)", line)})
    out += sr.waiver_ratchet(base_c, head_c, issues, approved or _issue_is_approved)
    for f in ("scripts/bandit_baseline.json", "scripts/gitleaks_baseline.json"):
        old, new = _lines(root, "show", f"{since}:{f}"), _lines(root, "show", f"{head}:{f}")
        if old is not None and new is not None:
            try:
                out += sr.baseline_raised(f, _entries(json.loads("\n".join(old))), _entries(json.loads("\n".join(new))))
            except ValueError:
                out.append(f"{f} does not read as JSON at one of the heads")
    for f, check in (("osv-scanner.toml", sr.osv_config_problems), (".gitleaks.toml", sr.gitleaks_config_problems)):
        if (text := _lines(root, "show", f"{head}:{f}")) is not None:
            try:
                out += check("\n".join(text))
            except (ValueError, tomllib.TOMLDecodeError) as e:
                out.append(f"{f} does not read: {e}")
    return out


SCANS_OWED = _PerThread(False)  # local.train.security-and-perf-once: the scanners and perf are the train's (work.do_check sets it)


def security(root, since: str, head: str, changed: list[str], cfg: Config) -> dict:
    """The security rung: the waiver lints, then `scripts/security_scan_run.py` over the batch (bandit with its baseline, semgrep with
    --baseline-commit, gitleaks over the batch's commits; osv-scanner only when `[check.security].osv` is on), reading only what is NEW.
    A scanner missing or at a version that is not pinned is REFUSED by name. Its table is in the row (`table`) and goes into the review
    prompt under SECURITY SCAN. Runs on `[check].build_remote` (never on this Mac) over the scratch tree shipped WITH its .git, under
    `[check.security].path`; an unreachable runner is a not-run row."""
    if not cfg.security:
        return {"ok": True, "skipped": True, "stdout_tail": "skipped: not configured", "results": []}
    dirs = tuple(cfg.security.get("dirs") or ())
    if not [f for f in changed if (dirs and f.startswith(dirs)) or f in ("osv-scanner.toml", ".gitleaks.toml")]:
        return {"ok": True, "skipped": True, "stdout_tail": "not required: no changed path is under a scanned directory", "stderr_tail": "", "results": []}
    problems = security_lints(root, since, head, dirs=dirs)
    if SCANS_OWED[0]:  # the added-line lints only; the scanners run once on the train's candidate
        return _report_only("security", cfg.security, not problems, [*problems, "the scanners are owed to the train"])
    pins = dict(cfg.security.get("pins") or {})
    osv_on = bool(cfg.security.get("osv", False))
    if not cfg.build_remote:
        return _not_run("security", cfg.security, "no runner", "no [check].build_remote: the security scan never runs on the manager's Mac", {}, problems)
    # 2026-11-27 11:16 (train-20261127-111606): green on every rung but security, where the iMac said "bandit/semgrep/gitleaks is not
    # installed on the runner", and the train went back red. A runner without the pinned tools is a fault of the runner, never a
    # step's red: the next runner that has them scans; with none, a not-run row that is never red and one alert naming the runners
    tried, missing = [], {}
    for runner in [cfg.build_remote, *[x for x in _runners(cfg) if x != cfg.build_remote]]:
        if runner.partition(":")[0] in {t_.partition(":")[0] for t_ in missing}:
            continue  # the same Mac in another folder has the same tools
        r = _security_on(root, since, head, replace(cfg, build_remote=runner), problems, pins, osv_on)
        tried.append(runner)
        if not (infra := r.pop("_runner_refused", None)):
            return r
        missing[runner] = infra
    why = "; ".join(f"{h}: {', '.join(v)}" for h, v in missing.items())
    journal.append("check", state="runner-tools-missing", rung="security", runners=list(missing), detail=why[-600:])
    down = all(v == ["(unreachable)"] for v in missing.values())
    _runner_alert(f"no check runner could run the security scan ({why[:300]})" if down else
                  f"no check runner has the pinned security scanners ({why[:300]}): `builder machines scanners --install` puts them on each")
    reason = "runner down" if down else "no runner has the pinned scanners"
    return {**_not_run("security", cfg.security, reason, why, {}, problems), "ok": True, "infra": True}


RUNNER_ALERTED: set = set()


def _runner_alert(why: str) -> None:
    """One manager alert per cause per process, from the loop only (a jailed check has no alert of its own to raise)."""
    if why in RUNNER_ALERTED:
        return
    RUNNER_ALERTED.add(why)
    try:
        from fichero_builder import queue
        queue.alert("-", "runner-tools", why, str(journal.STATE / "journal.jsonl"), ["retry"])
    except Exception:  # noqa: BLE001 - an alert that cannot be raised is the journal row above
        pass


RUNNER_FAULT = re.compile(r"^REFUSED: (\S+) (?:is not installed on the runner|is \S+ on the runner, the pin is)")


def _security_on(root, since: str, head: str, cfg: Config, problems: list, pins: dict, osv_on: bool) -> dict:
    """The scan on cfg.build_remote. A result whose every REFUSED line is the runner's (a tool missing there, or at another version
    than the pin) carries `_runner_refused` (those tools), so the caller tries the next runner."""
    # the runner's ssh PATH is only the system dirs; a leading ~/ becomes $HOME/ (expanded there, so it sits inside double quotes), the rest is quoted
    parts = [*(cfg.security.get("path") or SECURITY_PATH), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    path = ":".join('"$HOME/"' + shlex.quote(d[2:]) if d.startswith("~/") else shlex.quote(d) for d in parts)
    scan = shlex.join([_gate_python(cfg, GATE), "scripts/security_scan_run.py", "--since", since, "--head", head, "--pins", json.dumps({**pins, "osv-scanner-enabled": osv_on})])
    # the pin check first (its report goes to stderr; a mismatch is the scan's own REFUSED line), then the scan under the same PATH
    script = f"export PATH={path}; scripts/install_security_tools.sh --check >&2; {scan}"
    rr = _remote_build(root, cfg, ("sh", "-c", script), "security", reuse=False, timeout_s=float(cfg.security.get("timeout_s", 720)))  # the scan keeps its own budget
    if rr is None:  # unreachable: the runner's fault too, the next one scans
        return {"_runner_refused": ["(unreachable)"]}
    r = rr["results"][0]
    if (t := _timed_out_row("security", r)) is not None:
        return t
    m = SECURITY_LINE.search(r.get("stdout_tail") or "")
    refused, rows, rows_table = [], [], "none"
    if not m:
        return _not_run("security", cfg.security, "scan refused", "the scan printed no SECURITY-RESULT line: " + (r.get("stderr_tail") or r.get("stdout_tail") or "")[-300:], {"results": [r]}, problems)
    res = json.loads(m.group(1))
    refused, rows, rows_table = res.get("refused", []), res.get("rows", []), res.get("table", "none")
    reds = [x for x in rows if x.get("red")]
    if refused and all(RUNNER_FAULT.match(x) for x in refused) and not [x for x in rows if x.get("red")]:
        return {"_runner_refused": [RUNNER_FAULT.match(x)[1] for x in refused]}  # a red the scanners that ran found stands (below)
    if refused:  # REFUSED: <tool> ...: that scanner did not scan; the others did, so their reds and the lint problems stay in the lines
        tools = [(re.match(r"REFUSED: (\S+)", x) or [None, "a scanner"])[1] for x in refused]
        return _not_run("security", cfg.security, f"{', '.join(tools)} refused", "\n".join(refused), {"results": [r], "table": rows_table},
                        [*problems, *[f"{x['scanner']} {x['rule']} {x['where']}" for x in reds]])
    lines = [*problems, *refused, *[f"{x['scanner']} {x['rule']} {x['where']}" for x in reds]]
    return _report_only("security", cfg.security, not (problems or refused or reds), lines or ["no new finding"],
                        {"results": [r], "table": rows_table, "gitleaks_clean": not any(x.get("scanner") == "gitleaks" for x in reds)})


def push_blocker(root, pinned, since: str, head: str, scan: dict | None) -> str:
    """Why the head may not be sent to GitHub yet, or "". Whatever `[check.security].enforce` says, the push needs (1) no hit of the land
    boundary patterns over since..head and (2) a `security` row that scanned this batch with gitleaks and found nothing new: a skipped,
    not-run, refused or missing row, or a gitleaks finding, blocks it (the batch then runs the rung on the Macs)."""
    from . import land_tool
    try:  # the PINNED harness.toml, as the land step reads it: a lane's own edit of [land].boundary never loosens the patterns
        patterns = list((tomllib.loads((Path(pinned) / "harness.toml").read_text()).get("land") or {}).get("boundary", land_tool.DEFAULT_BOUNDARY))
    except (OSError, ValueError) as e:
        return f"the pinned harness.toml could not be read: {e}"
    if hits := land_tool.boundary(root, since, head, patterns):
        return "the public boundary: " + "; ".join(hits)
    if not scan:
        return "no security row: the head was not scanned"
    if scan.get("skipped") or scan.get("not_run") or scan.get("gitleaks_clean") is not True:
        return "the security rung did not show a clean gitleaks scan over " + f"{since[:9]}..{head[:9]}: " + (scan.get("stdout_tail") or "")[:160].replace("\n", " ")
    return ""


def from_actions(rung: str, root, head: str, cfg: Config, local, pinned, since: str = "", scan: dict | None = None, lane: str = "") -> dict:
    """A rung in [check].actions takes its result from the GitHub Actions run of the batch head (actions.fetch): green or red from the run,
    or `local()` with one journal row saying why when there is no usable run. Not listed: `local()` and no push. The head is pushed only
    when `push_blocker` is empty (boundary clear, `scan` = the security row shows gitleaks ran clean), to `lane-<lane>` and only when `head`
    is the tip of that lane's `work-<lane>` ref (actions.lane_branch)."""
    if rung not in cfg.actions or (rung == "unit" and not cfg.always_tests):  # a rung the local run skips is not turned on by Actions
        return local()
    if why := push_blocker(root, pinned, since, head, scan):
        journal.append("check", state="actions-local", rung=rung, head=head, reason="not pushed: " + why)
        return local()
    res = actions.fetch(root, head, actions.lane_branch(root, lane, head), cfg.actions_timeout_s)
    if res["state"] == "none":
        journal.append("check", state="actions-local", rung=rung, head=head, reason=res["why"])
        return local()
    return {"argv": [], "exit_code": 0 if res["ok"] else 1, "ok": res["ok"], "timed_out": False, "seconds": 0, "results": [], "actions_run": res["run"],
            "stdout_tail": f"from GitHub run {res['run']}: step {actions.STEP!r} {res['conclusion']}", "stderr_tail": "" if res["ok"] else res["lines"]}


def rung_not_run(r: dict) -> bool:
    """A rung that was skipped, refused or could not run is "not run" on the ladder and the console, never ok/green."""
    return bool(r.get("not_run") or r.get("skipped"))


CHEAP_RUNGS = ("ready", "guards", "contract-current", "since-guards")  # independent of each other and of the tests: all report in one pass; `unit` is not one: it pushes the head to GitHub, so only a ladder green so far (security included) reaches it


def ladder(rungs: list) -> dict:
    """Run (name, callable) rungs in order. A red stops the ladder, except that the cheap independent rungs (CHEAP_RUNGS) that
    follow a red cheap rung still run, so the worker gets every one of their findings in one fix brief (throughput review
    2026-11-24: 14 of 58 check reds were a later rung failing after the worker fixed an earlier one). `failed` is the first red,
    `also_failed` the other cheap reds."""
    out = []
    reds: list[str] = []
    for name, fn in rungs:
        if reds and name not in CHEAP_RUNGS:
            continue
        if name in SKIP_RUNGS[0]:
            out.append({"name": name, "ok": True, "skipped": True, "stdout_tail": "skipped: the merge train runs it once per train", "results": []})
            continue
        if (prior := (REUSE[0] or {}).get(name)) is not None:  # green before the approve, for this exact head: not run again (dev-workflows.run.loop-needs-maintainer)
            out.append({**prior, "name": name, "cached": True})
            if prior.get("reused"):  # local.check.fix-round-reuses-verdicts: one rung row naming the head it was judged at
                ACTIVITY(kind="check", key=_KEY[0], state="rung", rung=name, ok=True, reused=prior["reused"])
            continue
        ACTIVITY(kind="check", key=_KEY[0], state="rung-start", rung=name, load=_load())
        t0 = time.time()
        r = {"name": name, **fn()}
        # every rung row: its own wall time and the machine's load at its start and end (manager 2026-11-04: the ladder-time report
        # had no load and no wall time for the multi-result rungs)
        ACTIVITY(kind="check", key=_KEY[0], state="rung", rung=name, ok=bool(r.get("ok")), not_run=rung_not_run(r), seconds=r.get("seconds"),
                 wall_s=round(time.time() - t0, 1), load=_load())
        out.append(r)
        if ON_RUNG[0]:
            ON_RUNG[0](name, bool(r.get("ok")), out)
        if not r["ok"]:
            reds.append(name)
            if name not in CHEAP_RUNGS:
                break
    return {"ok": not reds, "failed": reds[0] if reds else "", "also_failed": reds[1:], "rungs": out}


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


SCRATCH_CHECKOUT_S = 600.0  # a scratch tree's `git worktree add`: minutes under load, never the 60 s other git calls get


def _scratch_tree(root, head: str, pinned, cfg: Config, overlay: bool = True, data_from_head: tuple = (), stricter_from_head: tuple = ()) -> str:
    """A detached worktree of `head` with the pinned copy's check files laid over it: the checks judge the worker's
    committed code, never its uncommitted edits and never its own copies of the checks. overlay=False: head's own tree,
    for the pytest rungs (manager 2026-11-02: pinned copies JUDGE, they are not the code under test; a batch that changes a
    guard and its test, or harness.toml and the code reading it, is tested as it will land). `data_from_head`: guard DATA files
    (a .json under a check path, e.g. an allowlist a guard reads beside itself) the manager approved by name: head's own copy
    stays instead of the pinned one, so the pinned guard judges head's routes against head's allowlist; the script stays pinned."""
    sha = (_lines(root, "rev-parse", head) or [""])[0]
    tree = _mkdtemp("check-tree-", readable=True)
    # no repo hook runs as the owner. A whole checkout at load 100 with Defender scanning every write took over git's default 60 s and
    # was killed (2026-11-07: 'reset died of signal 9', then an empty reason): the checkout gets SCRATCH_CHECKOUT_S
    r = _git(root, "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach", "-q", tree, sha, timeout_s=SCRATCH_CHECKOUT_S)
    if not r["ok"] and "Permission denied" in r["stderr_tail"]:
        # 2026-11-11: the manager's `builder done` cannot add a worktree to the worker's clone (its .git/worktrees is the jail user's):
        # a shared clone instead, every new file the invoking user's, the objects by alternates, the remote refs the checks diff against
        os.rmdir(tree)
        r = _git(root, "clone", "-q", "--shared", "--no-checkout", str(root), tree, timeout_s=SCRATCH_CHECKOUT_S)
        if r["ok"]:
            _git(tree, "fetch", "-q", str(root), "+refs/remotes/*:refs/remotes/*", timeout_s=SCRATCH_CHECKOUT_S)
            r = _git(tree, "-c", "core.hooksPath=/dev/null", "checkout", "-q", "--detach", sha, timeout_s=SCRATCH_CHECKOUT_S)
    if not r["ok"]:
        why = r["stderr_tail"].strip() or (f"timed out after {SCRATCH_CHECKOUT_S:g} s" if r.get("timed_out") else f"exit {r.get('exit_code')}")
        raise RuntimeError(f"scratch tree failed: {why}")
    try:
        for f in (_lines(pinned, "ls-files") or []) if overlay else []:
            if f.startswith(cfg.check_paths):
                if (f in data_from_head and f.endswith(".json")) or f in stricter_from_head:  # stricter: see `stricter_files`
                    continue
                src, dest = Path(pinned) / f, Path(tree) / f
                if src.is_symlink():
                    raise RuntimeError(f"pinned file {f} is a symlink: refused")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.parent.resolve().is_relative_to(Path(tree).resolve()):
                    raise RuntimeError(f"{f} resolves outside the scratch tree: refused")
                dest.unlink(missing_ok=True)  # never write through a worker-committed symlink (review 4 H1)
                dest.write_bytes(src.read_bytes())
                dest.chmod(src.stat().st_mode)
    except (RuntimeError, OSError):
        drop_tree(root, tree)  # a refusal leaves no half-made worktree behind (review -89)
        raise
    return tree


def stricter_files(root, since: str, head: str, cfg: Config, pinned, rows: bool = False) -> tuple:
    """`allowlist-entries-only-removed` (2026-11-14: a guard on base reported a stale entry, "drop from the set", and the lane could not
    drop it: any edit to a pinned guard was a refusal and the pinned copy kept saying stale): the check-path files the diff changes
    whose head copy is the PINNED copy with allowlist entries removed (review: compared with the lane's merge base, an older guard minus
    an entry would have replaced a newer pinned one). The ladder lays head's copy of exactly these over the pinned ones; `rows`: one
    `auto` row each (the ladder's call only, never the presubmit's or the precheck's)."""
    if "allowlist-entries-only-removed" not in cfg.auto:
        return ()
    from fichero_builder import autofix
    out = []
    for _s, _m, f in _changes(root, since, head, "--diff-filter=M"):
        src = Path(pinned) / f
        if f.startswith(cfg.check_paths) and f.endswith((".py", ".json")) and src.is_file() and not src.is_symlink():
            if autofix.allowlist_only_removed(f, src.read_text(errors="replace"), "\n".join(_lines(root, "show", f"{head}:{f}") or [])):
                if rows:
                    journal.append("auto", rule="allowlist-entries-only-removed", head=head, file=f, detail="the pinned copy with only allowlist entries removed: the guard is stricter; head's copy judges")
                out.append(f)
    return tuple(out)


def drop_tree(root, tree: str) -> None:
    """Remove a scratch tree, a worktree of `root` or a shared clone (2026-11-11): git forgets it, then the directory goes."""
    if not tree:
        return
    if os.path.isdir(os.path.join(tree, ".git")):  # a clone: not a worktree of root; its own dir holds everything
        shutil.rmtree(tree, ignore_errors=True)
        return
    _git(root, "worktree", "remove", "--force", tree)
    shutil.rmtree(tree, ignore_errors=True)


class EmptyRange(RuntimeError):
    """since equals head: a landing branch that never got its commit judged green on nothing (2026-11-02)."""


def ladder_over(root, since_sha: str, head: str, pinned, protected_ids=(), maintainer: bool = False, approve_weakened: bool | tuple = False,
                approve_red: bool = False, approve_pinned_new: bool = False, guard_data: tuple = (), lane: str = "") -> dict:
    """The one way `builder check` and `builder work` run the ladder: an empty range is refused, never judged. `lane`: the lane whose
    batch this is; the `unit` rung pushes only to its branch (from_actions)."""
    if since_sha == head:
        raise EmptyRange(f"{since_sha[:9]}..{head[:9]} is empty: nothing to check")
    return run_ladder(root, since_sha, head, pinned, list(protected_ids), maintainer=maintainer, approve_weakened=approve_weakened, approve_red=approve_red,
                      approve_pinned_new=approve_pinned_new, guard_data=guard_data, lane=lane)


def run_ladder(root, since: str, head: str, pinned, protected_ids=(), jail_required: bool = True, maintainer: bool = False,
               approve_weakened: bool | tuple = False, approve_red: bool = False, approve_pinned_new: bool = False, guard_data: tuple = (), lane: str = "") -> dict:
    """The project's whole ladder over the diff since..head, judged by the PINNED copy (an engine-owned checkout
    outside the worker's tree; its harness.toml is the config): pinned-checks, ready, diff bound, red-on-base for
    the changed test files (its green run is the pytest rung), guards, contract. Stops at the first red.
    `protected_ids`: the behaviour ids of the item, whose spec acceptance the worker may not rewrite.
    `maintainer`: a maintainer batch changes pinned files on purpose; the pinned-checks row records which and the
    ladder runs on (weakened tests and a rewritten acceptance still refuse)."""
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
    _jail_enter(j)
    _KEY[0] = f"check {since[:9]}..{str(head)[:9]}"
    RED_STOOD.discard(_KEY[0])  # a new ladder over the range judges its runners afresh
    _jailmod.note_unjailed(j, "check", since=since, head=str(head))
    sweep_cancels()
    ACTIVITY(kind="check", key=_KEY[0], state="start")
    ended: dict = {}
    try:
        ended = _run_ladder(root, since, head, pinned, protected_ids, maintainer, approve_weakened, approve_red, approve_pinned_new, guard_data, lane)
        return ended
    finally:
        ACTIVITY(kind="check", key=_KEY[0], state="end", ok=bool(ended.get("ok")), failed=ended.get("failed", "?"))
        cancel_file(str(head)).unlink(missing_ok=True)  # the superseded ladder has ended: its marker has done its work
        _jail_exit()
        if _SHIPPED or _DOWN:
            _drop_remote(load(pinned))


def _needs_red(names: list[str], tests: list[str], cfg: Config) -> bool:
    """By path (spec): with red_paths set, only a diff touching them (or changing a test) owes a red-on-base run."""
    return not cfg.red_paths or bool(tests) or any(n.startswith(cfg.red_paths) for n in names)


def tests_only(changed: list[str], cfg: Config) -> bool:
    """`red-on-base-tests-only`: the rule is on, red_paths is set, and every changed path (any status, so a deletion counts) is a test file
    (a `test_globs` name), sits in a `tests`/`Tests` directory, or is a Markdown file. A path outside red_paths that is code
    (`scripts/*.py`, `pipeline/*.py`) is source: its red stays owed. No changed path at all (a failed git call) is not test-only."""
    def inert(f: str) -> bool:
        p = Path(f)
        return (any(fnmatch.fnmatch(p.name, g) for g in cfg.test_globs) or bool({"tests", "Tests"} & set(p.parts[:-1])) or p.suffix == ".md")
    return ("red-on-base-tests-only" in cfg.auto and bool(cfg.red_paths) and bool(changed)
            and not any(f.startswith(cfg.red_paths) for f in changed) and all(inert(f) for f in changed))


def _whole_tests(names: list[str], cfg: Config) -> tuple:
    """Tests dirs the green run takes whole: a changed source can break an old test its own new test never imports."""
    return tuple(sorted({d for p, v in cfg.whole_tests.items() if any(n.startswith(p) for n in names)
                         for d in ([v] if isinstance(v, str) else v)}))


def _no_red_row(tree, whole: tuple, cfg: Config) -> dict:
    """No red-on-base owed; a change under a whole_tests prefix (a deletion too) still runs those dirs whole."""
    if whole:
        return green_runs(tree, [], whole, cfg, 1800)
    return {**_skipped("red-on-base"), "stdout_tail": "not required: no changed path is under [check].red_paths"}


RUNGS = ("ready", "diff-bound", "red-on-base", "guards", "security", "unit", "contract-current", "since-guards", "build", "ui", "perf")  # the ladder below, in order


def pick_rungs(all_rungs: list, cfg: Config, tree) -> list:
    """The ladder's rungs: every one of RUNGS in order unless [check].rungs names which to run and in what order; a name there may also
    be a [[check.rung]] (argv run in the scratch tree). A name that is neither refuses."""
    if not cfg.rungs and not cfg.rung:
        return all_rungs
    have = dict(all_rungs)
    for d in cfg.rung:
        if not d.get("name") or not d.get("argv"):
            raise ValueError(f"harness.toml [[check.rung]] needs a name and an argv: {d!r}")
        have[d["name"]] = (lambda d=d: _run(d["name"], list(d["argv"]), tree, d.get("timeout_s", 600), cfg))
    names = cfg.rungs or tuple(n for n, _ in all_rungs) + tuple(d["name"] for d in cfg.rung if d["name"] not in dict(all_rungs))
    if unknown := [n for n in names if n not in have]:
        raise ValueError(f"harness.toml [check].rungs names unknown rungs {unknown}")
    return [(n, have[n]) for n in names]


def _run_ladder(root, since: str, head: str, pinned, protected_ids=(), maintainer: bool = False, approve_weakened: bool | tuple = False,
                approve_red: bool = False, approve_pinned_new: bool = False, guard_data: tuple = (), lane: str = "") -> dict:
    cfg = load(pinned)
    stricter = stricter_files(root, since, head, cfg, pinned, rows=True)
    bad = [b for b in pinned_violations(root, since, head, cfg, pinned) if b.split(": ", 1)[0] not in stricter]
    noted = ""
    if maintainer:  # only "a pinned check file was changed/deleted" is noted; a symlink, sitecustomize/.pth, .claude/, a new pinned-path file still refuse
        changed = [b for b in bad if b.endswith((": a pinned check file was changed", ": a pinned check file was deleted")) or " is pinned by name anywhere (" in b]  # a conftest.py edit: the manager's approve excuses it (2026-11-02)
        if changed:
            noted, bad = "maintainer batch: " + "; ".join(changed), [b for b in bad if b not in changed]
    if approve_pinned_new:  # the manager answered the alert with approve: a new file under a pinned path, recorded, not refused
        new = [b for b in bad if b.endswith(": a new file under a pinned path (only a new guard may be added there)")]
        if new:
            noted, bad = (noted + "; " if noted else "") + "approved new pinned files: " + "; ".join(new), [b for b in bad if b not in new]
    if (weak := weakened_tests(root, since, head, cfg)) and "weakened-tests-of-a-deleted-module" in cfg.auto:
        gone = deleted_modules(root, since, head, cfg)
        for f in [w for w in weak if weakened_by_a_deleted_module(root, since, head, w, gone)]:
            journal.append("auto", rule="weakened-tests-of-a-deleted-module", head=head, file=f, detail=f"its lost checks used {', '.join(sorted(gone))}, deleted by this diff")
            weak.remove(f)
    # the manager answered the alert with approve (an owner ruling renamed or dropped them): recorded, not refused; a tuple of files
    # (an approve bound to their content, ladder.approve-is-fingerprinted) excuses only those
    excused = [w for w in weak if approve_weakened is True or (isinstance(approve_weakened, tuple) and w in approve_weakened)]
    if excused:
        noted = (noted + "; " if noted else "") + f"approved weakened tests: {', '.join(excused[:5])}"
    if weak := [w for w in weak if w not in excused]:
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
    tree = _scratch_tree(root, head, pinned, cfg, data_from_head=tuple(guard_data), stricter_from_head=stricter)
    own = _scratch_tree(root, head, pinned, cfg, overlay=False)  # the pytest rungs: head as it will land
    try:
        ok_pin = {"name": "pinned-checks", "argv": [], "exit_code": 0, "ok": True, "timed_out": False, "seconds": 0,
                  "stdout_tail": (noted + "\n" if noted else "") + f"checks from the pinned copy over {head}", "stderr_tail": ""}
        green_only = HEAD_GREEN_ONLY[0] or tests_only([f for _s, _m, f in _changes(root, since, head)], cfg)
        if tests and not HEAD_GREEN_ONLY[0] and green_only:
            journal.append("auto", rule="red-on-base-tests-only", head=head, file=",".join(tests),
                           detail="every changed path is a test, a tests directory file or a Markdown file: no red owed; the tests run green on head")
        seen: dict = {}  # the security row, read by `unit` before it may push the head
        out = ladder(pick_rungs([
            ("ready", lambda: ready(tree, cfg)),
            ("diff-bound", lambda: diff_bound(root, since, head, cfg, maintainer)),
            ("red-on-base", lambda: red_on_base_rung(root, since, head, names, tests, whole, cfg, own, approve_red, green_only)),
            ("guards", lambda: guards_on_current_base(root, since, head, pinned, cfg, tree, data_from_head=tuple(guard_data), stricter_from_head=stricter)),
            ("security", lambda: seen.setdefault("security", security(tree, since, head, names, cfg))),
            ("unit", lambda: from_actions("unit", root, head, cfg, lambda: unit(own, [f for _s, _m, f in _changes(root, since, head)], cfg), pinned, since, seen.get("security"), lane)),
            ("contract-current", lambda: contract_current(tree, names, cfg)),
            ("since-guards", lambda: since_guards(tree, since, names, cfg)),
            ("build", lambda: build(tree, build_names(root, since, head), cfg)),
            ("ui", lambda: ui(tree, [f for _s, _m, f in _changes(root, since, head)], cfg)),
            ("perf", lambda: perf(tree, since, [f for _s, _m, f in _changes(root, since, head)], cfg)),
        ], cfg, tree))
    finally:
        drop_tree(root, tree)
        drop_tree(root, own)
    owed = next((x.get("owed") for x in out["rungs"] if x.get("name") == "red-on-base" and x.get("owed")), [])
    return {**out, "rungs": [ok_pin, *unpinned_rows(cfg), *out["rungs"]], **({"owed": owed} if owed else {})}


OWE_WHOLE = _PerThread(False)  # local.check.red-on-base-changed-tests-only: with the train on, the whole-tests dirs are the train's (work.do_check sets it)


def red_on_base_rung(root, since: str, head: str, names: list[str], tests: list[str], whole: tuple, cfg: Config, own, approve_red=False,
                     green_only: bool = False) -> dict:
    """The red-on-base rung. With the train on (OWE_WHOLE) it runs the changed test files only, on the base and on the head; the
    `[check.whole_tests]` dirs of the diff are not run here, and the row lists them as `owed` to the train, which runs them once on its
    candidate (local.train.whole-tests-against-base). With the train off the head run takes them, as before."""
    owed, whole = (whole, ()) if OWE_WHOLE[0] else ((), whole)
    if green_only:
        r = green_runs(own, tests, whole, cfg, 1800) if tests or whole else _no_red_row(own, whole, cfg)
    elif _needs_red(names, tests, cfg):
        r = red_on_base(root, since, head, tests, cfg, head_tree=own, also_green=whole, approve_red=approve_red)
    else:
        r = _no_red_row(own, whole, cfg)
    if owed:
        r = {**r, "owed": list(owed), "stdout_tail": f"owed to the train: {', '.join(owed)}\n" + (r.get("stdout_tail") or "")}
    return r


def unpinned_rows(cfg: Config) -> list[dict]:
    """With [check].check_paths declared empty no check file is pinned: one NOT RUN row says so on every ladder (builder.client.empty-rungs)."""
    return [] if cfg.check_paths else [not_configured("pinned-paths", "[check].check_paths is empty: no check file is pinned, so none is protected from the diff")]


def run_tests(root, head: str, pinned, paths: list[str], jail_required: bool = True) -> dict:
    """`builder test` (the console's Run tests, owner 2026-11-02): the pinned pytest over `paths` (test files or dirs) in a
    scratch tree of `head`, as the jail user, on [check].remote when one is set; one pytest per top-level package."""
    from . import jail as _jailmod
    cfg = load(pinned)
    j = _jailmod.load(pinned)
    if j is None and jail_required:
        raise _jailmod.JailMissing("no [jail] in the rules file: tests will not run as the owner")
    if j is not None:
        j.require()
    _jail_enter(j)
    _jailmod.note_unjailed(j, "tests", head=str(head))
    tree = _scratch_tree(root, head, pinned, cfg, overlay=False)  # tests run on head as it is (manager 2026-11-02)
    try:
        return {**green_runs(tree, list(paths), (), cfg, 3600), "name": "tests"}
    finally:
        _jail_exit()
        _git(root, "worktree", "remove", "--force", tree)
        if _SHIPPED or _DOWN:
            _drop_remote(cfg)
