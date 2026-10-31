"""Stage 0 dry runs: the real worker path (tmux window, real Pi 1.4.0, the generated MCP wrapper, the ladder, the journal)
against a scripted fake model. No key, no network, nothing on GitHub, nothing pushed. Slow (a Pi start is seconds), so
it runs only when PIPELINE_DRY=1: `pipeline/dry.sh` is the one command."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import ROOT, coder, core, gh, journal, runner
from pipeline.fakemodel import FakeModel

pytestmark = pytest.mark.skipif(not os.environ.get("PIPELINE_DRY"), reason="slow: run pipeline/dry.sh")
TASK = "lane"
MODEL = "qwen/qwen3-coder-next"


def issue(n: int) -> dict:
    return {"number": n, "title": f"f({n}) is {n}", "author": "dtubb", "labels": [], "milestone": "demo", "part_of": False,
            "body": f"Acceptance: f{n}() returns {n}.\nFiles: src/mod.py\nTest: tests/test_{n}.py\nDiff bound: 20"}


def last_user(body: dict) -> str:
    c = [m for m in body["messages"] if m["role"] == "user"][-1]["content"]
    return c if isinstance(c, str) else " ".join(p.get("text", "") for p in c)


def commit(n: int, usage=300) -> dict:
    """The worker's turn: write the function and its test, commit citing the issue."""
    cmd = (f"printf 'def f{n}():\\n    return {n}\\n' >> src/mod.py && "
           f"printf 'from src.mod import f{n}\\n\\ndef test_f{n}():\\n    assert f{n}() == {n}\\n' > tests/test_{n}.py && "
           f"git add -A && git commit -qm 'add f{n} (Fixes #{n})'")
    return {"tools": [("bash", {"command": cmd})], "usage": {"prompt": usage, "out": 30}}


def done(n: int) -> dict:
    return {"tools": [("pipeline_done", {"task": TASK, "issue": n})], "usage": {"prompt": 320, "out": 10}}


def finish(prompt=330) -> dict:
    return {"text": "Committed and done.", "usage": {"prompt": prompt, "out": 6}}


def write_note(body: dict) -> dict:
    path = re.search(r"write it to (\S+)", last_user(body)).group(1)
    return {"tools": [("bash", {"command": f"echo 'BUILDER NOTE: f1001 is in src/mod.py; do not redo it.' > {path}"})], "usage": {"prompt": 905, "out": 20}}


def lane(n: int, usage_at_end=330) -> list:
    return [commit(n), done(n), finish(usage_at_end)]


@pytest.fixture
def dry(scratch, monkeypatch, tmp_path):
    fm = FakeModel()
    agent = tmp_path / "agent"
    shutil.copytree(ROOT / "pipeline" / "pi-agent", agent, ignore=shutil.ignore_patterns("auth.json"))
    m = json.loads((agent / "models.json").read_text())
    m["providers"]["openrouter"].update(baseUrl=fm.url, apiKey="dummy")
    (agent / "models.json").write_text(json.dumps(m))
    mcp = json.loads((agent / "mcp.json").read_text())
    mcp["mcpServers"] = {"pipeline": mcp["mcpServers"]["pipeline"]}  # the tool-list check is its own test
    (agent / "mcp.json").write_text(json.dumps(mcp))
    key = tmp_path / "key"
    key.write_text("dummy-not-a-key")
    cfg = scratch["cfg"]
    cfg["workers"].update(pi_bin=str(ROOT / ".studio-pi/node_modules/.bin/pi"), pi_adapter=str(ROOT / ".studio-pi/node_modules/pi-mcp-adapter/index.ts"),
                          agent_dir=str(agent), tmux_session=f"dry-{os.getpid()}", context_tokens_by={"openrouter": 1000},
                          batch_end_pct=85, cost_cap_usd=1.0)
    cfg["ladder"].insert(0, {"name": "diff-bound", "kind": "diff-bound", "max_lines": 150, "max_files": 12})
    cfg["keys"]["openrouter"]["files"] = [str(key)]
    cfg["roles"]["reviewer"] = [{"kind": "pi", "provider": "openrouter", "model": MODEL}]
    monkeypatch.setenv("TERM", "xterm-256color")
    folder = tmp_path / "issues"
    folder.mkdir()
    for n in (1001, 1002, 1003):
        (folder / f"{n}.json").write_text(json.dumps(issue(n)))
    fm.folder = folder
    yield fm
    subprocess.run(["tmux", "kill-session", "-t", cfg["workers"]["tmux_session"]], capture_output=True)
    fm.close()


def start(dry, issues, **kw):
    return core.start(issues, task=TASK, from_file=str(dry.folder), provider="openrouter", model=MODEL, **kw)


def events(name):
    return [e for e in journal.read() if e["event"] == name]


def test_a_cluster_is_built_issue_by_issue_with_a_handoff_between(dry, scratch):
    dry.script(*lane(1001, usage_at_end=900), write_note, {"text": "Note written.", "usage": {"prompt": 910, "out": 5}}, *lane(1002))
    out = start(dry, [1001, 1002])
    assert out["items"] == {"1001@lane": "checked", "1002@lane": "checked"}, out
    log = subprocess.run(["git", "log", "--format=%s", "origin/integration..HEAD"], cwd=out["worktree"], capture_output=True, text=True).stdout.split("\n")
    assert [s for s in log if s] == ["add f1002 (Fixes #1002)", "add f1001 (Fixes #1001)"]  # one commit per issue
    (h,) = events("handoff")
    assert h["builder_note"] and "do not redo it" in Path(h["note"]).read_text() and h["context"] >= 800


# --- reviews, send-back, landing, the issue and milestone update ----------------------------------------------------

def verdict_step(v: str, findings: str = "") -> callable:
    def step(body):
        text = Path(re.search(r"Read and do (\S+)", last_user(body)).group(1)).read_text()  # the tell names the brief file
        key, sha = re.search(r"# Review (\S+):", text).group(1), re.search(r"Head ([0-9a-f]{40})", text).group(1)
        return {"tools": [("pipeline_verdict", {"issue": key, "sha": sha, "verdict": v, "by": "reviewer", "findings": findings})],
                "usage": {"prompt": 400, "out": 20}}
    return step


def fix_commit(n: int) -> dict:
    """A second commit on the issue's branch, answering a review: another function and its test."""
    cmd = (f"printf 'def f{n}b():\\n    return {n}\\n' >> src/mod.py && "
           f"printf 'from src.mod import f{n}b\\n\\ndef test_f{n}b():\\n    assert f{n}b() == {n}\\n' > tests/test_{n}b.py && "
           f"git add -A && git commit -qm 'review fixes for f{n} (Fixes #{n})'")
    return {"tools": [("bash", {"command": cmd})], "usage": {"prompt": 350, "out": 30}}


def test_not_ready_is_sent_back_then_ready_then_lands_dry_then_for_real_on_the_scratch_origin(dry, scratch):
    dry.script(*lane(1001), verdict_step("NOT_READY", "MED src/mod.py: f1001 has no second case"), finish(450),
               fix_commit(1001), done(1001), finish(),
               verdict_step("READY"), finish(450))
    out = start(dry, [1001])
    key = "1001@lane"
    assert out["items"] == {key: "checked"}
    rv = core.review(key)
    assert core.state()["items"][key]["state"] == "coding", (rv, events("verdict"), core.state()["items"][key]["history"], [t["function"]["name"] for t in dry.requests[-1]["tools"]])  # the binding NOT_READY moved it
    runner.send_back(key)  # the coder gets the findings
    it = core.state()["items"][key]
    assert it["state"] == "checked" and it["attempts"] == 1, it["history"]
    core.review(key)
    assert [e["verdict"] for e in events("verdict")] == ["NOT_READY", "READY"]
    assert core.state()["items"][key]["state"] == "reviewed"
    would = runner.land(key)  # core.DRY_RUN is True: the guards run, nothing is pushed
    assert not would["landed"] and would["would_push"].startswith("git push origin "), would
    assert checks_remote(scratch) != core.state()["items"][key]["sha"]
    real = runner._land(key, apply=True)  # to the scratch origin only
    assert real["landed"] and checks_remote(scratch) == real["sha"]


def checks_remote(scratch) -> str:
    return subprocess.run(["git", "rev-parse", "refs/heads/integration"], cwd=scratch["origin"], capture_output=True, text=True).stdout.strip()


def test_a_landed_filed_issue_would_be_closed_and_its_milestone_updated_dry(dry, scratch, monkeypatch, issues):
    """The closer's output with core.DRY_RUN on: the exact `gh` writes, journaled, nothing sent. A --from-file item has no
    GitHub issue, so this one is a filed issue (the `issues` fixture stands in for gh) and `gh.read` is canned."""
    iss = dict(core.ISSUE(1001), body=issue(1001)["body"])
    monkeypatch.setattr(core, "ISSUE", lambda n: dict(iss))
    dry.script(*lane(1001), verdict_step("READY"), finish(450))
    out = core.start([1001], milestone="demo", provider="openrouter", model=MODEL)
    assert out["items"] == {"1001": "checked"}, out
    core.review(1001)
    assert runner._land(1001, apply=True)["landed"]
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=scratch["repo"], check=True)
    canned = {"view": {"state": "OPEN", "labels": [], "milestone": {"title": "demo"}, "comments": []},
              "milestones": [{"title": "demo", "number": 7, "open_issues": 1, "closed_issues": 0}]}
    monkeypatch.setattr(gh, "read", lambda *a: canned["milestones"] if "milestones?state=open" in " ".join(a) else
                        [] if "events" in " ".join(a) else canned["view"])
    res = core.close_landed()
    writes = [e["args"] for e in events("gh_write")]
    assert res["closed"] == [1001] and res["milestones"] == ["demo"]
    assert writes[0][:3] == ["issue", "close", "1001"] and "Fixed in" in writes[0][4], writes
    assert writes[-1][:3] == ["api", "-X", "PATCH"] and "milestones/7" in writes[-1][3], writes
    assert all(e["dry_run"] for e in events("gh_write"))
    print("WOULD WRITE:", *[" ".join(w) for w in writes], sep="\n  gh ")


# --- failures: each ends in the designed recovery, or is a GAP (xfail, strict, with the reason) ---------------------

def item(n=1001):
    return core.state()["items"][f"{n}@{TASK}"]


def test_a_tool_error_is_counted_and_the_worker_carries_on(dry):
    dry.script({"tools": [("bash", {"command": "exit 3"})], "usage": {"prompt": 300, "out": 10}}, *lane(1001))
    assert start(dry, [1001])["items"] == {"1001@lane": "checked"}
    (s,) = [e["session"] for e in events("cost")][:1]
    assert coder.status(Path(s))["tool_errors"] >= 1


def test_a_false_done_with_no_commit_is_red_and_retried(dry):
    dry.script(done(1001), finish(), *lane(1001))  # says done, committed nothing; the retry brief gets a real commit
    assert start(dry, [1001])["items"] == {"1001@lane": "checked"}
    red = [r for e in events("check") if not e["ok"] for r in e["results"] if not r["ok"]]
    assert item()["attempts"] == 1 and "nothing to check" in red[0]["text"], red


def test_a_diff_over_the_bound_is_red_and_the_retry_shrinks_it(dry):
    big = "".join(f"printf 'x{i} = {i}\\n' >> src/mod.py && " for i in range(30))
    over = {"tools": [("bash", {"command": big + "printf 'from src.mod import x0\\n\\ndef test_x():\\n    assert x0 == 0\\n' > tests/test_1001.py && "
                                  "git add -A && git commit -qm 'too much (Fixes #1001)'"})], "usage": {"prompt": 300, "out": 30}}
    shrink = {"tools": [("bash", {"command": "git reset -q --hard HEAD~1"})], "usage": {"prompt": 400, "out": 10}}
    dry.script(over, done(1001), finish(), shrink, *lane(1001))
    assert start(dry, [1001])["items"] == {"1001@lane": "checked"}
    red = [(r["name"], r["text"][-900:]) for e in events("check") if not e["ok"] for r in e["results"] if not r["ok"]]
    assert item()["attempts"] == 1 and [n for n, _ in red] == ["diff-bound"], red


def test_a_compaction_crash_reply_fails_the_item_with_the_text(dry):
    dry.script({"fail": "error:Compaction failed: the summary does not fit the context window"})
    out = start(dry, [1001])
    assert out["items"] == {"1001@lane": "failed"}
    assert "Compaction failed" in item()["history"][-1]


@pytest.mark.xfail(strict=True, reason="GAP: a stream cut mid-turn ends the item `failed` (Pi reports 'Stream ended without finish_reason', which coder.TRANSIENT does not match and nothing re-prompts the worker)")
def test_a_stream_dropped_mid_turn_is_recovered(dry):
    dry.script({"text": "starting", "fail": "drop"}, *lane(1001))
    assert start(dry, [1001])["items"] == {"1001@lane": "checked"}, item()["history"]


def test_a_503_is_retried_by_pi_itself(dry):
    dry.script({"fail": "503"}, *lane(1001))
    assert start(dry, [1001])["items"] == {"1001@lane": "checked"}, item()["history"]


def test_a_429_ends_rate_limited_and_asks_for_the_next_worker(dry):
    dry.script({"fail": "429"})
    assert start(dry, [1001])["items"] == {"1001@lane": "rate-limited"}
    assert any(q["kind"] in ("fallback", "budget") for q in core.state()["queue"].values())


def test_a_server_that_is_down_fails_the_item_loudly_and_stops_the_window(dry, monkeypatch):
    monkeypatch.setattr("pipeline.budget.backoff", lambda attempt, **kw: 1.0)  # the runner's own backoff, shortened
    dry.close()
    out = start(dry, [1001])
    assert out["items"] == {"1001@lane": "failed"}
    assert any(e["event"] == "worker_gone" for e in journal.read())


def test_the_cost_cap_stops_the_worker_and_asks(dry):
    dry.script({"text": "reading everything", "usage": {"prompt": 3_000_000, "out": 10}})  # about US$0.36 at the pinned price
    dry.cfg_cap = core.cfg()["workers"].update(cost_cap_usd=0.05)
    out = start(dry, [1001])
    assert out["items"] == {"1001@lane": "rate-limited"}
    assert any(q["kind"] in ("fallback", "budget") for q in core.state()["queue"].values())


def test_a_stalled_worker_is_stopped_after_the_wait_and_the_item_failed(dry, monkeypatch):
    import functools
    monkeypatch.setattr(coder, "wait_idle", functools.partial(coder.wait_idle, timeout_s=30, poll=3))  # the real wait is an hour
    dry.script({"fail": "hang"})
    assert start(dry, [1001])["items"] == {"1001@lane": "failed"}
    assert "no idle turn" in item()["history"][-1]


@pytest.mark.xfail(strict=True, reason="GAP #6214: a coder window started just before a runner restart never gets its brief; tick() does not resend it")
def test_a_restart_with_an_undelivered_brief_sends_it(dry, monkeypatch):
    real = coder.tell
    def runner_dies(*a, **kw):
        raise KeyboardInterrupt("the runner stopped between starting the window and typing the brief")
    monkeypatch.setattr(coder, "tell", runner_dies)
    with pytest.raises(KeyboardInterrupt):
        start(dry, [1001])
    monkeypatch.setattr(coder, "tell", real)
    dry.script(*lane(1001))
    runner.tick()  # a new runner pass finds a coding item whose worker never got its brief
    assert len(dry.requests) >= 1


def tool_names(body):
    return [t["function"]["name"] for t in body["tools"]]


def test_pi_1_4_with_the_adapter_7_gives_the_worker_its_pipeline_tools_directly(dry):
    """Pi 1.4.0 + pi-mcp-adapter 7.0.0 + the runner's --mcp-config: a worker must see pipeline_done/ask/report/verdict as
    tools of its own, on its FIRST session too (the adapter registers direct tools from a metadata cache that a fresh
    agent dir lacks; the brief tells the worker to call pipeline_done)."""
    dry.script(finish())
    core.start([1001], task="first", from_file=str(dry.folder), provider="openrouter", model=MODEL)
    cache = Path(core.cfg()["workers"]["agent_dir"]) / "mcp-cache.json"
    first = tool_names(dry.requests[0])
    want = {"pipeline_report", "pipeline_ask", "pipeline_done", "pipeline_verdict"}
    n = len(dry.requests)
    dry.script(finish())
    core.start([1002], task="second", from_file=str(dry.folder), provider="openrouter", model=MODEL)
    second = tool_names(dry.requests[n])
    assert want <= set(second), ("second session", sorted(second), cache.exists(), json.loads(cache.read_text()))
    assert want <= set(first), ("first session", sorted(first))


def test_the_feeder_cuts_clusters_and_the_next_cluster_starts_after_the_first(dry, scratch):
    from pipeline import feeder
    spec = {"s.md": "#### Step 1.1 — a (#1001)\n#### Step 1.2 — b (#1002)\n#### Step 1.3 — c (#1003)\n"}
    cut = feeder.cluster([issue(n) for n in (1003, 1001, 1002)], spec, size=2)
    assert cut == {"clusters": [{"spec": "s.md", "issues": [1001, 1002]}, {"spec": "s.md", "issues": [1003]}], "no_spec": []}
    dry.script(*lane(1001), *lane(1002), *lane(1003))
    for i, c in enumerate(cut["clusters"], 1):
        out = core.start(c["issues"], task=f"cluster-{i}", from_file=str(dry.folder), provider="openrouter", model=MODEL)
        assert set(out["items"].values()) == {"checked"}, out
    briefs = sorted((core.STATE / "briefs").rglob("issue-*-attempt-1.md"))
    assert len(briefs) == 3 and all("Diff bound: 20 lines" in b.read_text() and "src/mod.py" in b.read_text() for b in briefs)
    assert {t for t in core.state()["tasks"]} == {"cluster-1", "cluster-2"}
