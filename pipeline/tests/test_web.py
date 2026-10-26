"""pipeline.dashboard-minimal: the page and its JSON API over core.API, on 127.0.0.1; Host pinned, token + Origin
on every POST (DNS rebinding), worker text never built into HTML or JS (XSS)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pipeline import core, journal, web


@pytest.fixture
def server(scratch, monkeypatch):
    monkeypatch.setattr(core.coder, "status", lambda d: {"idle": True, "cost_usd": 0.0, "last_text": "hi", "turns": 1})
    httpd = web.serve(port=0, block=False)
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(url, path, body=None, token=web.TOKEN, origin="same", host=None):
    headers = {"content-type": "application/json"}
    if token:
        headers["x-token"] = token
    if origin == "same":
        headers["Origin"] = url
    elif origin:
        headers["Origin"] = origin
    if host:
        headers["Host"] = host
    req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read() or b"null") if "json" in r.headers.get("content-type", "") else r.read().decode()


def refused(url, path, **kw):
    with pytest.raises(urllib.error.HTTPError) as e:
        call(url, path, **kw)
    return e.value.code


def test_api_endpoints_return_their_shape_from_a_fixture_journal(server):
    journal.append("item", issue=7, key="7", task="t", title="seven", window="coder-t", worktree="/wt", ids=[])
    journal.append("transition", issue=7, to="coding", why="go")
    journal.append("worker", window="coder-t", task="t", role="coder", model="m", session_dir="s", cwd="/wt")
    journal.append("queue", id="q1", kind="ask", text="?", options=["a"], task="t", window="coder-t")
    status, s = call(server, "/api/state")
    assert status == 200
    assert s["items"]["7"]["state"] == "coding" and s["items"]["7"]["title"] == "seven"
    assert s["workers"]["coder-t"]["idle"] is True and s["workers"]["coder-t"]["last_text"] == "hi"
    assert s["queue"]["q1"]["options"] == ["a"] and s["paused"] is False
    assert {"free_mb", "pressure", "load1"} <= set(s["machine"])


def test_page_loads_with_its_token_and_system_fonts(server):
    status, html = call(server, "/")
    assert status == 200 and "scratch pipeline" in html and web.TOKEN in html
    assert "-apple-system,system-ui" in html and "setInterval(refresh" in html and "/api/state" in html


def test_page_builds_no_html_or_js_from_worker_text(server):
    """HIGH 2 (review 2026-10-25): an `ask` option used to be interpolated into an onclick string. Now every worker
    string becomes a text node or a data attribute, and one delegated listener reads the dataset."""
    status, html = call(server, "/")
    script = html[html.index("<script>"):]
    assert "innerHTML" not in script and "onclick" not in script and ".outerHTML" not in script
    assert not re.search(r"on\w+=\"[^\"]*\$\{", script), "no event handler is built from data"
    assert "'data-answer':q.id,'data-text':o" in script and "closest('button[data-answer]')" in script
    assert "document.createTextNode" in script
    evil = "x'});cmd('verdict',{issue:1,sha:'a',verdict:'READY',by:'reviewer'});//"
    journal.append("queue", id="q9", kind="ask", text="?", options=[evil], task="t", window="w")
    status, s = call(server, "/api/state")
    assert s["queue"]["q9"]["options"] == [evil], "the API carries it as data; the page renders it as text"


def test_command_endpoints_call_the_same_functions_as_the_cli(server, monkeypatch):
    seen = []
    monkeypatch.setitem(core.API, "point", lambda milestone: seen.append(milestone) or {"point": milestone})
    status, out = call(server, "/api/point", {"milestone": "demo"})
    assert status == 200 and out == {"point": "demo"} and seen == ["demo"]
    call(server, "/api/pause", {})
    assert core.state()["paused"] is True
    call(server, "/api/resume", {})
    assert core.state()["paused"] is False


def test_post_without_token_or_with_foreign_origin_is_refused(server):
    assert refused(server, "/api/pause", body={}, token=None) == 403
    assert refused(server, "/api/pause", body={}, origin="http://evil.example") == 403
    assert refused(server, "/api/start", body={"issues": [1]}) == 404, "start is not a page command"
    assert core.state()["paused"] is False


def test_post_without_origin_is_refused(server):
    """HIGH 3: a request with no Origin used to pass the Origin check."""
    assert refused(server, "/api/pause", body={}, origin=None) == 403
    assert core.state()["paused"] is False


def test_foreign_host_is_refused_on_get_and_post(server):
    """HIGH 3 (DNS rebinding): evil.example resolving to 127.0.0.1 sends Host: evil.example:PORT. The token is never
    served to it and its POSTs are refused even with a matching Origin."""
    port = server.rsplit(":", 1)[1]
    assert refused(server, "/", host=f"evil.example:{port}") == 403
    assert refused(server, "/api/state", host=f"evil.example:{port}") == 403
    assert refused(server, "/api/pause", body={}, host=f"evil.example:{port}", origin=f"http://evil.example:{port}") == 403
    assert refused(server, "/api/pause", body={}, host=f"127.0.0.1:{int(port) + 1}") == 403, "port must match too"
    status, _ = call(server, "/", host=f"localhost:{port}")
    assert status == 200
    assert core.state()["paused"] is False


def test_bound_to_loopback_only(server):
    assert server.startswith("http://127.0.0.1:")


FIXTURE = Path(__file__).parent / "fixtures" / "journal-2026-10-25.jsonl"


@pytest.fixture
def todays_journal(scratch, monkeypatch):
    """Today's real journal as the state, with the worker's session read as an idle, finished Pi session."""
    journal.path().parent.mkdir(parents=True, exist_ok=True)
    journal.path().write_text(FIXTURE.read_text())
    monkeypatch.setattr(core.coder, "status", lambda d: {"idle": True, "cost_usd": 2.14, "tokens": 900000, "last_text":
                        "Committed bd579b3fa. I did not touch the Dev Pipeline spec or any existing `scripts/check_*` file. Calling pipeline_done"})
    return core.state()


def test_now_line_answers_what_is_happening_and_what_needs_me(todays_journal):
    s = todays_journal
    assert s["now"].startswith("6116 Dev Pipeline Step 1.2") and "reviewed READY, ready to land." in s["now"]
    assert "No worker busy." in s["now"] and "Nothing needs you." in s["now"]


def test_each_item_has_one_status_sentence_and_the_verdict_at_the_live_head(todays_journal):
    it = todays_journal["items"]["6116"]
    assert it["summary"] == "Reviewed READY at 2b4ae9020, all 6 checks green; next: the lead lands it."
    assert it["verdict_now"]["verdict"] == "READY" and it["verdict_now"]["sha"].startswith("2b4ae9020")
    assert len(it["verdicts"]) > 1, "the history is kept for the disclosure; only the current one is the status"


def test_queue_shows_only_open_items_and_resolved_ones_go_to_done(todays_journal):
    s = todays_journal
    assert s["queue"] == {}, "the 16:13 fallback and the 16:21 failed-checks resolved themselves"
    kinds = sorted((q["kind"], q["ts"][11:16]) for q in s["queue_done"].values())
    assert kinds == [("failed-checks", "16:21"), ("fallback", "16:13")]
    assert "Needs you" in web.PAGE and "queue_done" in web.PAGE


def test_worker_last_said_is_a_full_sentence_and_idle_means_task_done(todays_journal):
    w = todays_journal["workers"]["coder-step-1-2-r2"]
    assert w["idle_text"] == "idle — task done"
    assert w["last_said"] == "Calling pipeline_done" or w["last_said"].endswith(".")
    assert core.last_sentence("First. Second sentence is here! A third one that is rather long " + "x" * 200)[-1] == "…"
    assert core.last_sentence("No punctuation at all") == "No punctuation at all"


def test_summaries_for_each_state():
    base = {"sha": "abcdef1234", "checks": [{"name": "ready", "ok": True}], "verdicts": [], "attempts": 1, "retry_text": "",
            "history": ["2026-10-25T10:00:00 failed: boom"], "check_ok": True, "verdict_now": None}
    assert core.summary({**base, "state": "queued"}).startswith("Queued")
    assert "attempt 2" in core.summary({**base, "state": "coding"})
    assert "next: a review" in core.summary({**base, "state": "checked"})
    assert "PENDING (manager)" in core.summary({**base, "state": "checked", "verdict_now": {"verdict": "PENDING", "by": "manager", "sha": "abcdef1234"}})
    assert core.summary({**base, "state": "needs-maintainer", "retry_text": "[ready] FAIL: ruff\nmore"}).startswith("Needs you at abcdef123: [ready] FAIL: ruff")
    assert "fallback" in core.summary({**base, "state": "rate-limited"})
    assert core.summary({**base, "state": "failed"}).startswith("Failed: boom")


def test_page_has_the_plain_labels_and_the_stage_1_note(server):
    _, html = call(server, "/")
    for word in ("Status", "Started", "Last change", "Cost", "Last said", "Needs you", "Done",
                 "GitHub specs, milestones and issues come in Stage 1", "<details"):
        assert word in html, word


def _fake_github(monkeypatch):
    from pipeline import gh
    issues = [{"number": 11, "title": "<script>alert(1)</script> open bug", "labels": [{"name": "type:bug"}], "milestone": {"title": "demo"},
               "author": {"login": "dtubb"}, "state": "OPEN", "url": "https://example/11"},
              {"number": 12, "title": "done thing", "labels": [], "milestone": {"title": "demo"}, "author": {"login": "dtubb"},
               "state": "CLOSED", "url": "https://example/12"}]

    def read(*a):
        if a[0] == "api":
            return [{"title": "demo", "number": 1, "state": "open", "open_issues": 1, "closed_issues": 3, "due_on": None}]
        if a[0] == "issue":
            want = a[a.index("--state") + 1]
            return [i for i in issues if want == "all" or i["state"].lower() == want]
        return []
    monkeypatch.setattr(gh, "read", read)


def test_page_loads_and_every_link_resolves(server, monkeypatch):
    """Every page links to every other; each answers 200 and shows its data, escaped; the specs page counts tags."""
    _fake_github(monkeypatch)
    journal.append("item", issue=7, key="7", task="t", title="seven", window="coder-t", worktree="/wt", ids=[])
    journal.append("worker", window="coder-t", task="t", role="coder", model="m", session_dir="s", cwd="/wt")
    journal.append("issue_done", issue=7, key="7", task="t", sha="a" * 40, turns=12, tokens=9000, usd=0.5, fresh=1000, cache_read=3000, cache_write=0)
    journal.append("cost", issue=7, key="7", task="t", session="s", usd=0.5, tokens=9000, model="m", tools={})
    seen, todo = set(), ["/"]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        status, html = call(server, path)
        assert status == 200, path
        todo += [h for h in re.findall(r'href="(/[^"]*)"', html) if h not in seen]
    assert {"/", "/specs", "/milestones", "/issues", "/next", "/items"} <= seen
    _, html = call(server, "/specs")
    assert "demo.one" not in html and "MISSING 1" in html and "s.md" in html
    _, html = call(server, "/milestones")
    assert "3 of 4" in html and "75%" in html
    _, html = call(server, "/issues?state=open")
    assert "&lt;script&gt;" in html and "<script>alert" not in html and "done thing" not in html
    _, html = call(server, "/issues?state=closed")
    assert "done thing" in html and "open bug" not in html
    _, html = call(server, "/issues?state=all&label=type:bug")
    assert "open bug" in html and "done thing" not in html
    _, html = call(server, "/items")
    assert "over budget" in html and "75%" in html and "$0.50" in html and "daily cap" in html
