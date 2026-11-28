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


# the two index servers every worker needs (agent-profiles.mcp.required): the `[jail]` key naming the owner's install, the script's name
INDEX_SERVERS = {"jcodemunch": ("code_map", "jcodemunch-mcp"), "jdocmunch": ("doc_map", "jdocmunch-mcp")}


def wrapper(root, server: str = "jcodemunch") -> str:
    """The copied server's command if one is in place, else ''."""
    t = _jail_table(root)
    key, name = INDEX_SERVERS[server]
    if not (t.get(key) and t.get("workroot")):
        return ""
    w = Path(t["workroot"]) / "bin" / name
    return str(w) if w.is_file() else ""


def provide_all(root, say=print) -> dict[str, str]:
    """`provide` for each index server: {server: wrapper path or ''}."""
    return {s: provide(root, say, s) for s in INDEX_SERVERS}


def provide(root, say=print, server: str = "jcodemunch") -> str:
    """As the owner, before a worker starts: the copy and its wrapper, made once and again after an upgrade. The wrapper's path, or ''."""
    t = _jail_table(root)
    key, name = INDEX_SERVERS[server]
    if not (t.get(key) and t.get("workroot")):
        return ""
    script = Path(t[key]).expanduser().resolve()
    if not script.is_file():
        return ""
    home = Path(t["workroot"]) / server
    venv, stamp = home / "venv", home / "installed-from"
    want = str(script.stat().st_mtime_ns)
    w = Path(t["workroot"]) / "bin" / name
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
            env = f"JCODEMUNCH_MAX_FOLDER_FILES={MAX_FILES} " if server == "jcodemunch" else ""
            w.write_text(f'#!/bin/sh\n{env}exec {q(str(venv / "bin" / "python"))} {q(str(venv / "bin" / script.name))} "$@"\n')
            w.chmod(0o755)
            stamp.write_text(want)
    except OSError as e:
        say(f"{server}: not provided ({e}); the worker cannot start without it")
        return ""
    return str(w)


INDEX_FAILED = 71  # the exit code of a worker command whose index build failed


def index_args(root, server: str, worktree) -> list[str]:
    """The index command's arguments: jcodemunch's own; jdocmunch's from `[jail].doc_index` (a list with `{worktree}`), refused when unset."""
    if server == "jcodemunch":
        return ["index", str(worktree), "--no-ai-summaries"]
    argv = _jail_table(root).get("doc_index")
    if not argv:
        raise ValueError("harness.toml [jail].doc_index (the jdocmunch index arguments, with {worktree}) is not set")
    return [x.replace("{worktree}", str(worktree)) for x in argv]


def index_prefix(root, worktree) -> str:
    """Shell to run as the worker before the session: each provided server's index over the worktree. A failed build prints
    which server and exits INDEX_FAILED, so the session never starts without its index."""
    # 2026-11-27: an unchanged tree still took 40-50 s to index (every file walked and hashed; longer at load 80-100), so each
    # session start waited ~2 min. A build is skipped when the tree's HEAD and status match the last good build's, stamped in the
    # tree's own git dir (it goes with the tree). ponytail: an index deleted by hand under an unchanged tree is not rebuilt until it changes
    wt = shlex.quote(str(worktree))
    # 2026-11-28: seven spec lanes' first builds at once took 8+ min each at load 120, and the loop gave their starts up. One build
    # at a time per worker user (one lock in its home); a start waiting here is still a live start to the loop (its process lives)
    # (no lockf, or no writable home: no lock, never a failed build)
    out = 'lk=; command -v lockf >/dev/null 2>&1 && [ -d "$HOME" ] && [ -w "$HOME" ] && lk="lockf -k $HOME/.fichero-index.lock"; '

    for server in INDEX_SERVERS:
        w = wrapper(root, server)
        if w:
            args = " ".join(shlex.quote(x) for x in index_args(root, server, worktree))
            stamp = f'"$(git -C {wt} rev-parse --absolute-git-dir)/{server}-index.stamp"'
            key = f'"$({{ git -C {wt} rev-parse HEAD; git -C {wt} status --porcelain; }} 2>/dev/null | shasum | cut -c1-40)"'
            out += (f"k={key}; [ \"$(cat {stamp} 2>/dev/null)\" = \"$k\" ] || {{ $lk {shlex.quote(w)} {args} >/dev/null 2>&1 && echo \"$k\" > {stamp} || "
                    f"{{ echo 'index build failed: {server}' >&2; exit {INDEX_FAILED}; }}; }}; ")
    return out


def owner_binary(root) -> str:
    """The owner's own install, for the search behind a step's Where list; '' when none is set or it is missing."""
    t = _jail_table(root)
    p = Path(t["code_map"]).expanduser() if t.get("code_map") else None
    return str(p) if p and p.is_file() else ""


def outlines(binary: str, repo_dir: str, files: list[str], timeout_s: float = 60.0) -> dict[str, list[str]] | None:
    """{file: ["name (line)", ...]} for the given files, from a stdio MCP call to the server's get_file_outline; a file the
    tree lacks is dropped. None when the server cannot answer or the repo is not indexed (the caller reads outlines by regex)."""
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
        files = [f for f in dict.fromkeys(files) if (Path(repo_dir) / f).is_file()]
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
