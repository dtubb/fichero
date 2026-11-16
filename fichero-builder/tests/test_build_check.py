"""dev-workflows.run.build-check (design batch ii, manager 2026-11-04): `builder build-check <lane>` runs the app's build rung over the lane's
HEAD before its done, jailed and in the stable build tree like the ladder's rung; a red prints every error line and the log; a green
key is stored, so the ladder's own build rung reuses it. Fakes: no fetch, no xcodebuild."""
from __future__ import annotations

import types

import pytest

from fichero_builder import check_tool, jail, journal, queue


@pytest.fixture
def lane(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/engine"\n[land]\nbranch = "integration"\n')
    queue.add("ext", "/w/ext", "1.1", str(tmp_path / "b1.1"), [7], kind="external")
    seen = []
    monkeypatch.setattr(check_tool, "load", lambda root: check_tool.Config(build=("xcodebuild", "build"), build_paths=("fichero/",)))
    monkeypatch.setattr(jail, "load", lambda root: None)
    monkeypatch.setattr(check_tool, "_scratch_tree", lambda repo, head, pinned, cfg: (seen.append(("tree", head)), "/scratch")[1])
    monkeypatch.setattr(check_tool, "_git", lambda repo, *args: seen.append(("git", args)) or {"ok": True})
    w = types.SimpleNamespace(ensure_pinned=lambda root, brief, base: str(tmp_path), r_since=lambda repo, branch: "b" * 40,
                              do_fetch=lambda a, repo, branch: (seen.append(("fetch", a.name)), "f" * 40)[1])
    return tmp_path, w, seen, monkeypatch


def test_a_red_build_check_prints_every_error_and_the_log_and_removes_its_scratch_tree(lane):
    root, w, seen, mp = lane
    calls = []
    mp.setattr(check_tool, "build", lambda tree, changed, cfg: (calls.append((tree, changed)), {"ok": False, "results": [
        {"name": "build", "ok": False, "seconds": 41.0, "errors": "Foo.swift:12:5: error: cannot find 'visionIsUnknown' in scope",
         "log": "/s/build-logs/build-1.log"}]})[1])
    rc, msg = queue.build_head(root, "ext", w)
    assert rc == 1 and "ext at fffffffff: BUILD RED" in msg
    assert "Foo.swift:12:5: error: cannot find 'visionIsUnknown'" in msg and "log: /s/build-logs/build-1.log" in msg
    assert calls == [("/scratch", ["fichero/"])], "the build paths are the change: it always compiles"
    assert seen[0] == ("fetch", "ext-check") and ("git", ("worktree", "remove", "--force", "/scratch")) in seen
    (row,) = [r for r in journal.read() if r["event"] == "build-check"]
    assert row["ok"] is False and row["head"] == "f" * 40 and row["log"] == "/s/build-logs/build-1.log"


def test_a_green_build_check_says_whether_it_built_or_reused_and_an_unknown_lane_is_refused(lane):
    root, w, seen, mp = lane
    mp.setattr(check_tool, "build", lambda tree, changed, cfg: {"ok": True, "results": [{"ok": True, "seconds": 0, "reused": "k" * 64}]})
    rc, msg = queue.build_head(root, "ext", w)
    assert rc == 0 and "BUILD GREEN (reused a green build of the same tree)" in msg
    mp.setattr(check_tool, "build", lambda tree, changed, cfg: {"ok": True, "results": [{"ok": True, "seconds": 95.2}]})
    assert "BUILD GREEN (built in 95.2 s); the ladder's build rung will reuse it" in queue.build_head(root, "ext", w)[1]
    assert queue.build_head(root, "nope", w) == (1, "REFUSED: no lane 'nope'")
