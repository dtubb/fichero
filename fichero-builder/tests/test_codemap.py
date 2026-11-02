"""The code map for jail workers (dev-workflows.run.code-map): the owner's jcodemunch install copied where the worker can read
it, registered in the worker's mcp.json, the worktree indexed as the worker before the session starts. A fake install."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types

import pytest

from fichero_builder import codemap, start_tool, work

SERVER = """#!/usr/bin/env python3
import os, sys
print("ran", sys.argv[1:], os.environ.get("JCODEMUNCH_MAX_FOLDER_FILES"))
"""


@pytest.fixture
def world(tmp_path):
    venv = tmp_path / "home" / "pipx" / "venv"
    (venv / "bin").mkdir(parents=True)
    os.symlink(sys.executable, venv / "bin" / "python")
    (venv / "bin" / "jcodemunch-mcp").write_text(SERVER.replace("/usr/bin/env python3", str(tmp_path / "owner-only" / "python")))  # a shebang the worker cannot run
    link = tmp_path / "home" / "bin-jc"
    os.symlink(venv / "bin" / "jcodemunch-mcp", link)
    wr = tmp_path / "wr"
    (wr / "bin").mkdir(parents=True)
    (tmp_path / "harness.toml").write_text(f'[jail]\nuser = "wu"\nworkroot = "{wr}"\ncode_map = "{link}"\n[check]\nengine_repo = "/e"\n')
    return types.SimpleNamespace(root=tmp_path, wr=wr, venv=venv, link=link)


def test_provide_copies_the_install_and_the_wrapper_runs_it_past_the_owner_only_shebang(world):
    w = codemap.provide(world.root)
    assert w == str(world.wr / "bin" / "jcodemunch-mcp")
    out = subprocess.run([w, "index", "/x"], capture_output=True, text=True).stdout
    assert "ran ['index', '/x']" in out and str(codemap.MAX_FILES) in out, "the whole repo, not the default 2000 files"
    assert os.stat(w).st_mode & 0o555 == 0o555 and os.stat(world.wr / "jcodemunch" / "venv" / "bin" / "jcodemunch-mcp").st_mode & 0o444 == 0o444


def test_provide_copies_once_and_again_after_an_upgrade(world):
    codemap.provide(world.root)
    marker = world.wr / "jcodemunch" / "venv" / "marker"
    marker.write_text("kept")
    codemap.provide(world.root)
    assert marker.exists(), "same install: not copied again"
    script = world.venv / "bin" / "jcodemunch-mcp"
    os.utime(script, (1, 1))
    codemap.provide(world.root)
    assert not marker.exists(), "an upgraded install is copied again"


def test_no_setting_or_a_missing_install_is_no_code_map_never_a_failure(world, tmp_path):
    (world.root / "harness.toml").write_text(f'[jail]\nuser = "wu"\nworkroot = "{world.wr}"\n')
    assert codemap.provide(world.root) == ""
    (world.root / "harness.toml").write_text(f'[jail]\nuser = "wu"\nworkroot = "{world.wr}"\ncode_map = "{tmp_path / "nowhere"}"\n')
    assert codemap.provide(world.root) == ""


def test_a_failed_copy_says_why_and_the_worker_still_runs(world, monkeypatch, capsys):
    monkeypatch.setattr(codemap.shutil, "copytree", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    assert codemap.provide(world.root) == ""
    assert "disk full" in capsys.readouterr().out


def test_prepare_registers_only_the_copied_server_and_keeps_the_strict_config(world, tmp_path, monkeypatch):
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    w = codemap.provide(world.root)
    argv = start_tool.prepare(world.root, wt, "do it", tmp_path / "scratch")
    assert json.loads((tmp_path / "scratch" / "mcp.json").read_text()) == {"mcpServers": {"jcodemunch": {"type": "stdio", "command": w, "args": [], "env": {}}}}
    assert "--strict-mcp-config" in argv


def test_the_worker_side_command_indexes_the_worktree_first_and_a_failed_index_does_not_stop_it(world):
    codemap.provide(world.root)
    a = types.SimpleNamespace(pinned=str(world.root), worktree="/wr/wt", brief="/b", root=str(world.root), name="n", kind="claude", session="s", tick=30.0)
    cmd = work.run_cmd(a, "sonnet")
    index, _, rest = cmd.partition("; ")
    assert index.endswith("index /wr/wt --no-ai-summaries >/dev/null 2>&1") and "-m fichero_builder run" in rest


def test_the_standing_rules_tell_the_worker_to_find_code_with_the_map():
    import tomllib
    from pathlib import Path

    rules = tomllib.loads((Path(codemap.__file__).resolve().parents[2] / "harness.toml").read_text())
    assert "search_symbols" in rules["brief"]["rules"] and "Read only a file you edit" in rules["brief"]["rules"]
    assert rules["jail"]["code_map"].startswith("~/"), "no owner path in the public rules file beyond what ~ means"


def test_a_planted_install_folder_refuses_the_copy_and_touches_nothing_behind_it(world, tmp_path, capsys):
    """The workroot is world-writable: a worker's symlink at `jcodemunch` would have the owner copy and chmod through it."""
    private = tmp_path / "private"
    private.mkdir()
    (world.wr / "jcodemunch").symlink_to(private)
    assert codemap.provide(world.root) == ""
    assert list(private.iterdir()) == [] and "not provided" in capsys.readouterr().out
