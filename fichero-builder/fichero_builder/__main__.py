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

from fichero_builder import check_tool, journal, models, spec_tool, steps, work
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


def checked(repo, pinned, head: str) -> bool:
    """The green `check` row of exactly <[land].branch>..head in the journal (dev-workflows.run.review-and-land: check before review and land)."""
    from fichero_builder import land_tool

    try:
        since = land_tool.resolve_branch(repo, tomllib_land_branch(pinned))
    except (RuntimeError, OSError, KeyError, ValueError):
        return False
    return land_tool.green_row(journal.read(), head, since) is not None


def tomllib_land_branch(pinned) -> str:
    import tomllib

    return tomllib.loads((Path(pinned) / "harness.toml").read_text())["land"]["branch"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="builder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="start a worker through the start path and watch its session file")
    r.add_argument("--worktree", required=True)
    r.add_argument("--brief", required=True, help="file holding the brief text")
    r.add_argument("--root", default=str(Path.cwd()))
    r.add_argument("--name", default=f"worker-{int(time.time())}")
    r.add_argument("--model", help="default [models].builder of --root's harness.toml (no model name is written in code)")
    r.add_argument("--kind", default="claude", choices=["claude", "pi"])
    r.add_argument("--provider", default="anthropic", help="pi: the provider in Pi's models.json")
    r.add_argument("--agent-dir", help="pi: an OWNER-owned Pi agent dir holding models.json (prices and base URLs the cap trusts); required for --kind pi")
    r.add_argument("--scratch", help="pi: the scratch path the policy allows writes under (default $TMPDIR)")
    r.add_argument("--session", default="harness")
    r.add_argument("--tick", type=float, default=30.0)
    r.add_argument("--handoff", help="the handoff file a successor reads (default <worktree>/HANDOFF.md)")
    r.add_argument("--feed", help="the queue's lane: a folder only the owner writes; DONE ends the step, not the session; msg-<seq+1>.txt is typed into the same pane; `stop` ends it")
    r.add_argument("--seq", type=int, default=0, help="with --feed: the first brief's message number")
    r.add_argument("--state", help="where the journal lives (default $FICHERO_BUILDER_STATE, else <[jail].workroot>/state, else the XDG state home)")
    c = sub.add_parser("check", help="run the ladder over SINCE..HEAD from the pinned copy; exit 1 if red")
    c.add_argument("--repo", help="the engine-owned repo to judge from (default [check].engine_repo of the pinned rules)")
    c.add_argument("since"), c.add_argument("head")
    c.add_argument("--pinned", required=True)
    c.add_argument("--id", action="append", default=[])
    c.add_argument("--guard-data", action="append", default=[], help="a guard data file (a .json under a check path) whose HEAD copy the guards read instead of the pinned one; the script stays pinned")
    c.add_argument("--approve-pinned-new", action="store_true", help="the manager approved this range's new files under a pinned path: recorded in the pinned-checks row, not refused")
    c.add_argument("--approve-red", action="store_true", help="the manager approved this range's red-on-base refusal (a test that passes on base by design): recorded in the row")
    c.add_argument("--approve-weakened", action="store_true", help="the manager approved this range's weakened tests (an owner ruling): recorded in the pinned-checks row, not refused")
    c.add_argument("--maintainer", action="store_true", help="a maintainer batch: a changed pinned file is recorded in the pinned-checks row, not refused; point --pinned at the candidate's own tree")
    c.add_argument("--state", help="where the journal lives (default: see run --state)")
    ms = sub.add_parser("milestone", help="a milestone's open issues as one cluster brief per build-order step; questions, never guesses")
    ms.add_argument("name", nargs="?", help="the milestone (default: the first under `## In order` in specs/build-order.md with open issues)")
    ms.add_argument("--spec", help="the APPROVED spec whose Build order places the issues (default: the build-order line's `Spec:` path)")
    ms.add_argument("--repo-dir", default=str(Path.cwd())), ms.add_argument("--out", required=True, help="where the brief files go")
    ms.add_argument("--base", help="the base sha the briefs name (default: origin/<[land].branch> in --repo-dir)")
    ms.add_argument("--gh", default="gh")
    ms.add_argument("--enqueue", action="store_true", help="queue each step brief in the milestone's lane (worktree <[jail].workroot>/wt-<lane>), in build order")
    ms.add_argument("--state", help="where the queue and the journal live (default: the owner's journal dir)")
    land = sub.add_parser("land", help="the land gate after a green check row: a READY verdict for the exact range and the boundary, no second ladder; prints the push, never pushes")
    land.add_argument("--repo", help="the engine-owned repo (default [check].engine_repo of the pinned rules)")
    land.add_argument("head")
    land.add_argument("--pinned", required=True), land.add_argument("--verdicts", required=True), land.add_argument("--log", required=True)
    land.add_argument("--state", help="where the journal lives (default: see run --state)")
    ld = sub.add_parser("landed", help="after a READY verdict and a green check: push (--push only), refresh, pin, fast-forward the jail root, update the issues")
    ld.add_argument("sha")
    ld.add_argument("--root", default=str(Path.cwd()), help="the checkout holding harness.toml ([land].branch, [land].pinned_dir, [check].engine_repo, [jail])")
    ld.add_argument("--repo", help="the engine-owned repo (default [check].engine_repo)")
    ld.add_argument("--verdicts", help="the owner-owned verdict store (default: the verdicts*.json under --state that holds a READY for the range)")
    ld.add_argument("--gh", default="gh")
    ld.add_argument("--push", action="store_true", help="push sha to origin/<branch> first; nothing else ever sets this")
    ld.add_argument("--no-issues", action="store_true", help="leave the cited issues alone")
    ld.add_argument("--keep-worktree", action="store_true", help="leave the worktree the work rows name: the queue's session is still open in it")
    ld.add_argument("--lane", default="", help="the lane the landing is for: named on its spec-ok-proposed rows")
    ld.add_argument("--state", help="where the owner's journal lives (default: the owner's journal dir)")
    tr = sub.add_parser("triage", help="clean up the repo's GitHub metadata directly by the rules in harness.toml [triage]; --dry reads only")
    tr.add_argument("--labels", action="store_true", help="the closed label set only (step, type, priority, phase, needs-*, status:blocked); any other label is reported, never deleted, and its issues get what [triage.labels] maps it to")
    tr.add_argument("--specs", action="store_true", help="needs-spec on an issue inside a spec milestone that no spec cites, off one a spec cites; buckets left alone")
    tr.add_argument("--milestones", action="store_true", help="an issue goes to the milestone of the spec that cites it and loses its spec:* hint; a spec-less bug to Next release; empty milestones close; a spec-less milestone gets a write-the-spec issue")
    tr.add_argument("--assignees", action="store_true", help="the gh login on needs-your-decision / needs-your-test only; other assignees cleared")
    tr.add_argument("--order", action="store_true", help="read specs/build-order.md and print proposed lines for milestones it lacks; never writes it")
    tr.add_argument("--move", type=int, metavar="N", help="move issue N to the milestone --to, with --reason as its comment; never a close")
    tr.add_argument("--to", metavar="MILESTONE", help="the milestone --move moves the issue to (it must exist)")
    tr.add_argument("--close", type=int, metavar="N", help="close issue N as --as (not-planned default) with --reason as its comment; only with --owner-approved")
    tr.add_argument("--reason", default="", help="why the issue closes: its comment, word for word")
    tr.add_argument("--as", dest="close_as", choices=["not-planned", "completed", "duplicate"], default="not-planned")
    tr.add_argument("--owner-approved", action="store_true", help="the owner (or the manager by the owner's delegation) approved this close")
    tr.add_argument("--dry", action="store_true"), tr.add_argument("--gh", default="gh")
    tr.add_argument("--root", default=str(Path.cwd()), help="the checkout holding harness.toml and docs/contributor_manual/specs")
    tr.add_argument("--state", help="where the journal lives (default: the owner's journal dir)")
    q = sub.add_parser("queue", help="one long-running worker per lane, fed step by step: no action prints the steps; add; run (the owner-side loop; push only with --push); pause (no new step is fed); stop (the worker commits what is green and its session ends; the tree is kept); resume")
    q.add_argument("action", nargs="?", choices=["add", "run", "pause", "resume", "tell", "stop"])
    q.add_argument("--grace", type=float, default=300.0, help="stop: seconds the worker has to commit what is green before its session is closed")
    q.add_argument("--text", help="tell: the finding to put into the lane's live session"), q.add_argument("--file", help="tell: read the finding from this file")
    q.add_argument("--lane"), q.add_argument("--worktree"), q.add_argument("--step"), q.add_argument("--brief"), q.add_argument("--issues", type=int, nargs="*", default=[])
    q.add_argument("--hold", action="store_true", help="add: a milestone a person holds (the intake never takes this lane)")
    q.add_argument("--maintainer", action="store_true", help="add: a registered maintainer lane (the harness builder): its checks run --maintainer")
    q.add_argument("--pane", default="", help="add: the external lane's tmux pane, told its findings and LANDED")
    q.add_argument("--kind", choices=["worker", "external"], default="worker", help="add: external = a branch the loop starts no worker for; `builder done` is its DONE")
    q.add_argument("--push", action="store_true"), q.add_argument("--once", action="store_true"), q.add_argument("--tick", type=float, default=30.0)
    q.add_argument("--gh", default="gh", help="resume: the gh that takes needs-your-decision off the resumed steps' issues")
    q.add_argument("--lanes", type=int, default=1, help="run: how many build-order milestones are worked at once, each by its own long-running worker; an empty one gives its lane the next milestone no lane holds; checks stay one at a time")
    q.add_argument("--root", default=str(Path.cwd())), q.add_argument("--state", help="where the queue and the journal live (default: the owner's journal dir)")
    lp = sub.add_parser("loop", help="the continuous loop (dev-workflows.run.loop): `queue run --push` forever with a heartbeat row a tick; lanes and rounds from [loop]")
    lp.add_argument("--root", default=str(Path.cwd())), lp.add_argument("--state", help="where the queue and the journal live (default: the owner's journal dir)")
    lp.add_argument("--tick", type=float, default=30.0), lp.add_argument("--lanes", type=int, help="default [loop].lanes, else 1")
    dn = sub.add_parser("done", help="an external lane's DONE (dev-workflows.run.loop-external-lane): its step at <sha> goes to the check, review and landing")
    dn.add_argument("lane"), dn.add_argument("sha", nargs="?", default=""), dn.add_argument("--sha", dest="sha_opt", default="")
    dn.add_argument("--state", help="where the queue and the journal live (default: the owner's journal dir)")
    dn.add_argument("--no-presubmit", action="store_true", help="skip the lane's ready check with guards (the manager's call, e.g. a known-red guard)")
    cl = sub.add_parser("check-lane", help="the console's Run check (owner 2026-11-02): the pinned ladder over a lane's HEAD now, beside the loop; lands nothing")
    cl.add_argument("lane"), cl.add_argument("--root", default="."), cl.add_argument("--state", help="where the queue and the journal live")
    bc = sub.add_parser("build-check", help="the app's build rung over a lane's HEAD now, before its done: every error line with file:line and the log; a green result is reused by the ladder's build rung for the same tree; lands nothing")
    bc.add_argument("lane"), bc.add_argument("--root", default="."), bc.add_argument("--state", help="where the queue and the journal live")
    va = sub.add_parser("verify-all", help="everything on a checkout's HEAD verified before a dev DMG: every guard, the full engine suite (on [check].remote), the app build; one `verify` row; --build makes the dev DMG only after a green verdict")
    va.add_argument("--root", default="."), va.add_argument("--state", help="where the journal lives"), va.add_argument("--build", action="store_true")
    hv = sub.add_parser("heavy", help="run a heavy command (xcodebuild, a full pytest run) under the machine's one-heavy-job lock; waits, and says who holds it after 30 s: builder heavy -- <cmd>")
    hv.add_argument("--state", help="where the journal and the lock live"), hv.add_argument("argv", nargs=argparse.REMAINDER)
    hb = sub.add_parser("heartbeat", help="the loop's watchdog: an alert row when the journal has no `loop` tick for more than --ticks ticks (once per silence); exit 1 while stale")
    hb.add_argument("--state", help="where the queue and the journal live (default: the owner's journal dir)")
    hb.add_argument("--tick", type=float, default=30.0), hb.add_argument("--ticks", type=int, default=3)
    hb.add_argument("--restart", metavar="ROOT", help="on a new stale alert also kill the loop (loop.pid, with its children) and start `builder loop --root ROOT`, once per silence")
    la = sub.add_parser("launchd", help="write the owner's three LaunchAgents (the loop and the console with KeepAlive, started at login; the heartbeat watchdog every 3 ticks); --load also loads them")
    la.add_argument("--root", default=str(Path.cwd())), la.add_argument("--state"), la.add_argument("--tick", type=float, default=30.0)
    la.add_argument("--port", type=int, default=8766, help="the console's port"), la.add_argument("--load", action="store_true", help="launchctl bootout + bootstrap each agent")
    la.add_argument("--out", default=str(Path.home() / "Library" / "LaunchAgents"))
    al = sub.add_parser("alert", help="answer one alert row (dev-workflows.run.loop-alerts): retry | park | ask-owner, or approve | send-back for needs-maintainer")
    al.add_argument("id"), al.add_argument("action")
    al.add_argument("--state", help="where the queue and the journal live (default: the owner's journal dir)")
    al.add_argument("--gh", default="gh"), al.add_argument("--root", default=str(Path.cwd()), help="the checkout gh runs from (ask-owner)")
    bd = sub.add_parser("build", help="the dev DMG through the project's own script, as the owner: one journal row, the DMG's path and pass or fail; a full release is refused")
    bd.add_argument("--dev", action="store_true", help="required: the dev tier, no version stamp, no notarizing")
    bd.add_argument("--root", default=str(Path.cwd()), help="the checkout to build"), bd.add_argument("--state", help="where the journal and the log live (default: the owner's journal dir)")
    me = sub.add_parser("measure", help="run a script on a test machine against a lane's commit (git archive of its engine source): one measure row, told to the lane's pane")
    me.add_argument("--lane", required=True), me.add_argument("--machine", required=True), me.add_argument("--sha", default="")
    me.add_argument("--root", default=str(Path.cwd())), me.add_argument("--state"), me.add_argument("argv", nargs=argparse.REMAINDER)
    mc = sub.add_parser("machines", help="test machines: `sync <name>` installs the test plugins at the jail venv's exact pins into the machine's gate venv")
    mc.add_argument("action", choices=["sync"]), mc.add_argument("machine"), mc.add_argument("--root", default=str(Path.cwd())), mc.add_argument("--state")
    ins = sub.add_parser("install", help="copy the newest dev DMG to a [machines] test machine over ssh, install it in ~/Applications there, open it and say whether the app and its engine run")
    ins.add_argument("machine"), ins.add_argument("dmg", nargs="?", default=""), ins.add_argument("--root", default=str(Path.cwd())), ins.add_argument("--state")
    tl = sub.add_parser("tell", help="a message into a Claude Code pane, submitted; over 400 characters it goes to a file and the pane reads it")
    tl.add_argument("pane"), tl.add_argument("message", nargs="+"), tl.add_argument("--state")
    ts = sub.add_parser("test", help="the pinned pytest over test paths on the land branch's tip (or --head) in a scratch tree, as the jail user, local or [check].remote; one test row")
    ts.add_argument("paths", nargs="+"), ts.add_argument("--head", default=""), ts.add_argument("--root", default=str(Path.cwd())), ts.add_argument("--state")
    ln = sub.add_parser("lane", help="ticked issues as one lane: a cluster brief from them, queued as a worker lane in the jail (the console's Start as one lane)")
    ln.add_argument("name"), ln.add_argument("--issues", type=int, nargs="+", required=True), ln.add_argument("--root", default=str(Path.cwd()))
    ln.add_argument("--gh", default="gh"), ln.add_argument("--state")
    od = sub.add_parser("order", help="the owner's build order (JSON {order, parked}) as one commit on branch build-order, queued as a tiny batch the loop lands")
    od.add_argument("--file", required=True), od.add_argument("--root", default=str(Path.cwd())), od.add_argument("--state")
    au = sub.add_parser("auto", help="the day's auto decisions (the manager's audit): every `auto` journal row by rule, with head, file and why")
    au.add_argument("--day", default="", help="YYYY-MM-DD (default: today)"), au.add_argument("--state")
    au.add_argument("--root", default=str(Path(__file__).resolve().parents[2]), help="the checkout whose specs say what is folded")
    ss = sub.add_parser("sweep-scratch", help="the ladders' old scratch dirs in the jail's workroot: --list writes the list (deletes nothing), --delete FILE removes exactly those, each re-checked")
    g = ss.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true"), g.add_argument("--delete", metavar="FILE")
    ss.add_argument("--retain-h", type=float, default=6.0), ss.add_argument("--root", default=str(Path.cwd())), ss.add_argument("--state")
    sw = sub.add_parser("sweep", help="clean up one landed worktree through the landing's sweep: a patch first, git worktree remove, never rm; a jail tree as the worker")
    sw.add_argument("--worktree", required=True), sw.add_argument("--root", default=str(Path.cwd())), sw.add_argument("--state")
    cs = sub.add_parser("status", help="the owner's console on 127.0.0.1: lanes live, alerts with their actions, Build, loop start/stop; /api/status, /api/events, POST /api/action onto the existing verbs")
    cs.add_argument("--port", type=int, default=8766), cs.add_argument("--state", help="where the queue and the journal live (default: the owner's journal dir)")
    cs.add_argument("--root", default=str(Path.cwd()), help="the checkout whose harness.toml the verbs read")
    w = sub.add_parser("work", help="run, patches, fetch, check, review, land as one process; stops with QUESTION: (exit 2), never pushes")
    w.add_argument("--brief", required=True), w.add_argument("--worktree", required=True), w.add_argument("--name", required=True)
    w.add_argument("--kind", default="claude", choices=["claude"])
    w.add_argument("--issues", type=int, nargs="+", required=True)
    w.add_argument("--pinned", help="override: the pinned copy to read the rules from (default [land].pinned_dir/pinned-<base7> of --root's harness.toml, made from the engine repo when missing)")
    w.add_argument("--base", help="the base sha (default: the brief's first line `(base <sha>)`)")
    w.add_argument("--ids", nargs="+", default=[], help="the item's behaviour ids: protected from a rewrite of their spec acceptance")
    w.add_argument("--repo", help="the engine-owned repo (default [check].engine_repo of the pinned rules)")
    w.add_argument("--model", help="the builder's model (default [models].builder)")
    w.add_argument("--root", default=str(Path.cwd())), w.add_argument("--session", default="harness")
    w.add_argument("--tick", type=float, default=30.0)
    w.add_argument("--state", help="where the journal, patches, ladder and verdicts live (default: the owner's journal dir)")
    st = sub.add_parser("steps", help="file one issue per build-order step of an APPROVED spec under its milestone; a second run updates")
    st.add_argument("--spec", required=True), st.add_argument("--gh", default="gh"), st.add_argument("--dry-run", action="store_true")
    st.add_argument("--state", help="where the journal lives (default: the owner's journal dir)")
    fl = sub.add_parser("file", help="a milestone and one issue under it from a brief (created if absent, edited by exact title otherwise); --dry-run writes nothing; never pushes")
    fl.add_argument("--milestone", required=True), fl.add_argument("--title", required=True), fl.add_argument("--body-file", required=True)
    fl.add_argument("--label", action="append", default=[]), fl.add_argument("--gh", default="gh"), fl.add_argument("--dry-run", action="store_true")
    fl.add_argument("--state", help="where the journal lives (default: the owner's journal dir)")
    sp = sub.add_parser("spec", help="write the spec-writer's brief for an issue to FILE; starts no worker")
    sp.add_argument("--issue", type=int, required=True), sp.add_argument("--out", required=True), sp.add_argument("--gh", default="gh")
    sp.add_argument("--root", default=str(Path.cwd()), help="the checkout holding harness.toml and the spec template")
    sp.add_argument("--state", help="where the journal lives (default: the owner's journal dir)")
    a = ap.parse_args(argv)
    if a.cmd == "milestone":
        import tomllib

        from fichero_builder import brief_tool, codemap, milestone, queue, triage

        journal.STATE = Path(a.state) if a.state else journal.STATE
        if not (Path(a.repo_dir) / "harness.toml").is_file():  # a refusal with a row, never a traceback (real use 2026-11-02)
            print(f"REFUSED: {a.repo_dir} has no harness.toml: --repo-dir must be a checkout of the project")
            journal.append("milestone", refused="rules", detail=f"no harness.toml in {a.repo_dir}")
            return 1
        if not a.name:
            try:
                a.name, spec = triage.first_open(a.repo_dir, a.gh)
            except triage.Refused as e:
                print(f"REFUSED: {e}")
                return 1
            a.spec = a.spec or str(spec)
            print(f"milestone {a.name} (first in build-order.md), spec {a.spec}")
        if not a.spec:
            print("REFUSED: --spec is needed when the milestone is named")
            return 1
        order = milestone.build_order(a.spec)
        planned = milestone.plan(milestone.list_issues(a.name, gh=a.gh), order, milestone.spec_slug(a.spec))
        rules_doc = tomllib.loads((Path(a.repo_dir) / "harness.toml").read_text())
        base = a.base or resolve(a.repo_dir, "origin/" + rules_doc.get("land", {}).get("branch", ""))
        rules = rules_doc.get("brief", {}).get("rules", "")
        written = milestone.write_briefs(planned, out=a.out, repo_dir=a.repo_dir, base=base, rules=rules,
                                         fetch=lambda n: brief_tool.fetch_issue(n, gh=a.gh), cluster=brief_tool.cluster,
                                         spec_path=a.spec, binary=codemap.owner_binary(a.repo_dir), lane=queue.slug(a.name) if a.enqueue else "")
        for c, p in zip(planned["clusters"], written):
            print(f"Step {c['step']}: {', '.join('#%d' % i['number'] for i in c['issues'])} -> {p}")
        if a.enqueue:
            journal.STATE = Path(a.state) if a.state else journal.STATE
            workroot = rules_doc.get("jail", {}).get("workroot", "")
            lane = queue.slug(a.name)
            for c, p in zip(planned["clusters"], written):
                queue.add(lane, str(Path(workroot) / f"wt-{lane}"), c["step"], str(p), [i["number"] for i in c["issues"]], waits=c["waits"])
        for q in planned["questions"]:
            print(f"QUESTION: {q}", file=sys.stderr)
        return 0 if not planned["questions"] else 2
    # run (as the worker) journals under the shared workroot; check and land (as the owner) keep the owner's own journal,
    # because land trusts the check row: a journal the worker can write would let a worker forge one.
    journal.STATE = state_dir(a.root, a.state) if a.cmd == "run" else (Path(a.state) if a.state else journal.STATE)
    if a.cmd == "work":
        return work.main(a)
    if a.cmd == "triage":
        from fichero_builder import triage

        return triage.main(a)
    if a.cmd == "build":
        from fichero_builder import build

        return build.main(a)
    if a.cmd == "alert":
        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        rc, msg = queue.answer(a.id, a.action, gh=a.gh, cwd=a.root)
        print(msg)
        return rc
    if a.cmd == "heavy":
        import subprocess

        argv = [x for i, x in enumerate(a.argv) if not (i == 0 and x == "--")]
        if not argv:
            print("REFUSED: builder heavy -- <command>")
            return 2
        with journal.heavy("heavy: " + " ".join(argv)[:80]):
            return subprocess.run(argv, env={**os.environ, journal.HEAVY_ENV: "1"}).returncode
    if a.cmd == "verify-all":
        from fichero_builder import verify

        journal.STATE = Path(a.state) if a.state else journal.STATE
        return verify.main(a)
    if a.cmd == "build-check":
        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        rc, msg = queue.build_head(a.root, a.lane)
        print(msg)
        return rc
    if a.cmd == "check-lane":
        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        rc, msg = queue.check_head(a.root, a.lane)
        print(msg)
        return rc
    if a.cmd == "done":
        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        if not a.no_presubmit:  # speed batch 2: the guards' reds die in the lane, before a ladder is spent
            ok, said = queue.presubmit(a.lane, a.sha_opt or a.sha)
            if not ok:
                print(f"REFUSED: the presubmit ([check].ready with its guards) is red; fix it, then done again:\n{said[-3000:]}")
                return 1
            if said.startswith(("presubmit skipped", "presubmit green but")):
                print(said.splitlines()[0])
        why = queue.done(a.lane, a.sha_opt or a.sha)
        paused = not why and any(x["id"] == a.lane and x.get("paused") for x in queue.load())
        print(f"REFUSED: {why}" if why else f"{a.lane}: DONE at {(a.sha_opt or a.sha or 'its HEAD')[:12]}, snapshot in land-{a.lane}; "
              + ("the lane is PAUSED: the head is recorded and waits for `builder queue resume`" if paused else "the loop checks it next tick"))
        return 1 if why else 0
    if a.cmd == "heartbeat":
        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        aid = queue.heartbeat_check(a.tick, a.ticks)
        if aid:
            print(f"ALERT {aid}: the loop's heartbeat is stale")
            if a.restart:
                print(f"loop restarted, pid {queue.restart_loop(a.restart, a.tick)}")
        return 1 if aid else 0
    if a.cmd == "launchd":
        from fichero_builder import queue

        paths = queue.launch_agents(a.root, a.out, state=a.state, tick_s=a.tick, port=a.port)
        for path in paths:
            print(f"wrote {path}" + ("" if a.load else f"\nload: launchctl bootstrap gui/$(id -u) {path}"))
        lines = queue.load_agents(paths) if a.load else []
        print("\n".join(lines)) if lines else None
        return 1 if any(ln.startswith("FAILED") for ln in lines) else 0
    if a.cmd == "loop":
        import tomllib

        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        if pid := queue.other_loop():  # a launchd loop at login beside a hand-started one: never two (KeepAlive retries it)
            print(f"REFUSED: a loop already runs (pid {pid}, loop.pid)")
            return 1
        f = Path(a.root) / "harness.toml"
        cfg = tomllib.loads(f.read_text()).get("loop", {}) if f.is_file() else {}
        queue.ROUNDS = int(cfg.get("rounds", queue.ROUNDS))
        lanes_n = max(1, a.lanes or int(cfg.get("lanes", 1)))
        try:
            procs = queue.real_procs(a.root)
        except Exception as e:  # noqa: BLE001 - a rules file that cannot run the loop is a row and a line, never a traceback
            print(f"REFUSED: the rules file cannot run the loop: {e}")
            journal.append("loop", state="refused", detail=str(e)[-300:])
            return 1
        # manager 2026-11-04: a fresh loop (the LaunchAgent) took an old build-order milestone the hand loop had long skipped and started a
        # worker on steps lane-sharing had landed: the lanes are named in [loop].only, and milestones are taken only when feed_milestones is on
        queue.ONLY[0] = tuple(cfg.get("only", ()))
        return queue.run(procs, workers_n=max(queue.workers(a.root), lanes_n), push=True, lanes_n=lanes_n, tick_s=a.tick, forever=True, heartbeat=True,
                         feed_milestones=bool(cfg.get("feed_milestones", False)))
    if a.cmd == "queue":
        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        return queue.main(a)
    if a.cmd == "measure":
        from fichero_builder import measure

        journal.STATE = Path(a.state) if a.state else journal.STATE
        return measure.main(a)
    if a.cmd == "machines":
        from fichero_builder import measure

        journal.STATE = Path(a.state) if a.state else journal.STATE
        rc, out = measure.sync(a.root, a.machine)
        print(out)
        return rc
    if a.cmd == "install":
        from fichero_builder import measure

        journal.STATE = Path(a.state) if a.state else journal.STATE
        rc, out = measure.install(a.root, a.machine, a.dmg)
        print(out)
        return rc
    if a.cmd == "tell":
        from fichero_builder import tell

        journal.STATE = Path(a.state) if a.state else journal.STATE
        return tell.main(a)
    if a.cmd == "test":
        import subprocess
        import tomllib

        journal.STATE = Path(a.state) if a.state else journal.STATE
        doc = tomllib.loads((Path(a.root) / "harness.toml").read_text())
        repo, branch = doc["check"]["engine_repo"], doc["land"]["branch"]
        subprocess.run(["git", "-C", repo, "fetch", "-q", "origin", branch], capture_output=True)
        head = a.head or f"origin/{branch}"
        r = check_tool.run_tests(repo, head, a.root, a.paths)
        journal.append("test", head=head, paths=a.paths, ok=bool(r.get("ok")), seconds=r.get("seconds"), remote=r.get("remote", ""),
                       detail=(r.get("stdout_tail") or "")[-600:])
        print(r.get("stdout_tail", "")[-3000:])
        return 0 if r.get("ok") else 1
    if a.cmd == "lane":
        from fichero_builder import queue

        journal.STATE = Path(a.state) if a.state else journal.STATE
        rc, out = queue.lane_from_issues(a.root, a.name, a.issues, gh=a.gh)
        print(out)
        return rc
    if a.cmd == "order":
        from fichero_builder import order

        journal.STATE = Path(a.state) if a.state else journal.STATE
        return order.main(a)
    if a.cmd == "auto":
        import collections
        import time as _t

        journal.STATE = Path(a.state) if a.state else journal.STATE
        day = a.day or _t.strftime("%Y-%m-%d")
        rows = [r for r in journal.read() if r.get("event") == "auto" and str(r.get("ts", "")).startswith(day)]
        by = collections.defaultdict(list)
        for r in rows:
            by[r.get("rule", "?")].append(r)
        print(f"{len(rows)} auto decision(s) on {day}" + ("" if rows else ": none"))
        for rule, rs in sorted(by.items()):
            print(f"\n{rule}: {len(rs)}")
            for r in rs:
                print(f"  {r.get('ts', '')[11:19]} {str(r.get('head', ''))[:9]} {r.get('file', '')}: {r.get('detail', '')}")
        from fichero_builder import landed
        open_ = landed.unfolded_proposals(a.root, journal.read())
        print(f"\nspec-ok proposals not folded yet (any day): {len(open_)}")
        for r in open_:
            print(f"  {r.get('lane') or '?'} {str(r.get('sha', ''))[:9]} {r['file']}: `{r['id']}` [OK]" + (f" Tests: {', '.join(r.get('tests') or [])}" if r.get("tests") else ""))
        return 0
    if a.cmd == "sweep-scratch":
        from fichero_builder import scratch

        journal.STATE = Path(a.state) if a.state else journal.STATE
        return scratch.main(a)
    if a.cmd == "sweep":
        from fichero_builder import landed

        journal.STATE = Path(a.state) if a.state else journal.STATE
        rc, out = landed.sweep_one(a.root, a.worktree)
        print(out)
        return rc
    if a.cmd == "status":
        from fichero_builder import console

        return console.main(a)
    if a.cmd == "landed":
        from fichero_builder import landed

        return landed.main(a)
    if a.cmd == "spec":
        try:
            model = models.for_role(models.load(a.root), "spec-writer")
            spec_tool.run(a.issue, a.out, a.root, gh=a.gh)
        except models.Question as e:
            print(f"QUESTION: {e}")
            return 2
        except (RuntimeError, OSError) as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        journal.append("spec", issue=a.issue, out=a.out, model=model.model)
        print(f"wrote {a.out} for the spec-writer ({model.provider}/{model.model}); start it with `builder run --brief {a.out}`")
        return 0
    if a.cmd == "steps":
        try:
            steps.run(a.spec, gh=a.gh, dry_run=a.dry_run)
        except (steps.Refused, OSError, ValueError) as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "file":
        from fichero_builder import file_tool

        try:
            file_tool.run(milestone=a.milestone, title=a.title, body=Path(a.body_file).read_text(), labels=a.label, gh=a.gh, dry_run=a.dry_run)
        except (steps.Refused, OSError, ValueError) as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "land":
        from fichero_builder import land_tool

        if problem := land_tool.log_problem(a.log):  # first: every later refusal writes here
            print(f"REFUSED (log): {problem}", file=sys.stderr)
            journal.append("land", head=a.head, refused="log", detail=problem)
            return 1
    if a.cmd in ("check", "land") and not a.repo:
        try:
            a.repo = check_tool.load(a.pinned).engine_repo
        except (ValueError, OSError) as e:  # a bad rules file is a refusal with a row, never a traceback
            print(f"REFUSED (rules file):\n  {e}", file=sys.stderr)
            if a.cmd == "land":
                with open(a.log, "a") as f:
                    f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "refused": "rules", "detail": [str(e)]}) + "\n")
            return 1
        if not a.repo:
            print("REFUSED: no --repo and no [check].engine_repo in the pinned rules", file=sys.stderr)
            return 1
    if a.cmd == "land":  # the green check row is the ladder's result for this head; the verb adds the verdict and the boundary only
        from fichero_builder import land_tool

        if problems := check_tool.rules_problems(a.pinned):  # the rules file first: cheap and fail-closed, before any read of the journal
            print("REFUSED (rules file):\n  " + "\n  ".join(problems), file=sys.stderr)
            land_tool.safe_append(a.log, json.dumps({"at": time.time(), "land": a.head, "refused": "rules", "detail": problems}) + "\n")
            return 1
        head = resolve(a.repo, a.head)
        if problem := land_tool.journal_problem(journal.path()):  # land trusts this file: it must be the caller's own (review 1 N2)
            print(f"REFUSED (journal): {problem}; land reads only the owner's journal", file=sys.stderr)
            return 1
        if not head or not checked(a.repo, a.pinned, head):
            print(f"REFUSED: no green `builder check` row over the land branch..{head[:9] or a.head} in {journal.path()}; run builder check first", file=sys.stderr)
            return 1
        ok, out = land_tool.gate(a.repo, head, a.pinned, a.verdicts, a.log)
        print(out, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if a.cmd == "check":
        head = resolve(a.repo, a.head)  # before the ladder: a commit made meanwhile never gets the row (review 1 M5)
        if not head:
            print(f"builder check: {a.head!r} is not a commit in {a.repo}", file=sys.stderr)
            return 1
        since = resolve(a.repo, a.since)
        if not since:
            print(f"builder check: {a.since!r} is not a commit in {a.repo}", file=sys.stderr)
            return 1
        try:
            check_tool.ACTIVITY = lambda **kw: journal.append("activity", lane="by hand", **kw)  # console view A sees a check run by hand
            check_tool.GUARD_CACHE[0] = journal.STATE / "guard-cache.json"  # speed 5: a guard's green is reused for the same inputs
            r = check_tool.ladder_over(a.repo, since, head, a.pinned, a.id, maintainer=a.maintainer, approve_weakened=a.approve_weakened, approve_red=a.approve_red,
                                       approve_pinned_new=a.approve_pinned_new, guard_data=tuple(a.guard_data))
        except check_tool.EmptyRange:  # the shared refusal, also `builder work`'s
            print(f"REFUSED: {a.since}..{a.head} is empty: nothing to check", file=sys.stderr)
            return 1
        print(json.dumps(r, indent=1))
        journal.append("check", repo=str(a.repo), since=since, head=head, ok=bool(r.get("ok")), failed=r.get("failed", ""), maintainer=a.maintainer,
                       approve_weakened=a.approve_weakened)
        return 0 if r.get("ok") else 1
    if a.cmd == "run" and not a.model:
        from fichero_builder import models as models_mod

        try:
            a.model = models_mod.for_role(models_mod.load(a.root), "builder").model
        except models_mod.Question as e:
            print(f"builder run refuses: {e}", file=sys.stderr)
            return 1
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
                      tick_s=a.tick, procs=procs, handoff=a.handoff, feed=a.feed, seq=a.seq)
    return 0 if end in ("done", "done-unsaid", "lane-done", "gone", "parked") else 1  # a clean end is 0; "refused" is the 1


if __name__ == "__main__":
    sys.exit(main())
