"""pipeline.dashboard-minimal: the page and its JSON API over core.API, on 127.0.0.1, token + Origin on every POST."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from pipeline import core, journal, web


@pytest.fixture
def server(scratch, monkeypatch):
    monkeypatch.setattr(core.coder, "status", lambda d: {"idle": True, "cost_usd": 0.0, "last_text": "hi"})
    httpd = web.serve(port=0, block=False)
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(url, path, body=None, token=web.TOKEN, origin=None):
    req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json", **({"x-token": token} if token else {}),
                                          **({"Origin": origin} if origin else {})})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read() or b"null") if "json" in r.headers.get("content-type", "") else r.read().decode()


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
    assert "-apple-system,system-ui" in html and "setInterval(refresh" in html
    assert "/api/state" in html


def test_command_endpoints_call_the_same_functions_as_the_cli(server, monkeypatch):
    seen = []
    monkeypatch.setitem(core.API, "point", lambda milestone: seen.append(milestone) or {"point": milestone})
    status, out = call(server, "/api/point", {"milestone": "demo"}, origin=server)
    assert status == 200 and out == {"point": "demo"} and seen == ["demo"]
    status, out = call(server, "/api/pause", {})
    assert core.state()["paused"] is True
    call(server, "/api/resume", {})
    assert core.state()["paused"] is False


def test_post_without_token_or_with_foreign_origin_is_refused(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        call(server, "/api/pause", {}, token=None)
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        call(server, "/api/pause", {}, origin="http://evil.example")
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        call(server, "/api/start", {"issues": [1]})
    assert e.value.code == 404, "start is not a page command"
    assert core.state()["paused"] is False


def test_bound_to_loopback_only(server):
    assert server.startswith("http://127.0.0.1:")
