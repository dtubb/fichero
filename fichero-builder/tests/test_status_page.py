"""dev-workflows.run.loop-status: `builder status` (= `builder watch`) shows lanes, the last check and landing, issues closed
today, spend today and open alerts, from the journal and the queue only; the same as JSON at /status.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import console, journal, watch

DAY = "2026-11-02"
ROWS = [
    {"ts": "2026-11-01T23:00:00", "event": "cost", "task": "a", "usd": 9.0},
    {"ts": "2026-11-01T23:10:00", "event": "landed", "sha": "e" * 40, "step": "done", "ok": True, "branch": "integration", "pushed": True, "issues": [1], "left_open": []},
    {"ts": f"{DAY}T09:00:00", "event": "cost", "task": "a", "usd": 1.25},
    {"ts": f"{DAY}T09:30:00", "event": "cost", "task": "b", "usd": 0.5},
    {"ts": f"{DAY}T10:00:00", "event": "check", "since": "a" * 40, "head": "b" * 40, "ok": True, "failed": None},
    {"ts": f"{DAY}T10:30:00", "event": "landed", "sha": "c" * 40, "step": "done", "ok": True, "branch": "integration", "pushed": True, "issues": [7, 8], "left_open": [8]},
    {"ts": f"{DAY}T11:00:00", "event": "alert", "id": "a-s1-1", "lane": "a", "step": "s1", "what": "red at pytest", "actions": ["retry", "park"]},
    {"ts": f"{DAY}T11:05:00", "event": "alert", "id": "b-s2-2", "lane": "b", "step": "s2", "what": "a question", "actions": ["ask-owner"]},
    {"ts": f"{DAY}T11:10:00", "event": "alert-answer", "id": "a-s1-1", "action": "retry", "ok": True},
    {"ts": f"{DAY}T11:11:00", "event": "alert-answer", "id": "b-s2-2", "action": "retry", "ok": False},
]
def _s(step, state):
    return {"step": step, "state": state, "issues": [7], "why": "", "brief": "/nonexistent/brief"}


LANES = [
    {"id": "a", "worktree": "/nonexistent/a", "cursor": 1, "paused": False, "kind": "worker", "steps": [_s("s0", "landed"), _s("s1", "running")]},
    {"id": "b", "worktree": "/nonexistent/b", "cursor": 1, "paused": True, "kind": "external", "steps": [_s("s2", "landed")]},
]


def test_a_journal_of_fixed_rows_gives_that_status_and_that_page():
    st = watch.status(ROWS, LANES, today=DAY)
    assert st["lanes"] == [{"lane": "a", "kind": "worker", "paused": False, "done": False, "step": "s1", "state": "running"},
                           {"lane": "b", "kind": "external", "paused": True, "done": True, "step": "-", "state": "done"}]
    assert st["last_check"]["head"] == "b" * 40 and st["last_check"]["ok"] is True
    assert st["last_land"] == {"ts": f"{DAY}T10:30:00", "sha": "c" * 40, "branch": "integration", "pushed": True}
    assert st["issues_closed_today"] == [7], "yesterday's #1 and the left-open #8 are not closed today"
    assert st["spend_today_usd"] == 1.75, "yesterday's cost is not today's"
    assert [a["id"] for a in st["open_alerts"]] == ["b-s2-2"], "an alert stays open until an answer that took"
    page = watch.render(ROWS, LANES)
    assert "Open alerts" in page and "b-s2-2" in page and "a question" in page and "(paused)" in page


def test_status_json_is_served_on_the_loopback(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    (tmp_path / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    monkeypatch.setattr(watch, "_lanes", lambda: LANES)
    srv = watch.server("127.0.0.1", 0)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    resp = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/status.json", timeout=5)
    assert resp.headers["Content-Type"] == "application/json"
    st = json.loads(resp.read())
    assert [x["lane"] for x in st["lanes"]] == ["a", "b"] and [a["id"] for a in st["open_alerts"]] == ["b-s2-2"]


def test_the_status_verb_serves_the_console_and_watch_keeps_the_page(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(console, "server", lambda host, port: (seen.update(host=host, port=port), _Stub())[1])
    assert cli.main(["status", "--port", "9998", "--state", str(tmp_path)]) == 0
    assert seen == {"host": "127.0.0.1", "port": 9998}


class _Stub:
    server_address = ("127.0.0.1", 9998)

    def serve_forever(self):
        pass


@pytest.fixture
def live(tmp_path, monkeypatch):
    """A console on an ephemeral loopback port over a fake journal and queue; verbs go to a fake runner."""
    monkeypatch.setattr(journal, "STATE", tmp_path)
    (tmp_path / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    monkeypatch.setattr(console.queue, "load", lambda: LANES)
    monkeypatch.setattr(console, "ROOT", tmp_path)
    ran = []
    monkeypatch.setattr(console, "run_verb", lambda argv: ran.append(argv) or (0, "ok"))
    monkeypatch.setattr(console, "EVENT_POLL_S", 0.05)
    srv = console.server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", ran
    srv.shutdown()


def _post(url, body, token=None, host=None):
    req = urllib.request.Request(url + "/api/action", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Builder-Token": token} if token else {}), **({"Host": host} if host else {})})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _wait(pred):
    for _ in range(100):
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_the_api_status_has_the_lanes_steps_spend_alerts_review_and_heartbeat(live):
    url, _ = live
    st = json.loads(urllib.request.urlopen(url + "/api/status", timeout=5).read())
    a, b = st["lanes"]
    assert a["lane"] == "a" and a["step"] == "s1" and [s["step"] for s in a["steps"]] == ["s0", "s1"] and a["usd"] == 1.25 + 9.0
    assert [x["id"] for x in st["open_alerts"]] == ["b-s2-2"] and st["spend_today_usd"] >= 0 and "heartbeat" in st and "last_review" in st
    page = urllib.request.urlopen(url + "/", timeout=5).read().decode()
    assert console.TOKEN in page and "__TOKEN__" not in page and "htm@3.1.1/preact/standalone" in page, "the token is in the page; Preact pinned"


def test_each_action_calls_its_existing_verb_and_writes_rows_naming_who(live):
    url, ran = live
    for verb, args, want in [("pause", {"lane": "a"}, ["queue", "pause", "--lane", "a"]),
                             ("resume", {"lane": "a"}, ["queue", "resume", "--lane", "a"]),
                             ("stop", {"lane": "a"}, ["queue", "stop", "--lane", "a"]),
                             ("alert", {"id": "b-s2-2", "action": "retry"}, ["alert", "b-s2-2", "retry"]),
                             ("build", {}, ["build", "--dev"]),
                             ("done", {"lane": "b", "sha": "abc123"}, ["done", "b", "abc123"]),
                             ("queue-add", {"lane": "c", "worktree": "/w/c", "step": "1.1", "brief": "/b/1.1", "issues": [5, 6]},
                              ["queue", "add", "--lane", "c", "--worktree", "/w/c", "--step", "1.1", "--brief", "/b/1.1"])]:
        code, body = _post(url, {"verb": verb, "args": args}, console.TOKEN)
        assert code == 200 and body["ok"], (verb, body)
        assert _wait(lambda: len(ran) and ran[-1][3:3 + len(want)] == want), (verb, ran[-1])
    assert ran[-1][-3:] == ["--issues", "5", "6"]
    code, _ = _post(url, {"verb": "loop-start"}, console.TOKEN)
    assert code == 200 and _wait(lambda: ran[-1][:2] == ["launchctl", "bootstrap"])
    assert _wait(lambda: sum(1 for r in journal.read() if r["event"] == "console" and r["state"] == "ended") == 8)
    rows = [r for r in journal.read() if r["event"] == "console"]
    assert all(r["who"].endswith("@console") for r in rows) and {r["verb"] for r in rows} >= {"pause", "build", "loop-start"}


def test_a_missing_token_a_foreign_host_and_an_unlisted_verb_or_a_flag_value_are_refused_with_a_row(live):
    url, ran = live
    assert _post(url, {"verb": "build"})[0] == 403, "no token"
    assert _post(url, {"verb": "build"}, console.TOKEN, host="evil.example:80")[0] == 403, "a foreign Host (DNS rebinding)"
    code, body = _post(url, {"verb": "rm", "args": {}}, console.TOKEN)
    assert code == 400 and "not a console verb" in body["error"]
    code, body = _post(url, {"verb": "pause", "args": {"lane": "--push"}}, console.TOKEN)
    assert code == 400 and "never a flag" in body["error"]
    assert ran == []
    assert [r["state"] for r in journal.read() if r["event"] == "console"] == ["refused"] * 4


def test_events_stream_each_new_journal_row(live):
    url, _ = live
    resp = urllib.request.urlopen(url + "/api/events", timeout=5)
    journal.append("queue", lane="a", step="s1", state="checking", detail="")
    line = b""
    while not line.startswith(b"data: "):
        line = resp.readline()
    assert json.loads(line[6:])["state"] == "checking"
    resp.close()


def test_milestones_come_by_section_with_counts_steps_and_issues_and_start_calls_milestone_enqueue(tmp_path, monkeypatch, live):
    """Milestones view: the build-order list (In order, Then, Parked), open/closed counts from one gh read, an In order
    milestone's steps (done / running / next / waiting) and open issues with labels and step; Start lane = `milestone --enqueue`."""
    from fichero_builder import milestone as ms
    spec_dir = tmp_path / "docs" / "contributor_manual" / "specs"
    spec_dir.mkdir(parents=True)
    (spec_dir / "build-order.md").write_text("# Build order\n\n## In order\n\n1. `Alpha` Spec: alpha.md\n2. `Beta` Spec: beta.md\n\n"
                                             "## Then (unordered)\n\n- `Gamma`\n\n## Parked\n\n- `Delta`\n")
    (spec_dir / "alpha.md").write_text("> Milestone: alpha\n")
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\necho '[{\"title\":\"Alpha\",\"open_issues\":2,\"closed_issues\":5},{\"title\":\"Gamma\",\"open_issues\":1,\"closed_issues\":0}]'\n")
    gh.chmod(0o755)
    issues = [{"number": 11, "title": "alpha Step 1.2: b", "body": "", "labels": [{"name": "step:1.2"}, {"name": "bug"}]},
              {"number": 12, "title": "alpha Step 1.3: c", "body": "", "labels": [{"name": "step:1.3"}]}]
    monkeypatch.setattr(ms, "list_issues", lambda name, gh="gh": issues if name == "Alpha" else [])
    monkeypatch.setattr(ms, "build_order", lambda p: [{"number": n, "title": t, "depends_on": d} for n, t, d in
                                                      [("1.1", "a", []), ("1.2", "b", []), ("1.3", "c", ["1.2"])]])
    lanes = [{"id": "alpha", "worktree": "/w", "cursor": 0, "steps": [{"step": "1.2", "state": "sent"}]}]
    d = console.milestones(tmp_path, gh=str(gh), lanes=lanes, reads=lambda root, ls, br: ({}, "", set()), closed=lambda name: [])
    by = {m["name"]: m for m in d["milestones"]}
    assert [(m["name"], m["section"]) for m in d["milestones"]] == [("Alpha", "In order"), ("Beta", "In order"), ("Gamma", "Then"), ("Delta", "Parked")]
    a = by["Alpha"]
    assert (a["open"], a["closed"], a["lane"]) == (2, 5, "alpha") and by["Gamma"]["open"] == 1 and by["Delta"]["open"] is None
    assert [(s["step"], s["state"]) for s in a["steps"]] == [("1.1", "done"), ("1.2", "running"), ("1.3", "waiting")]
    assert {k: a["issues"][0][k] for k in ("number", "title", "labels", "step")} == {"number": 11, "title": "alpha Step 1.2: b", "labels": ["step:1.2", "bug"], "step": "1.2"}
    assert d["ts"] and d["gh_ok"]
    url, ran = live
    assert json.loads(urllib.request.urlopen(url + "/api/milestones", timeout=5).read())["milestones"] == [], "nothing read yet: the cache, never gh"
    code, _ = _post(url, {"verb": "start-milestone", "args": {"milestone": "UX - Library"}}, console.TOKEN)
    assert code == 200 and _wait(lambda: ran and ran[-1][3:6] == ["milestone", "UX - Library", "--enqueue"])


def test_an_external_lane_is_working_or_idle_by_its_head_the_title_skips_rules_and_a_silent_loop_is_off(tmp_path):
    """Owner 2026-11-02: an external lane read 'queued' while it committed every few minutes; the step title showed the
    RULES preamble; 'heartbeat none' said nothing plain."""
    brief = tmp_path / "b.md"
    brief.write_text("RULES: you are a long-running builder. Read AGENTS.md first.\nLANE sharing, branch lane-sharing. Spec: x.md\n")
    lanes = [{"id": n, "worktree": str(tmp_path), "cursor": 0, "paused": False, "kind": "external",
              "steps": [{"step": "2.3", "state": "queued", "issues": [], "why": "", "brief": str(brief)}]} for n in ("busy", "quiet")]
    now = time.time()
    ticks = [{"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 600)), "event": "loop", "state": "tick"}]
    st = console.api_status(ticks, lanes, now=now, commit=lambda wt: ("abc fix (1 minute ago)", int(now - 60)))
    assert st["lanes"][0]["state"] == "working" and st["lanes"][0]["title"] == "LANE sharing, branch lane-sharing"
    assert st["loop_on"] is False, "the last tick is ten minutes old"
    st = console.api_status([], lanes, now=now, commit=lambda wt: ("abc fix (1 hour ago)", int(now - 3600)))
    assert st["lanes"][1]["state"] == "idle" and st["loop_on"] is False
    st = console.api_status([{**ticks[0], "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 20))}], lanes, now=now, commit=lambda wt: ("", 0))
    assert st["loop_on"] is True


def test_each_issue_and_step_has_one_status_from_git_and_gh_and_start_is_offered_only_where_nothing_is_built():
    """Owner 2026-11-02: 'done but not landed' was invisible; a milestone whose lane built everything still offered Start."""
    log = lambda *cs: "".join(f"\x1e{sha}\x00subject\n\n{body}\n" for sha, body in cs)  # noqa: E731
    st = console.statuses({1, 2, 3}, {4, 5},
                          {"lane-a": log(("a" * 40, "Part of #1"), ("b" * 40, "Fixes #2\nPart of #1"))},
                          log(("c" * 40, "Fixes #4"), ("d" * 40, "Closes #5")), {"d" * 40})
    assert st[1] == ("in progress", "lane-a aaaaaaaaa") and st[2] == ("built, waiting to land", "lane-a bbbbbbbbb")
    assert st[3] == ("open", "") and st[4] == ("released", "ccccccccc") and st[5] == ("landed", "ddddddddd")
    assert [r for r in console.RANK] == ["open", "in progress", "built, waiting to land", "landed", "released"], "lowest first: a step takes the lowest"


def test_worktrees_lists_each_tree_and_clean_up_sweeps_only_a_landed_clean_one_with_a_patch(tmp_path, monkeypatch):
    """View E (owner 2026-11-02): every worktree with branch, last commit, dirty, landed and the grace deadline; Clean up goes
    through the landing's sweep (`builder sweep --worktree`): a patch first, `git worktree remove`, never rm."""
    import subprocess

    from fichero_builder import landed
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(landed, "live_worktrees", lambda: set())
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    g(repo, "init", "-q", "-b", "main")
    (repo / "harness.toml").write_text('[land]\nbranch = "integration"\nworktree_grace_hours = 36\n')
    g(repo, "add", "."), g(repo, "commit", "-qm", "base")
    g(repo, "update-ref", "refs/remotes/origin/integration", "HEAD")
    g(repo, "worktree", "add", "-q", "-b", "done-lane", str(tmp_path / "done"), "HEAD")
    g(repo, "worktree", "add", "-q", "-b", "busy-lane", str(tmp_path / "busy"), "HEAD")
    (tmp_path / "busy" / "wip.txt").write_text("uncommitted")
    d = console.worktrees(repo)
    by = {Path(t["path"]).name: t for t in d["trees"]}
    assert by["repo"]["where"] == "checkout (main tree)" and not by["repo"]["can_clean"]
    assert by["done"]["landed"] and not by["done"]["dirty"] and by["done"]["can_clean"] and by["done"]["branch"] == "done-lane" and by["done"]["grace_until"]
    assert by["busy"]["dirty"] and not by["busy"]["can_clean"], "a dirty tree is never offered"
    rc, out = landed.sweep_one(repo, str(tmp_path / "done"))
    assert rc == 0 and not (tmp_path / "done").exists() and "patch" in out
    assert g(repo, "branch", "--list", "done-lane"), "the branch stays"
    (row,) = [r for r in journal.read() if r["event"] == "sweep"]
    assert row["ok"] and row["worktree"].endswith("done")
    assert console.argv_for("sweep", {"worktree": "/w/x"})[3:6] == ["sweep", "--worktree", "/w/x"]


def test_an_external_lanes_step_and_progress_come_from_its_newest_commit_and_its_specs_build_order(tmp_path):
    """Order 8 + manager defect 2026-11-02: lane-sharing showed its queue step 'sharing-2.3' while its HEAD was workflows Step 1.4.
    The step comes from the newest commit (`Step X.Y`, else the step whose Build order section names its `Behaviour:`), and
    i/N from that spec's build order in the lane's own tree."""
    import subprocess

    def g(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True, capture_output=True)
    spec = tmp_path / "docs/contributor_manual/specs/ui/flows.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("> Milestone: flows\n\n## Build order\n\n#### Step 1.1 — a\n- Behaviours: `flows.a`\n\n#### Step 1.2 — b\n- Behaviours: `flows.b`\n")
    g("init", "-q", "-b", "main"), g("add", "."), g("commit", "-qm", "spec")
    (tmp_path / "x.txt").write_text("x")
    g("add", "."), g("commit", "-qm", "feat: b works\n\nBehaviour: flows.b")
    pr = console.progress(str(tmp_path))
    assert (pr["step"], pr["i"], pr["n"], pr["milestone"]) == ("1.2", 2, 2, "flows"), pr
    (tmp_path / "y.txt").write_text("y")
    g("add", "."), g("commit", "-qm", "fix: a (Step 1.1, owner ruling)\n\nBehaviour: flows.b")
    assert console.progress(str(tmp_path))["step"] == "1.1", "a Step in the message wins"


def test_a_lock_wait_over_its_limit_is_a_row_naming_the_holder_and_the_console_shows_it(tmp_path, monkeypatch):
    """Manager 2026-11-02: a landing sat 16 min in flock on ladder.lock, held by a check, with no row."""
    import multiprocessing

    monkeypatch.setattr(journal, "STATE", tmp_path)
    monkeypatch.setattr(journal.Lock, "WARN_S", 0.2)
    with journal.Lock("ladder", what="the check of ie"):
        def wait():
            journal.STATE = tmp_path
            journal.Lock.WARN_S = 0.2
            with journal.Lock("ladder", what="a landing"):
                pass
        p = multiprocessing.get_context("fork").Process(target=wait)
        p.start()
        assert _wait(lambda: any(r["event"] == "lock" for r in journal.read()))
        st = console.api_status(journal.read(), [])
        (w,) = st["lock_waits"]
        assert w["what"] == "a landing" and "the check of ie" in w["holder"] and str(os.getpid()) in w["holder"]
    p.join(5)
    assert [r["state"] for r in journal.read() if r["event"] == "lock"] == ["waiting", "acquired"]
    assert console.api_status(journal.read(), [])["lock_waits"] == []


def test_console_tiles_come_from_origin_an_owned_milestone_has_no_start_and_the_spec_twin_is_one_row(tmp_path, monkeypatch, live):
    """Owner 11:00 screenshot: last landing '-', closed today 0, '4 of 1 lanes', Start on a spec lane-sharing owns, two rows for one milestone."""
    from fichero_builder import milestone as ms
    monkeypatch.setattr(console, "_git_tiles", lambda branch="integration": {"last_land_git": {"sha": "d" * 40, "ts": "2026-11-02T10:01:00", "subject": "x"},
                                                                            "closed_today_git": [6204, 6244]})
    st = console.api_status(journal.read(), LANES)
    assert st["last_land_git"]["sha"].startswith("ddd") and st["closed_today_git"] == [6204, 6244]
    assert st["lanes_note"] == "1 worker lane(s) (limit 1) · 1 external"
    spec_dir = tmp_path / "docs" / "contributor_manual" / "specs"
    (spec_dir / "source").mkdir(parents=True)
    (spec_dir / "build-order.md").write_text("# Build order\n\n## In order\n\n1. `Sharing & Pairing` — x. Spec: source/sharing-two-macs.md\n2. `sharing-two-macs` — the twin\n\n## Parked\n\n- `Delta`\n")
    (spec_dir / "source" / "sharing-two-macs.md").write_text("> Milestone: sharing\n")
    brief = tmp_path / "brief.md"
    brief.write_text("LANE sharing. Spec: docs/contributor_manual/specs/source/sharing-two-macs.md\n")
    monkeypatch.setattr(console.queue, "load", lambda: [{"id": "lane-sharing", "worktree": "/w", "cursor": 0, "kind": "external",
                                                         "steps": [{"step": "2.3", "state": "queued", "brief": str(brief)}]}])
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\necho '[{\"title\":\"Sharing & Pairing\",\"open_issues\":3,\"closed_issues\":1}]'\n")
    gh.chmod(0o755)
    monkeypatch.setattr(ms, "list_issues", lambda name, gh="gh": [{"number": 1, "title": "sharing Step 1.1: a", "body": "", "labels": [{"name": "step:1.1"}]}])
    monkeypatch.setattr(ms, "build_order", lambda p: [{"number": "1.1", "title": "a", "depends_on": []}])
    d = console.milestones(tmp_path, gh=str(gh), lanes=console.queue.load(), reads=lambda r, ls, b: ({}, "", set()), closed=lambda n: [])
    names = [m["name"] for m in d["milestones"]]
    assert names == ["Sharing & Pairing", "Delta"], "the spec's empty twin is dropped"
    m = d["milestones"][0]
    assert m["owner"] == "lane-sharing" and not m["startable"] and m["held_by"] == "owned by lane-sharing"


def test_activity_gives_each_rung_its_usual_time_and_a_running_rung_reads_it():
    """Speed item 1 (manager 2026-11-02): time every rung; the console shows the usual time per rung."""
    rows = []
    for i, s in enumerate((100, 300, 200)):
        rows += [{"ts": f"2026-11-02T0{i}:00:00", "event": "activity", "kind": "check", "key": f"k{i}", "state": "start", "lane": "a"},
                 {"ts": f"2026-11-02T0{i}:01:00", "event": "activity", "kind": "check", "key": f"k{i}", "state": "rung", "rung": "guards", "ok": True, "seconds": s},
                 {"ts": f"2026-11-02T0{i}:02:00", "event": "activity", "kind": "check", "key": f"k{i}", "state": "end", "ok": True}]
    rows += [{"ts": "2026-11-02T05:00:00", "event": "activity", "kind": "check", "key": "k9", "state": "start", "lane": "b"},
             {"ts": "2026-11-02T05:00:01", "event": "activity", "kind": "check", "key": "k9", "state": "rung-start", "rung": "guards"}]
    d = console.activity(rows)
    assert d["medians"] == {"guards": 200} and d["running"][0]["now"] == "guards" and d["running"][0]["usual"] == 200
