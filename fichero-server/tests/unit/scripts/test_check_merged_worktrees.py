"""Unit tests for scripts/check_merged_worktrees.py (pins `git.cleanup-merged-worktrees`).

All git calls are monkeypatched — this suite must NEVER touch the real worktree tree.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_merged_worktrees.py"
_SPEC = importlib.util.spec_from_file_location("check_merged_worktrees", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


PORCELAIN_TWO_LANES = """worktree /code/fichero
HEAD aaaaaaa
branch refs/heads/main

worktree /code/fichero-worktrees/merged-lane
HEAD bbbbbbb
branch refs/heads/merged-lane

worktree /code/fichero-worktrees/active-lane
HEAD ccccccc
branch refs/heads/active-lane
"""


def _wire(monkeypatch, porcelain: str, current_path: str, merged_refs: set[str]) -> None:
    monkeypatch.setattr(_mod, "_git_worktree_list_porcelain", lambda: porcelain)
    monkeypatch.setattr(_mod, "_current_worktree_path", lambda: current_path)
    monkeypatch.setattr(_mod, "_is_ancestor_of_main", lambda ref: ref in merged_refs)


def test_parse_porcelain_reads_path_head_branch():
    entries = _mod.parse_porcelain(PORCELAIN_TWO_LANES)
    assert len(entries) == 3
    assert entries[0] == {"path": "/code/fichero", "head": "aaaaaaa", "branch": "main", "bare": False}
    assert entries[1]["branch"] == "merged-lane"


def test_parse_porcelain_detached_head_has_no_branch():
    text = "worktree /code/detached\nHEAD ddddddd\ndetached\n"
    entries = _mod.parse_porcelain(text)
    assert entries[0]["branch"] is None
    assert entries[0]["head"] == "ddddddd"


def test_merged_lane_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", tmp_path / "allowlist.json")
    _wire(monkeypatch, PORCELAIN_TWO_LANES, "/code/fichero-worktrees/active-lane",
          merged_refs={"merged-lane"})
    assert _mod.check() == 1


def test_unmerged_lane_is_not_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", tmp_path / "allowlist.json")
    _wire(monkeypatch, PORCELAIN_TWO_LANES, "/code/fichero-worktrees/active-lane",
          merged_refs=set())
    assert _mod.check() == 0


def test_main_checkout_and_current_worktree_are_never_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", tmp_path / "allowlist.json")
    # Everything (including main and the current worktree) reports as "merged" — only a
    # non-main, non-current worktree may ever be flagged.
    _wire(monkeypatch, PORCELAIN_TWO_LANES, "/code/fichero-worktrees/active-lane",
          merged_refs={"main", "merged-lane", "active-lane"})
    entries = _mod.parse_porcelain(PORCELAIN_TWO_LANES)
    lingering = _mod.find_lingering(entries, "/code/fichero-worktrees/active-lane")
    assert [e["path"] for e in lingering] == ["/code/fichero-worktrees/merged-lane"]


def test_allowlisted_merged_lane_is_not_flagged(tmp_path, monkeypatch):
    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text(json.dumps([
        {"path": "/code/fichero-worktrees/merged-lane", "reason": "kept for a hotfix reference"},
    ]), encoding="utf-8")
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", allowlist_path)
    _wire(monkeypatch, PORCELAIN_TWO_LANES, "/code/fichero-worktrees/active-lane",
          merged_refs={"merged-lane"})
    assert _mod.check() == 0


def test_stale_allowlist_entry_fails(tmp_path, monkeypatch):
    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text(json.dumps([
        {"path": "/code/fichero-worktrees/gone-lane", "reason": "no longer exists"},
    ]), encoding="utf-8")
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", allowlist_path)
    _wire(monkeypatch, PORCELAIN_TWO_LANES, "/code/fichero-worktrees/active-lane",
          merged_refs=set())
    assert _mod.check() == 1


def test_allowlist_entry_without_reason_fails(tmp_path, monkeypatch):
    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text(json.dumps([
        {"path": "/code/fichero-worktrees/merged-lane", "reason": ""},
    ]), encoding="utf-8")
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", allowlist_path)
    _wire(monkeypatch, PORCELAIN_TWO_LANES, "/code/fichero-worktrees/active-lane",
          merged_refs={"merged-lane"})
    assert _mod.check() == 1


def test_never_calls_a_mutating_git_command(monkeypatch):
    calls: list[list[str]] = []

    class _FakeCompleted:
        returncode = 0
        stdout = PORCELAIN_TWO_LANES
        stderr = ""

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(_mod.subprocess, "run", _fake_run)
    _mod._git_worktree_list_porcelain()
    for cmd in calls:
        assert cmd[:2] == ["git", "worktree"] and cmd[2] == "list", f"unexpected: {cmd}"
        assert "remove" not in cmd and "prune" not in cmd
