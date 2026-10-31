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

from pipeline import ROOT, coder, core, journal
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
                          batch_end_pct=80, cost_cap_usd=1.0)
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
