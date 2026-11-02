"""The code map for jail workers (dev-workflows.run.code-map): jcodemunch where the worker can run it. `[jail].code_map` names the
owner's install; it is a pipx script whose shebang and venv live under the owner's home, which the worker cannot read, so
the whole venv is copied to `<workroot>/jcodemunch/venv` and `<workroot>/bin/jcodemunch-mcp` runs the script with the copy's
python. Everything here is optional: no setting, no install or a failed copy means a worker that greps, never a refusal."""
from __future__ import annotations

import os
import shlex
import shutil
import stat
import tomllib
from pathlib import Path

MAX_FILES = 20000  # jcodemunch's default stops at 2000 files, a fraction of this repo


def _jail_table(root) -> dict:
    f = Path(root) / "harness.toml"
    return tomllib.loads(f.read_text()).get("jail", {}) if f.is_file() else {}


def wrapper(root) -> str:
    """The copied server's command if one is in place, else ''."""
    t = _jail_table(root)
    if not (t.get("code_map") and t.get("workroot")):
        return ""
    w = Path(t["workroot"]) / "bin" / "jcodemunch-mcp"
    return str(w) if w.is_file() else ""


def provide(root, say=print) -> str:
    """As the owner, before a worker starts: the copy and its wrapper, made once and again after an upgrade. The wrapper's path, or ''."""
    t = _jail_table(root)
    if not (t.get("code_map") and t.get("workroot")):
        return ""
    script = Path(t["code_map"]).expanduser().resolve()
    if not script.is_file():
        return ""
    home = Path(t["workroot"]) / "jcodemunch"
    venv, stamp = home / "venv", home / "installed-from"
    want = str(script.stat().st_mtime_ns)
    w = Path(t["workroot"]) / "bin" / "jcodemunch-mcp"
    try:
        if not (w.is_file() and stamp.is_file() and stamp.read_text() == want):
            home.mkdir(parents=True, exist_ok=True)
            tmp = home / "venv.tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(script.parents[1], tmp, symlinks=True)
            shutil.rmtree(venv, ignore_errors=True)
            tmp.rename(venv)
            for d, dirs, files in os.walk(venv):
                os.chmod(d, 0o755)
                for n in files:
                    p = Path(d) / n
                    if not p.is_symlink():
                        p.chmod(p.stat().st_mode | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            q = shlex.quote
            w.parent.mkdir(parents=True, exist_ok=True)
            w.write_text(f'#!/bin/sh\nJCODEMUNCH_MAX_FOLDER_FILES={MAX_FILES} exec {q(str(venv / "bin" / "python"))} {q(str(venv / "bin" / script.name))} "$@"\n')
            w.chmod(0o755)
            stamp.write_text(want)
    except OSError as e:
        say(f"code map: not provided ({e}); the worker will grep")
        return ""
    return str(w)


def mcp_config(root) -> dict:
    """What the worker's `--strict-mcp-config` file holds: the copied server when there is one, nothing else."""
    w = wrapper(root)
    return {"mcpServers": {"jcodemunch": {"type": "stdio", "command": w, "args": [], "env": {}}} if w else {}}


def index_prefix(root, worktree) -> str:
    """Shell to run as the worker before the session: `<wrapper> index <worktree> ...; ` (a failed index never stops the worker)."""
    w = wrapper(root)
    return f"{shlex.quote(w)} index {shlex.quote(str(worktree))} --no-ai-summaries >/dev/null 2>&1; " if w else ""
