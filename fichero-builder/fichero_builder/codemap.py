"""The code map for jail workers (dev-workflows.run.code-map): jcodemunch where the worker can run it. `[jail].code_map` names the
owner's install; it is a pipx script whose shebang and venv live under the owner's home, which the worker cannot read, so
the whole venv is copied to `<workroot>/jcodemunch/venv` and `<workroot>/bin/jcodemunch-mcp` runs the script with the copy's
python. Everything here is optional: no setting, no install or a failed copy means a worker that greps, never a refusal."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import threading
import tomllib
from pathlib import Path

TEST_PATH = re.compile(r"(^|/)(tests?|Tests)/|(^|/)test_|Tests?\.swift$")
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
        for d in (home, w.parent):  # the workroot is world-writable: a worker's link here would have the owner copy and chmod through it
            try:
                os.mkdir(d, 0o755)  # made first, never `exist_ok`: a check before the mkdir left a window for a planted link
            except FileExistsError:
                pass
            if d.is_symlink() or d.lstat().st_uid != os.getuid():
                raise OSError(f"{d} is not this user's folder")
        if not (w.is_file() and stamp.is_file() and stamp.read_text() == want):
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


def owner_binary(root) -> str:
    """The owner's own install, for the search behind a step's Where list; '' when none is set or it is missing."""
    t = _jail_table(root)
    p = Path(t["code_map"]).expanduser() if t.get("code_map") else None
    return str(p) if p and p.is_file() else ""


def search(binary: str, repo_dir: str, words: list[str], timeout_s: float = 60.0, limit: int = 10) -> dict[str, list[str]] | None:
    """{file: ["name (line)", ...]} from a stdio MCP call to the server: the step's words through search_symbols and
    search_text, then each file's outline. None when the server cannot answer or the repo is not indexed (the caller greps)."""
    if not binary:
        return None
    try:
        p = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                             env={**os.environ, "JCODEMUNCH_DEFAULT_FORMAT": "json"})
    except OSError:
        return None
    guard = threading.Timer(timeout_s, p.kill)  # a hung server costs a grep, never the verb
    guard.start()
    n = [0]

    def call(method: str, params: dict) -> dict:
        n[0] += 1
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n[0], "method": method, "params": params}) + "\n")
        p.stdin.flush()
        for line in p.stdout:
            r = json.loads(line)
            if r.get("id") == n[0]:
                return r["result"]
        raise OSError("the server closed its output")

    def tool(name: str, **args) -> dict:
        return json.loads(call("tools/call", {"name": name, "arguments": args})["content"][0]["text"])

    try:
        call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "builder", "version": "1"}})
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        p.stdin.flush()
        found = tool("resolve_repo", path=str(repo_dir))
        if not found.get("indexed"):
            return None
        repo = found["repo"]
        files = [r["file"] for r in tool("search_symbols", repo=repo, query=" ".join(words), max_results=limit, detail_level="compact").get("results", [])]
        for w in words:
            files += [r["file"] for r in tool("search_text", repo=repo, query=w, max_results=limit).get("results", [])]
        files = [f for f in dict.fromkeys(files) if (Path(repo_dir) / f).is_file()]
        files = sorted(files, key=lambda f: bool(TEST_PATH.search(f)))[:limit]  # stable: the search's rank, the code before its tests
        if not files:
            return None
        outlines = tool("get_file_outline", repo=repo, file_paths=files).get("results", [])
        by_file = {o.get("file"): [f"{x['name']} ({x['line']})" for x in o.get("symbols", [])[:12]] for o in outlines}
        return {f: by_file[f] for f in files if f in by_file}
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    finally:
        guard.cancel()
        p.kill()
        p.wait()
