"""Section H of the console's spec (owner 2026-11-27, after using the Builder Console): one test per `builder-console.*` line there."""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from fichero_builder import console, journal, queue, work

_REAL_LOAD = queue.load  # the `live` fixture replaces queue.load; a test over the real queue file puts this back


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    monkeypatch.setattr(console, "ROOT", tmp_path)
    monkeypatch.setattr(console, "_STATUS", {"at": 0.0, "data": None})
    monkeypatch.setattr(console, "_CHARTS", {})
    return tmp_path


def _wait(pred):
    for _ in range(200):
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_a_ladder_wait_names_what_holds_each_busy_slot_and_the_console_fills_an_old_question_mark(state, monkeypatch):
    """builder-console.lock.holder-named: 'held by ?' in the ladder-lock waiting line."""
    monkeypatch.setattr(journal.Lock, "WARN_S", 0.05)
    with journal.Lock("ladder", what="the check of ie"):
        (state / "ladder.files").write_text(json.dumps({"name": "ie", "files": ["a.py"]}))
        t = threading.Thread(target=lambda: work.ladder_slot("seg", ["b.py"], 1, sleep=lambda s: time.sleep(0.02), by_file=False).__enter__(), daemon=True)
        t.start()
        assert _wait(lambda: any(r["event"] == "lock" and r["state"] == "waiting" for r in journal.read()))
        (w,) = [r for r in journal.read() if r["event"] == "lock"]
        assert w["holder"] == f"{os.getpid()} the check of ie", "the slot's lock file says who: never ?"
        journal.append("lock", state="waiting", name="ladder", holder="?", what="the check of old", pid=os.getpid(), detail="all 1 ladder slot(s) are busy")
        waits = console.api_status(journal.read(), [])["lock_waits"]
        assert [x["holder"] for x in waits] == [f"{os.getpid()} the check of ie"] * 2, "a row written before the fix reads the lock files now"
    t.join(5)


def _get(url, path):
    import urllib.request
    return json.loads(urllib.request.urlopen(url + path, timeout=5).read())


def _post(url, path, body, token=None):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Builder-Token": token} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture
def live(state, monkeypatch):
    """A console on an ephemeral loopback port over the state dir; verbs go to a fake runner."""
    monkeypatch.setattr(console.queue, "load", lambda: [])
    ran = []
    monkeypatch.setattr(console, "run_verb", lambda argv: ran.append(argv) or (0, "ok"))
    srv = console.server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", ran
    srv.shutdown()


def _page() -> str:
    return console.PAGE.read_text()


def _at(now: float, hours_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - hours_ago * 3600))


def test_alerts_are_a_badge_count_and_a_page_grouped_by_kind_with_old_ones_folded_and_the_owners_marked(live):
    """builder-console.alerts.badge-and-page: 68 alerts up to 11 days old took over the top of every page."""
    url, _ran = live
    now = time.time()
    al = lambda h, i, lane, what, actions: journal.append("alert", id=i, lane=lane, step="s", what=what, actions=actions) | {"ts": _at(now, h)}  # noqa: E731
    rows = [al(200, "a-s-1", "a", "runner m4 unreachable; load 31", ["retry", "park"]),
            al(30, "a-s-2", "a", "runner m4 unreachable; load 12", ["retry", "park"]),
            al(3, "a-s-3", "a", "red at pytest 14 failed", ["retry", "park", "ask-owner"]),
            al(2, "b-s-4", "b", "red at pytest 2 failed", ["retry", "park", "ask-owner"]),
            al(1, "review-x-q-5", "review-x", "Owner question 1 of the x review: keep the old name?", ["ask-owner", "park"]),
            al(5, "c-s-6", "c", "a question", ["retry", "ask-owner"]),
            al(4, "c-s-7", "c", "answered", ["retry"]),
            {"ts": _at(now, 4), "event": "alert-answer", "id": "c-s-6", "action": "ask-owner", "ok": True},
            {"ts": _at(now, 3), "event": "alert-answer", "id": "c-s-7", "action": "retry", "ok": True}]
    (journal.STATE / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    v = console.alerts_view(journal.read(), now=now)
    assert (v["count"], v["owner_count"], v["older_count"]) == (3, 1, 2), "the badge counts the open alerts under a day old; the owner's apart"
    assert [(g["kind"], g["n"], g["owner"]) for g in v["groups"]] == [("Owner question N of the x review: keep the old name?", 1, True), ("red at pytest N failed", 2, False)]
    assert [x["id"] for x in v["groups"][1]["alerts"]] == ["b-s-4", "a-s-3"], "one kind across lanes, newest first"
    assert [(g["kind"], g["n"]) for g in v["older"]] == [("runner mN unreachable", 2)], "over a day old: folded, grouped the same way"
    assert [a["id"] for a in v["asked_owner"]] == ["c-s-6"], "what the manager handed to the owner"
    assert _get(url, "/api/alerts")["count"] == 3
    st = _get(url, "/api/status")
    assert st["alerts"] == {"count": 3, "owner_count": 1}
    page = _page()
    assert '["alerts", "Alerts"]' in page and "st.alerts.count" in page, "a tab and a badge"
    app = page[page.index("function App()"):]
    assert "<${Alerts}" not in app.replace("alerts: Alerts", "") and "Resolved" not in app, "no page opens with the alert cards"


def _lane(i, steps, **kw):
    return {"id": i, "worktree": "/nonexistent/" + i, "cursor": 0, "paused": False, "kind": "worker",
            "steps": [{"step": s, "state": st, "issues": [7], "why": "", "brief": "/nonexistent/brief", "entered_at": 0.0} for s, st in steps], **kw}


def test_the_status_api_computes_status_once_and_reads_the_journal_for_last_actions_once_not_per_lane(live, monkeypatch):
    """Review of #6589: api_status is the slow path of #6498; the badge and the lanes' last actions add no pass per lane."""
    class Rows(list):
        scans = 0

        def __reversed__(self):
            Rows.scans += 1
            return super().__reversed__()

    calls, real = [], console.status
    monkeypatch.setattr(console, "status", lambda *a, **k: calls.append(1) or real(*a, **k))
    rows = [{"ts": "2026-11-27T10:00:00", "event": "console", "who": "owner", "verb": "pause", "state": "ended", "ok": True, "rc": 0, "detail": "old", "args": {"lane": "a"}},
            {"ts": "2026-11-27T10:01:00", "event": "console", "who": "owner", "verb": "resume", "state": "ended", "ok": True, "rc": 0, "detail": "new", "args": {"lane": "a"}}]
    one = console.api_status(Rows(rows), [_lane("a", [("s1", "queued")])])
    assert len(calls) == 1, "alerts_view takes the status api_status already holds"
    assert one["lanes"][0]["last_action"]["verb"] == "resume", "the newest row of the lane"
    n1, Rows.scans = Rows.scans, 0
    three = console.api_status(Rows(rows), [_lane(i, [("s", "queued")]) for i in "abc"])
    assert Rows.scans == n1, "the journal scans do not grow with the lanes"
    assert [x["last_action"] and x["last_action"]["detail"] for x in three["lanes"]] == ["new", None, None]


def test_a_lanes_last_action_sits_in_its_row_and_the_action_log_is_one_page(live, monkeypatch):
    """builder-console.actions.beside-what-they-act-on: the console actions sat at the bottom of every page."""
    url, ran = live
    monkeypatch.setattr(console.queue, "load", lambda: [_lane("a", [("s1", "queued")]), _lane("b", [("s2", "queued")])])
    monkeypatch.setattr(console, "run_verb", lambda argv: ran.append(argv) or (1, "first line\nREFUSED: no lane"))
    assert _post(url, "/api/action", {"verb": "pause", "args": {"lane": "a"}}, console.TOKEN)[0] == 200
    assert _wait(lambda: any(r.get("state") == "ended" for r in journal.read()))
    monkeypatch.setattr(console, "_STATUS", {"at": 0.0, "data": None})
    a, b = _get(url, "/api/status")["lanes"]
    assert {k: a["last_action"][k] for k in ("verb", "state", "ok", "rc", "detail")} == {"verb": "pause", "state": "ended", "ok": False, "rc": 1, "detail": "REFUSED: no lane"}
    assert a["last_action"]["ts"] and b["last_action"] is None, "the newest console row whose args name that lane"
    page = _page()
    app, lanes, log = page[page.index("function App()"):], page[page.index("function Lanes("):page.index("function DevBuilds(")], page[page.index("function Log("):page.index("function App()")]
    assert "l.last_action" in lanes, "the result beside the lane's buttons"
    assert "Console actions" in log and "Last events" in log and '["log", "Log"]' in app
    assert "Console actions" not in app and "Last events" not in app, "no other page ends with them"
    assert 'act("build")' in app and 'act("loop-stop")' in app, "the whole-harness actions stay in the toolbar"


def test_every_milestone_issue_and_step_issue_number_is_a_link_to_the_issue(tmp_path, monkeypatch):
    """builder-console.milestones.issue-links: clicking Milestones, then an issue, changed nothing."""
    from fichero_builder import milestone as ms
    spec_dir = tmp_path / "docs" / "contributor_manual" / "specs"
    spec_dir.mkdir(parents=True)
    (spec_dir / "build-order.md").write_text("# Build order\n\n## In order\n\n1. `Alpha` Spec: alpha.md\n")
    (spec_dir / "alpha.md").write_text("> Milestone: alpha\n")
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\necho '[{\"title\":\"Alpha\",\"open_issues\":1,\"closed_issues\":0}]'\n")
    gh.chmod(0o755)
    monkeypatch.setattr(ms, "list_issues", lambda name, gh="gh", **k: [{"number": 11, "title": "alpha Step 1.1: a", "body": "", "labels": [{"name": "step:1.1"}]}])
    monkeypatch.setattr(ms, "build_order", lambda p: [{"number": "1.1", "title": "a", "depends_on": []}])
    read = lambda: console.milestones(tmp_path, gh=str(gh), lanes=[], reads=lambda root, ls, br: ({}, "", set()), closed=lambda name: [])  # noqa: E731
    monkeypatch.setattr(console, "repo_url", lambda root: "https://example.test/o/r")
    d = read()
    assert d["repo"] == "https://example.test/o/r" and d["milestones"][0]["issues"][0]["url"] == "https://example.test/o/r/issues/11"
    monkeypatch.setattr(console, "repo_url", lambda root: "")
    d = read()
    assert d["repo"] == "" and d["milestones"][0]["issues"][0]["url"] == "", "no origin remote: no link"
    page = _page()
    ms_js = page[page.index("function Milestones("):page.index("function Worktrees(")]
    assert "href=${i.url}" in ms_js and "issueLink(n)" in ms_js and "data.repo" in ms_js, "the issue rows and the steps' numbers link out"


def test_a_lane_moves_in_the_queues_order_through_the_cli_and_the_console_calls_the_verbs(live, monkeypatch, capsys):
    """builder-console.control.lanes-and-steps, the controls: pause, resume, start, a lane up or down, a queued step up or down."""
    from fichero_builder import __main__ as cli
    brief = journal.STATE / "b.txt"
    brief.write_text("brief")
    monkeypatch.setattr(console.queue, "load", _REAL_LOAD)  # the real queue file under the state dir
    for name in ("a", "b", "c"):
        queue.add(name, "/w/" + name, "1.1", str(brief), [])
    st = ["--state", str(journal.STATE)]
    assert cli.main(["queue", "move", "--lane", "c", "--to", "0", *st]) == 0 and [x["id"] for x in queue.load()] == ["c", "a", "b"]
    assert cli.main(["queue", "move", "--lane", "c", "--to", "9", *st]) == 0 and [x["id"] for x in queue.load()] == ["a", "b", "c"], "past the end: last"
    assert cli.main(["queue", "move", "--lane", "zz", "--to", "0", *st]) == 1 and "REFUSED" in capsys.readouterr().out
    moved = [r for r in journal.read() if r["event"] == "queue" and r["state"] == "lane-moved"]
    assert [(r["lane"], r["detail"]) for r in moved] == [("c", "to place 1 of 3"), ("c", "to place 3 of 3")], "one row a move"
    url, ran = live
    for verb, args, want in [("lane-move", {"lane": "b", "to": 0}, ["queue", "move", "--lane", "b", "--to", "0"]),
                             ("queue-move", {"lane": "b", "step": "1.1", "to": 1}, ["queue", "move", "--lane", "b", "--step", "1.1", "--to", "1"]),
                             ("pause", {"lane": "b"}, ["queue", "pause", "--lane", "b"]),
                             ("resume", {"lane": "b"}, ["queue", "resume", "--lane", "b"]),
                             ("start", {"lane": "b"}, ["queue", "resume", "--lane", "b"])]:
        code, body = _post(url, "/api/action", {"verb": verb, "args": args}, console.TOKEN)
        assert code == 200 and body["ok"], (verb, body)
        assert _wait(lambda: len(ran) and ran[-1][3:3 + len(want)] == want), (verb, ran)
    assert _wait(lambda: sum(1 for r in journal.read() if r["event"] == "console" and r.get("state") == "ended") == 5), "each one console row pair"


def test_the_now_view_lists_lanes_in_order_with_each_steps_age_the_trains_and_every_ladder_slot_with_its_holder(live, monkeypatch):
    """builder-console.control.lanes-and-steps, the view: what is running now, in order."""
    url, _ran = live
    now = time.time()
    lanes = [_lane("b", [("s1", "landed"), ("s2", "checking")], cursor=1), _lane("a", [("s3", "queued")], paused=True)]
    lanes[0]["steps"][1]["entered_at"] = now - 600
    monkeypatch.setattr(console.queue, "load", lambda: lanes)
    journal.append("train", id="train-1", steps=["b/s2"], candidate="c" * 40, result="green", landed=["b/s2"])
    with journal.Lock("ladder", what="the check of b"):
        (journal.STATE / "ladder.files").write_text(json.dumps({"name": "b", "files": ["x.py"]}))
        (journal.STATE / "ladder-2.lock").write_text("999999999 the check of gone")
        v = console.now_view(journal.read(), lanes, now=now)
    assert [(x["lane"], x["paused"]) for x in v["lanes"]] == [("b", False), ("a", True)], "the queue's order, not sorted"
    assert [(s["step"], s["state"], s["age_s"]) for s in v["lanes"][0]["steps"]] == [("s1", "landed", None), ("s2", "checking", 600)]
    assert [(t["id"], t["steps"], t["result"]) for t in v["trains"]] == [("train-1", ["b/s2"], "green")]
    assert v["slots"] == [{"slot": "ladder", "held": True, "holder": f"{os.getpid()} the check of b", "name": "b"},
                          {"slot": "ladder-2", "held": False, "holder": "", "name": ""}], "a dead pid's lock file is a free slot"
    assert [x["lane"] for x in _get(url, "/api/now")["lanes"]] == ["b", "a"]
    page = _page()
    now_js = page[page.index("function Now("):page.index("function App()")]
    assert '["now", "Now"]' in page and all(w in now_js for w in ('"lane-move"', '"queue-move"', '"pause"', '"resume"', '"start"', "d.slots", "d.trains", "age_s"))


def test_a_message_to_the_manager_is_an_inbox_line_and_one_row_and_the_thread_shows_both_sides(live):
    """builder-console.manager.thread: talk to the manager from the console."""
    url, _ran = live
    inbox, outbox = journal.STATE / "manager" / "inbox.jsonl", journal.STATE / "manager" / "outbox.jsonl"
    assert _post(url, "/api/message", {"text": "hello"})[0] == 403 and not inbox.exists(), "the token rule of every POST"
    assert _post(url, "/api/message", {"text": "   "}, console.TOKEN)[0] == 400 and _post(url, "/api/message", {"text": 5}, console.TOKEN)[0] == 400
    assert not inbox.exists(), "an empty text is refused"
    code, body = _post(url, "/api/message", {"text": " hold lane a until the build is out \n"}, console.TOKEN)
    assert code == 200 and body["ok"]
    (line,) = [json.loads(x) for x in inbox.read_text().splitlines()]
    assert sorted(line) == ["text", "ts"] and line["text"] == "hold lane a until the build is out"
    (row,) = [r for r in journal.read() if r["event"] == "owner-message"]
    assert row["chars"] == len(line["text"]) and row["who"].endswith("@console") and "hold lane" not in json.dumps(row), "the row wakes the manager; the text stays in the inbox"
    outbox.write_text(json.dumps({"ts": "2999-01-01T00:00:00", "text": "held"}) + "\nnot json\n")
    t = _get(url, "/api/thread")["messages"]
    assert [(m["from"], m["text"]) for m in t] == [("manager", "unreadable line 2 of outbox.jsonl"), ("owner", line["text"]), ("manager", "held")], "one thread, by time"
    page = _page()
    js = page[page.index("function Manager("):page.index("function App()")]
    assert '["manager", "Manager"]' in page and '"/api/message"' in js and '"/api/thread"' in js and "<textarea" in js


def test_progress_is_series_per_day_from_the_journal_and_each_priority_specs_ok_count_from_git_history(live, monkeypatch):
    """builder-console.progress.page: landings, trains by result, issues closed, rounds per landing, and [OK] counts over time."""
    url, _ran = live
    now = time.mktime(time.strptime("2026-11-27T12:00:00", "%Y-%m-%dT%H:%M:%S"))
    rows = [{"ts": "2026-11-25T09:00:00", "event": "landed", "step": "done", "issues": [1, 2], "left_open": [2]},
            {"ts": "2026-11-27T09:00:00", "event": "landed", "step": "done", "issues": [3, 4]},
            {"ts": "2026-11-27T10:00:00", "event": "landed", "step": "done", "issues": []},
            {"ts": "2026-11-27T10:00:00", "event": "landed", "step": "verdict"},
            {"ts": "2026-10-01T10:00:00", "event": "landed", "step": "done", "issues": [9]},
            {"ts": "2026-11-26T08:00:00", "event": "train", "id": "t1", "result": "red"},
            {"ts": "2026-11-27T08:00:00", "event": "train", "id": "t2", "result": "green"},
            {"ts": "2026-11-27T08:30:00", "event": "train", "id": "t3", "result": "green"},
            {"ts": "2026-11-27T08:40:00", "event": "train", "id": "t4", "state": "train-lost"},
            {"ts": "2026-11-26T01:00:00", "event": "queue", "lane": "a", "step": "s1", "state": "red"},
            {"ts": "2026-11-26T02:00:00", "event": "queue", "lane": "a", "step": "s1", "state": "red"},
            {"ts": "2026-11-26T03:00:00", "event": "queue", "lane": "a", "step": "s1", "state": "landed"},
            {"ts": "2026-11-26T04:00:00", "event": "queue", "lane": "a", "step": "s2", "state": "landed"}]
    spec = "- `x.a` [OK] one\n- `x.b` — **[OK]** two\n- `x.c` [GAP] (#1) three\n> an **[OK]** means built\n"
    calls = []

    def git(repo, *args):
        calls.append(args)
        if args[0] == "log":
            return "c3 2026-11-27\nc2 2026-11-27\nc1 2026-11-20\n"
        if args[0] == "rev-list":
            return "c0\n"
        return {"c0": "", "c1": spec.replace("[OK] one", "[GAP] (#2) one"), "c3": spec}[args[1].split(":")[0]]
    p = console.progress_view(rows, journal.STATE, {"Seg": "specs/seg.md"}, now=now, git=git)
    assert len(p["days"]) == console.PROGRESS_DAYS and p["days"][-1] == "2026-11-27" and p["days"][0] == "2026-10-29"
    at = lambda series, day: series[p["days"].index(day)]  # noqa: E731
    assert (at(p["landings"], "2026-11-25"), at(p["landings"], "2026-11-26"), at(p["landings"], "2026-11-27")) == (1, 0, 2) and sum(p["landings"]) == 3
    assert (at(p["closed"], "2026-11-25"), at(p["closed"], "2026-11-27")) == (1, 2), "issues less the ones left open"
    assert sorted(p["trains"]) == ["green", "red"] and at(p["trains"]["green"], "2026-11-27") == 2 and at(p["trains"]["red"], "2026-11-26") == 1
    assert [(r["lane"], r["step"], r["rounds"]) for r in p["rounds"]] == [("a", "s1", 2), ("a", "s2", 0)], "the red rows of a step before its landed row"
    assert p["specs"] == {"Seg": [{"day": "2026-10-28", "ok": 0}, {"day": "2026-11-20", "ok": 1}, {"day": "2026-11-27", "ok": 2}]}, "each day's last commit; behaviour lines only"
    assert ("show", "c2:specs/seg.md") not in calls
    (journal.STATE / "harness.toml").write_text('[land]\nbranch = "integration"\n')
    assert _get(url, "/api/progress")["specs"] == {}, "no [console.progress_specs]: no spec chart"
    import tomllib
    listed = tomllib.loads((console.PKG.parent / "harness.toml").read_text())["console"]["progress_specs"]
    assert len(listed) == 4 and all((console.PKG.parent / f).is_file() for f in listed.values()), "the project's four priority specs exist"
    page = _page()
    js = page[page.index("function Chart("):page.index("function App()")]
    assert '["progress", "Progress"]' in page and "<svg" in js and "/api/progress" in js and page.count("https://") == 1, "inline SVG; nothing new is fetched"
