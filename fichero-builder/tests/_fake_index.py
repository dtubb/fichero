"""Fake jcodemunch and jdocmunch installs for tests of the start path: a harness.toml [jail] naming both, copied under the workroot."""
from __future__ import annotations

import os
import sys

from fichero_builder import codemap

SERVER = "#!/usr/bin/env python3\nimport sys\nsys.exit(int(open(__file__ + '.exit').read()) if __import__('os').path.exists(__file__ + '.exit') else 0)\n"


def install(tmp_path, name):
    venv = tmp_path / "home" / name / "venv"
    (venv / "bin").mkdir(parents=True)
    os.symlink(sys.executable, venv / "bin" / "python")
    script = venv / "bin" / f"{name}-mcp"
    script.write_text(SERVER)
    return script


def write_rules(root, extra=""):
    """harness.toml with the [jail] for both servers (+ `extra` tables); the wrappers are made. Returns the workroot."""
    wr = root / "wr"
    (wr / "bin").mkdir(parents=True, exist_ok=True)
    code, doc = install(root, "jcodemunch"), install(root, "jdocmunch")
    (root / "harness.toml").write_text(f'[jail]\nuser = "wu"\nworkroot = "{wr}"\ncode_map = "{code}"\ndoc_map = "{doc}"\nrequire_index = true\n'
                                       f'doc_index = ["index-local", "{{worktree}}"]\n[check]\nengine_repo = "/e"\n{extra}')
    codemap.provide_all(root)
    return wr
