"""The embedded engine is rebuilt when ANY shipped engine source file changes, not only a .py.

`scripts/rebuild-engine-if-stale.sh` decides whether the Dev Embedded app re-embeds the engine.
It looked at `*.py` only, so a change to the Reader's served page (api/templates/document_view.html)
left the bundle "up to date" and the app shipped the old Reader, the same trap the script's own
comment records for pyproject.toml. Bytecode is not source, so it must not trigger a rebuild.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "rebuild-engine-if-stale.sh"


def _tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / SCRIPT.name)
    server = root / "fichero-server"
    stub = server / "scripts" / "build_backend_bundle.sh"
    stub.parent.mkdir(parents=True)
    stub.write_text("#!/bin/bash\necho STUB-BUILD\n")
    stub.chmod(0o755)
    src = server / "src" / "fichero_server" / "api" / "templates"
    src.mkdir(parents=True)
    (src / "document_view.html").write_text("<p>old</p>")
    (server / "src" / "fichero_server" / "app.py").write_text("x = 1\n")
    stamp = server / "build" / "fichero_server" / "macos" / "app" / "Fichero Server.app" / "Contents" / "Info.plist"
    stamp.parent.mkdir(parents=True)
    past = time.time() - 60
    for f in (stub, src / "document_view.html", server / "src" / "fichero_server" / "app.py"):
        os.utime(f, (past, past))
    stamp.write_text("<plist/>")  # the bundle is newer than every source file
    return root, src / "document_view.html"


def _run(root: Path) -> str:
    return subprocess.run(
        ["bash", str(root / "scripts" / SCRIPT.name)], capture_output=True, text=True, check=True
    ).stdout


def test_a_fresh_bundle_is_not_rebuilt(tmp_path):
    root, _ = _tree(tmp_path)
    assert "up to date" in _run(root)


def test_a_changed_reader_page_rebuilds_the_bundle(tmp_path):
    root, page = _tree(tmp_path)
    page.write_text("<p>new</p>")
    out = _run(root)
    assert "STUB-BUILD" in out, f"a changed document_view.html must rebuild the engine: {out}"


def test_bytecode_alone_does_not_rebuild(tmp_path):
    root, page = _tree(tmp_path)
    cache = page.parent.parent / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-312.pyc").write_bytes(b"\0")
    assert "up to date" in _run(root)
