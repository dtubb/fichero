"""The CLI face over `core.API` (pipeline.three-faces), plus --self-test, which proves each check can fail.

  python -m pipeline status | queue
  python -m pipeline start <issue> [<issue>...] [--milestone M] [--task T] [--base REF] [--from-file F]
  python -m pipeline check <issue>
  python -m pipeline approve-checks <issue> --findings TEXT
  python -m pipeline verdict <issue> <sha> READY|NOT_READY|PENDING --by reviewer|manager [--findings TEXT]
  python -m pipeline tell <window> "<text>"      answer <id> "<text>"      point <milestone>
  python -m pipeline pause | resume
  python -m pipeline file-bug "<title>" "<text>" [--milestone M] [--apply]
  python -m pipeline serve [--port N]
  python -m pipeline --self-test

A worker's shell (PIPELINE_WORKER set) may only run status and queue: the role split is enforced here and in the
MCP tool tables until the write jail exists (pipeline.jailed-agent).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from pipeline import core

# command -> positional arguments, then options (name, kwargs)
COMMANDS = {
    "status": [], "queue": [], "pause": [],
    "resume": [("--raise-cap", {"type": float, "dest": "raise_cap", "help": "lift today's daily API cap to this many dollars"})],
    "review": [("issue", {}), ("--worker", {"type": int, "default": 0, "dest": "worker_index"})],
    "start": [("issues", {"type": int, "nargs": "+"}), ("--milestone", {}), ("--task", {}),
              ("--base", {"help": "the ref the worktree comes off (default: the profile's base)"}),
              ("--from-file", {"help": "a local JSON issue (number, title, body, author, part_of) for a step not yet filed"})],
    "retry": [("issue", {}), ("--worker", {"type": int, "help": "index into the role's fallback list (default: one past the rate-limited stops)"})],
    "approve-checks": [("issue", {}), ("--findings", {"required": True, "help": "what the coder is told when the item goes back"})],
    "check": [("issue", {})],
    "repair": [("issue", {}), ("--base", {}), ("--from-file", {}), ("--since", {}), ("--why", {"default": ""})],
    "verdict": [("issue", {}), ("sha", {}), ("verdict", {}), ("--by", {"required": True}), ("--findings", {"default": ""})],
    "tell": [("window", {}), ("text", {})],
    "answer": [("qid", {}), ("text", {})],
    "point": [("milestone", {})],
    "reset": [("issue", {}), ("--why", {"default": ""})],
    "file-bug": [("title", {}), ("text", {}), ("--milestone", {}), ("--apply", {"action": "store_true", "help": "really write to GitHub (default: dry run)"})],
    "serve": [("--port", {"type": int, "default": 8765})],
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    for name, args in COMMANDS.items():
        s = sub.add_parser(name)
        for flag, kw in args:
            s.add_argument(flag, **kw)
    a = p.parse_args(argv)
    if a.self_test:
        return self_test()
    name = (a.cmd or "status").replace("-", "_")
    if os.environ.get("PIPELINE_WORKER") and name in core.WORKER_FORBIDDEN + ("serve", "file_bug"):
        print(json.dumps({"error": f"a worker may not run `{name}`"}))
        return 2
    if a.cmd == "serve":
        from pipeline import web
        web.serve(a.port)
        return 0
    if a.cmd == "file-bug":
        core.DRY_RUN = not a.apply
    kwargs = {k: v for k, v in vars(a).items() if k not in ("cmd", "self_test", "apply") and v is not None}
    print(json.dumps(core.API[name](**kwargs), indent=1, default=str))
    return 0


def self_test() -> int:
    """Each check can fail; the scratch parts run in a temp repo, never the real worktrees."""
    import re
    import subprocess
    import tempfile
    from pathlib import Path

    from pipeline import ROOT, budget, checks, coder, config

    fails = []

    def must(cond, name):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    profiles = sorted(p.stem for p in config.PROJECTS.glob("*.toml"))
    for name in profiles:
        try:
            config.load(name)
            must(True, f"profile {name} loads")
        except Exception as e:  # noqa: BLE001
            must(False, f"profile {name} loads: {e}")
    project = (config.PROJECTS / "current").read_text().strip()
    code = ""
    for p in (ROOT / "pipeline").glob("*.py"):
        if p.name == "__main__.py":
            continue
        code += "".join(re.sub(r"#.*", "", line) for line in p.read_text().splitlines(True))
    must(project not in code.lower(), f"runner code names no project (grep '{project}' outside comments)")
    env = coder.allowed_env(config.load(profiles[0]))
    must(set(env) <= set(coder.ALLOWED_ENV) | {"PI_CODING_AGENT_DIR", "PIPELINE_WORKER"}, "env allow-list drops everything else")
    must(not budget.room_for("pytest", {"pytest": 10**9}, {"free_mb": 100, "pressure": "normal"})[0], "memory check can refuse")
    must(not budget.room_for("pi", {"pi": 0}, {"free_mb": 10**6, "pressure": "critical"})[0], "critical pressure refuses")
    delays = [budget.backoff(i, rng=lambda: 1.0) for i in range(4)]
    must(delays == sorted(delays) and delays[0] < delays[-1], "backoff grows")
    sp = budget.Spawns({"coders": 1})
    sp.add("coders", "a")
    must(not sp.can("coders", "b")[0] and not sp.can("coders", "a")[0], "spawn cap and de-dup refuse")
    st = coder.parse_session(ROOT / "pipeline" / "tests" / "fixtures" / "pi-session-redacted.jsonl")
    must(st["cost_usd"] > 0 and st["tool_calls"], f"cost parser reads the redacted sample (${st['cost_usd']:.4f}, {sum(st['tool_calls'].values())} tool calls)")
    r = subprocess.run(["bash", str(ROOT / "scripts" / "lane_ready_check.sh"), "--self-test"], cwd=ROOT, capture_output=True, text=True)
    must(r.returncode == 0, f"lane_ready_check.sh --self-test: {r.stdout.strip()[-60:]}")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "r"
        repo.mkdir()

        def g(*a):
            subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True)

        g("init", "-q", "-b", "integration")
        g("config", "user.email", "x@y")
        g("config", "user.name", "x")
        (repo / "test_a.py").write_text("def test_a():\n    assert True\n")
        g("add", ".")
        g("commit", "-qm", "base")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        g("checkout", "-qb", "lane")
        (repo / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
        g("commit", "-qam", "lane")
        cfg = {"repo": {"base": "integration", "python_path": "", "test_env": {}, "scratch_base_env": ""}}
        rung = {"pytest": "{python} -m pytest -q -p no:cacheprovider {files}", "test_glob": ["*test*.py"], "kind": "red-on-base"}
        ok, text = checks.red_on_base(str(repo), str(repo), base, ["test_a.py"], rung, cfg)
        must(not ok and "NOT RED ON BASE" in text, "red-on-base refuses a test that passes on the base")
    print(f"\n{len(fails)} failing" if fails else "\nself-test OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
