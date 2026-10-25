"""pipeline.dashboard-minimal: the page and its JSON API over core.API, on 127.0.0.1; Host pinned, token + Origin
on every POST (DNS rebinding), worker text never built into HTML or JS (XSS)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

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
    journal.append("item", issue=7, task="t", title="seven", window="coder-t", worktree="/wt")
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
