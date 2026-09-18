"""Unit tests for scripts/check_no_orphan_stashes.py (pins `git.commit-never-stash`).

`git stash list` is monkeypatched everywhere — this suite must NEVER touch the real shared
stash stack.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_no_orphan_stashes.py"
_SPEC = importlib.util.spec_from_file_location("check_no_orphan_stashes", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


def _fake_stash(monkeypatch, n: int) -> None:
    entries = [f"stash@{{{i}}}: WIP on x: entry {i}" for i in range(n)]
    monkeypatch.setattr(_mod, "_git_stash_list", lambda: entries)
    monkeypatch.setattr(_mod, "_git_stash_list_named", lambda: "\n".join(entries[:5]))


def _seed_ceiling(tmp_path, monkeypatch, ceiling) -> None:
    path = tmp_path / "stash_ceiling.json"
    monkeypatch.setattr(_mod, "CEILING_PATH", path)
    if ceiling is not None:
        path.write_text(json.dumps(ceiling), encoding="utf-8")


def test_count_equal_to_ceiling_passes(tmp_path, monkeypatch):
    _fake_stash(monkeypatch, 19)
    _seed_ceiling(tmp_path, monkeypatch, {"ceiling": 19, "reason": "x"})
    assert _mod.check() == 0


def test_count_above_ceiling_fails_and_names_newest(tmp_path, monkeypatch, capsys):
    _fake_stash(monkeypatch, 20)
    _seed_ceiling(tmp_path, monkeypatch, {"ceiling": 19, "reason": "x"})
    rc = _mod.check()
    out = capsys.readouterr().out
    assert rc == 1
    assert "above the ceiling" in out
    assert "entry 0" in out  # the named-entries listing is included


def test_count_below_ceiling_fails_asking_to_lower_it(tmp_path, monkeypatch, capsys):
    _fake_stash(monkeypatch, 18)
    _seed_ceiling(tmp_path, monkeypatch, {"ceiling": 19, "reason": "x"})
    rc = _mod.check()
    out = capsys.readouterr().out
    assert rc == 1
    assert "lower the ceiling" in out


def test_malformed_ceiling_json_exits_2(tmp_path, monkeypatch):
    path = tmp_path / "stash_ceiling.json"
    monkeypatch.setattr(_mod, "CEILING_PATH", path)
    path.write_text("{not valid json", encoding="utf-8")
    _fake_stash(monkeypatch, 19)
    try:
        _mod._load_ceiling()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 2


def test_missing_ceiling_file_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "CEILING_PATH", tmp_path / "does_not_exist.json")
    try:
        _mod._load_ceiling()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 2


def test_ceiling_missing_integer_field_exits_2(tmp_path, monkeypatch):
    path = tmp_path / "stash_ceiling.json"
    monkeypatch.setattr(_mod, "CEILING_PATH", path)
    path.write_text(json.dumps({"reason": "no ceiling key"}), encoding="utf-8")
    try:
        _mod._load_ceiling()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 2


# --- --update-ceiling: lower-only, plus first-time seeding ------------------------------

def test_update_ceiling_first_time_seeding_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "CEILING_PATH", tmp_path / "stash_ceiling.json")
    _fake_stash(monkeypatch, 19)
    assert _mod.update_ceiling() == 0
    data = json.loads(_mod.CEILING_PATH.read_text(encoding="utf-8"))
    assert data["ceiling"] == 19


def test_update_ceiling_refuses_to_raise(tmp_path, monkeypatch, capsys):
    _seed_ceiling(tmp_path, monkeypatch, {"ceiling": 19, "reason": "x"})
    _fake_stash(monkeypatch, 20)  # a new, un-committed stash — the escape hatch this closes
    rc = _mod.update_ceiling()
    err = capsys.readouterr().err
    assert rc == 2
    assert "refusing to raise it" in err
    # The file on disk must be untouched — the refusal must not partially write.
    data = json.loads(_mod.CEILING_PATH.read_text(encoding="utf-8"))
    assert data["ceiling"] == 19


def test_update_ceiling_lowers_when_count_drops(tmp_path, monkeypatch):
    _seed_ceiling(tmp_path, monkeypatch, {"ceiling": 19, "reason": "x"})
    _fake_stash(monkeypatch, 15)
    assert _mod.update_ceiling() == 0
    data = json.loads(_mod.CEILING_PATH.read_text(encoding="utf-8"))
    assert data["ceiling"] == 15


def test_update_ceiling_is_a_noop_when_equal(tmp_path, monkeypatch, capsys):
    _seed_ceiling(tmp_path, monkeypatch, {"ceiling": 19, "reason": "x"})
    _fake_stash(monkeypatch, 19)
    rc = _mod.update_ceiling()
    out = capsys.readouterr().out
    assert rc == 0
    assert "no-op" in out
    data = json.loads(_mod.CEILING_PATH.read_text(encoding="utf-8"))
    assert data["ceiling"] == 19  # unchanged (still the original file, not rewritten to drop `reason`)


def test_never_calls_a_mutating_git_command(monkeypatch):
    """Guards the read-only contract itself: `subprocess.run` is only ever called with
    `git stash list` (with or without --format), never pop/drop/clear."""
    calls: list[list[str]] = []

    class _FakeCompleted:
        returncode = 0
        stdout = "stash@{0}: WIP on x: entry\n"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(_mod.subprocess, "run", _fake_run)
    _mod._git_stash_list()
    _mod._git_stash_list_named()
    for cmd in calls:
        assert cmd[:3] == ["git", "stash", "list"], f"unexpected git command: {cmd}"
        assert "pop" not in cmd and "drop" not in cmd and "clear" not in cmd
