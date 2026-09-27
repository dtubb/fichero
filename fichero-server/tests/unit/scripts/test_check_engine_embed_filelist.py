"""The embed filelist's source set is what git sees, not what this disk holds.

52908912d regenerated `FicheroEngineEmbedInputs.xcfilelist` in a checkout holding a
`.ruff_cache/` and a locally built `resources/bin/fm-bridge` — gitignored, both — so the
committed list named four files no fresh checkout has and the check was red in every clean
worktree. The list decides whether an embedded build re-runs the engine embed phase, so a
wrong answer here ships a stale engine; a check that is red for local junk gets ignored.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_engine_embed_filelist.py"
_SPEC = importlib.util.spec_from_file_location("check_engine_embed_filelist_t", _SCRIPT)
assert _SPEC and _SPEC.loader
embed = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = embed
_SPEC.loader.exec_module(embed)  # type: ignore[attr-defined]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    src = tmp_path / "fichero-server" / "src" / "fichero_server"
    (src / "api").mkdir(parents=True)
    (src / "api" / "routes.py").write_text("x = 1\n")
    (src / ".ruff_cache").mkdir()
    (src / ".ruff_cache" / ".gitignore").write_text("*\n")
    (src / ".ruff_cache" / "CACHEDIR.TAG").write_text("tag\n")
    (src / "resources" / "bin").mkdir(parents=True)
    (src / "resources" / "bin" / ".gitignore").write_text("*\n!.gitignore\n")
    (src / "resources" / "bin" / "fm-bridge").write_text("binary\n")
    (src / "api" / "__pycache__").mkdir()
    (src / "api" / "__pycache__" / "routes.cpython-312.pyc").write_text("")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    monkeypatch.setattr(embed, "ROOT", tmp_path)
    monkeypatch.setattr(embed, "ENGINE_SRC", src)
    return src


def test_gitignored_local_files_are_not_engine_sources(repo):
    """If this fails, regenerating in a checkout with caches or built binaries commits
    them into the list, and every clean checkout's check goes red again."""
    sources = embed.real_engine_sources()
    assert not any(".ruff_cache/CACHEDIR.TAG" in s or s.endswith("fm-bridge") for s in sources)
    assert not any("__pycache__" in s for s in sources)


def test_tracked_and_new_untracked_sources_are_listed(repo):
    """Over-fire check: a tracked source is listed, and so is one a lane has just added
    but not committed — excluding it would let an uncommitted engine edit skip re-embed."""
    (repo / "api" / "new_route.py").write_text("y = 2\n")
    sources = embed.real_engine_sources()
    assert "fichero-server/src/fichero_server/api/routes.py" in sources
    assert "fichero-server/src/fichero_server/api/new_route.py" in sources
