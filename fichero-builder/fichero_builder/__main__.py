"""`python -m fichero_builder run --worktree W --brief FILE ...` starts and watches a worker (run AS the worker user);
`python -m fichero_builder check REPO SINCE HEAD --pinned DIR [--id ID ...]` runs the project's ladder and prints typed JSON;
`python -m fichero_builder land REPO HEAD --pinned DIR --verdicts FILE --log FILE` runs the land gate and prints the push."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import json

from fichero_builder import check_tool, journal
from fichero_builder import run as run_mod


def state_dir(rules_root, explicit) -> Path:
    """For `run`: --state, else $FICHERO_BUILDER_STATE, else `<[jail].workroot>/state` from the rules file (the shared area
    both users can read, so the owner reads the worker's journal without sudo), else the XDG default."""
    if explicit:
        return Path(explicit)
    if os.environ.get("FICHERO_BUILDER_STATE"):
        return Path(os.environ["FICHERO_BUILDER_STATE"])
    f = Path(rules_root) / "harness.toml"
    if f.is_file():
        import tomllib

        workroot = tomllib.loads(f.read_text()).get("jail", {}).get("workroot")
        if workroot:
            return Path(workroot) / "state"
    return journal.STATE


def resolve(repo, rev: str) -> str:
    import subprocess

    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", f"{rev}^{{commit}}"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""  # unknown rev = no sha, never the rev's own text (review 1 N9)


def checked(head: str) -> bool:
    """A green `check` row for this exact head in the journal (dev-workflows.run.review-and-land: check before review and land)."""
    return any(r.get("event") == "check" and r.get("head") == head and r.get("ok") is True for r in journal.read())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="builder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="start a worker through the start path and watch its session file")
    r.add_argument("--worktree", required=True)
    r.add_argument("--brief", required=True, help="file holding the brief text")
    r.add_argument("--root", default=str(Path.cwd()))
    r.add_argument("--name", default=f"worker-{int(time.time())}")
    r.add_argument("--model", default="sonnet")
    r.add_argument("--kind", default="claude", choices=["claude", "pi"])
    r.add_argument("--provider", default="anthropic", help="pi: the provider in Pi's models.json")
    r.add_argument("--agent-dir", help="pi: an OWNER-owned Pi agent dir holding models.json (prices and base URLs the cap trusts); required for --kind pi")
    r.add_argument("--scratch", help="pi: the scratch path the policy allows writes under (default $TMPDIR)")
    r.add_argument("--session", default="harness")
    r.add_argument("--tick", type=float, default=30.0)
    r.add_argument("--handoff", help="the handoff file a successor reads (default <worktree>/HANDOFF.md)")
    r.add_argument("--state", help="where the journal lives (default $FICHERO_BUILDER_STATE, else <[jail].workroot>/state, else the XDG state home)")
    c = sub.add_parser("check", help="run the ladder over SINCE..HEAD from the pinned copy; exit 1 if red")
    c.add_argument("repo"), c.add_argument("since"), c.add_argument("head")
    c.add_argument("--pinned", required=True)
    c.add_argument("--id", action="append", default=[])
    c.add_argument("--state", help="where the journal lives (default: see run --state)")
    land = sub.add_parser("land", help="the land gate: a READY verdict for the exact range, the boundary, the ladder; prints the push, never pushes")
    land.add_argument("repo"), land.add_argument("head")
    land.add_argument("--pinned", required=True), land.add_argument("--verdicts", required=True), land.add_argument("--log", required=True)
    land.add_argument("--state", help="where the journal lives (default: see run --state)")
    a = ap.parse_args(argv)
    # run (as the worker) journals under the shared workroot; check and land (as the owner) keep the owner's own journal,
    # because land trusts the check row: a journal the worker can write would let a worker forge one.
    journal.STATE = state_dir(a.root, a.state) if a.cmd == "run" else (Path(a.state) if a.state else journal.STATE)
    if a.cmd == "land":  # ponytail: the gate is scripts/harness_land.py whole; this verb runs it, it does not copy it
        import runpy

        if problems := check_tool.rules_problems(a.pinned):  # the rules file first, as the gate script does: cheap and fail-closed
            print("REFUSED (rules file):\n  " + "\n  ".join(problems), file=sys.stderr)
            with open(a.log, "a") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "refused": "rules", "detail": problems}) + "\n")
            return 1
        head = resolve(a.repo, a.head)
        jp = journal.path()
        if jp.exists() and jp.stat().st_uid != os.getuid():  # land trusts this file: it must be the caller's own (review 1 N2)
            print(f"REFUSED: {jp} is not owned by this user; land reads only the owner's journal", file=sys.stderr)
            return 1
        if not head or not checked(head):
            print(f"REFUSED: no green `builder check` row for {head[:9] or a.head} in {journal.path()}; run builder check first", file=sys.stderr)
            return 1

        script = Path(__file__).resolve().parents[2] / "scripts" / "harness_land.py"
        sys.argv = [str(script), a.repo, a.head, "--pinned", a.pinned, "--verdicts", a.verdicts, "--log", a.log]
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as e:
            if isinstance(e.code, str):
                print(e.code, file=sys.stderr)
                return 1
            return int(e.code or 0)
        return 0
    if a.cmd == "check":
        head = resolve(a.repo, a.head)  # before the ladder: a commit made meanwhile never gets the row (review 1 M5)
        if not head:
            print(f"builder check: {a.head!r} is not a commit in {a.repo}", file=sys.stderr)
            return 1
        r = check_tool.run_ladder(a.repo, a.since, head, a.pinned, a.id)
        print(json.dumps(r, indent=1))
        journal.append("check", repo=str(a.repo), since=a.since, head=head, ok=bool(r.get("ok")), failed=r.get("failed", ""))
        return 0 if r.get("ok") else 1
    if a.kind == "pi":
        from fichero_builder import pi_rpc

        if not a.agent_dir:
            print("builder run refuses: --kind pi needs --agent-dir (an owner-owned dir; the worker's own ~/.pi/agent could set its own prices)", file=sys.stderr)
            return 1
        agent_dir = Path(a.agent_dir)
        if not pi_rpc.priced(agent_dir, a.provider, a.model):
            print(f"builder run refuses: {agent_dir / 'models.json'} has no cost for {a.provider}/{a.model}: unknown price, no start", file=sys.stderr)
            return 1
        scratch = Path(a.scratch or os.environ.get("TMPDIR", "/tmp"))
        procs = pi_rpc.pi_procs(root=a.root, scratch=scratch, provider=a.provider, session_dir=scratch / "pi-sessions" / a.name,
                                agent_dir=agent_dir)
    else:
        procs = run_mod.real_procs(Path.home(), a.worktree)
    end = run_mod.run(a.root, a.worktree, a.brief, name=a.name, model=a.model, kind=a.kind, tmux_session=a.session,
                      tick_s=a.tick, procs=procs, handoff=a.handoff)
    return 0 if end in ("gone", "parked") else 1


if __name__ == "__main__":
    sys.exit(main())
