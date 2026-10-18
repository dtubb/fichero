"""The cluster login's second factor and key (`compute.connect.second-factor-passes-through`, `.ssh-in-process`).

`ssh` asks for a second factor (or a key passphrase) by running its `SSH_ASKPASS` program with the prompt as the
argument. Ours is `askpass.py`: it hands the prompt to the engine over a private socket; the engine holds it in a
`PromptBroker` for the app to show and answer; the answer goes back to ssh and is kept nowhere.

The cluster's private key is the one the app pushes from its Keychain into the engine's own state folder (never
`~/.ssh`, which the sandboxed app cannot read).
"""
from __future__ import annotations

import itertools
import json
import os
import shlex
import re
import shutil
import socket
import stat
import sys
import tempfile
import threading
from pathlib import Path

ASKPASS = Path(__file__).with_name("askpass.py")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SecondFactorRefused(RuntimeError):
    """The person refused, or did not answer in time; the attempt ends with this reason."""


class PromptBroker:
    """The prompts ssh is waiting on, for the app to list and answer. Answers are not kept."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._open: dict[str, dict] = {}
        self._ended: dict[str, str] = {}  # id → "expired" | "refused": why a prompt is gone, for the person to be told
        self.log: list[tuple[str, str]] = []  # (id, reason) in order, so a sign-in can tell what happened to it

    def ask(self, prompt: str, *, timeout: float = 300.0) -> str:
        done = threading.Event()
        entry = {"prompt": prompt, "answer": None, "done": done}
        with self._lock:
            key = str(next(self._ids))
            self._open[key] = entry
        try:
            if not done.wait(timeout):
                self._end(key, "expired")
                raise SecondFactorRefused("no answer to the sign-in prompt in time")
            if entry["answer"] is None:
                self._end(key, "refused")
                raise SecondFactorRefused("the sign-in prompt was refused")
            return entry["answer"]
        finally:
            with self._lock:
                self._open.pop(key, None)

    def _end(self, key: str, reason: str) -> None:
        with self._lock:
            self._ended[key] = reason
            self.log.append((key, reason))

    def ended(self, prompt_id: str) -> str | None:
        """Why a prompt is gone (`expired` or `refused`), or None if it never existed or was answered."""
        with self._lock:
            return self._ended.get(prompt_id)

    def pending(self) -> list[dict]:
        with self._lock:
            return [{"id": k, "prompt": v["prompt"]} for k, v in self._open.items()]

    def answer(self, prompt_id: str, text: str) -> bool:
        with self._lock:
            entry = self._open.get(prompt_id)
        if entry is None:
            return False
        entry["answer"] = text
        entry["done"].set()
        return True

    def refuse(self, prompt_id: str) -> bool:
        with self._lock:
            entry = self._open.get(prompt_id)
        if entry is None:
            return False
        entry["done"].set()  # answer stays None
        return True


_BROKER = PromptBroker()


def prompt_broker() -> PromptBroker:
    """The engine's one broker: the app lists and answers what any login is waiting on."""
    return _BROKER


class AskpassServer:
    """A private unix socket for one login attempt: `askpass.py` sends the prompt, gets the answer back."""

    def __init__(self, broker: PromptBroker, *, timeout: float = 300.0) -> None:
        self.broker, self.timeout = broker, timeout
        # a unix socket path must stay under ~100 bytes, so a short private (0700) folder of its own
        self._dir = Path(tempfile.mkdtemp(prefix="fa", dir="/tmp"))
        self.path = self._dir / "s"
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self._sock.listen(4)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn: socket.socket) -> None:
        with conn:
            try:
                prompt = json.loads(conn.makefile("r").readline())["prompt"]
                conn.sendall((json.dumps({"answer": self.broker.ask(prompt, timeout=self.timeout)}) + "\n").encode())
            except (SecondFactorRefused, ValueError, KeyError, OSError):
                pass  # the helper reads an empty reply as a refusal

    def env(self) -> dict[str, str]:
        wrapper = self._dir / "askpass.sh"
        wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(ASKPASS))} "$@"\n')
        wrapper.chmod(0o700)
        return {"SSH_ASKPASS": str(wrapper), "SSH_ASKPASS_REQUIRE": "force", "FICHERO_ASKPASS_SOCKET": str(self.path)}

    def close(self) -> None:
        self._sock.close()
        shutil.rmtree(self._dir, ignore_errors=True)


def _owner(st: os.stat_result) -> int:
    return st.st_uid


def _control_candidates() -> list[Path]:
    """The engine's own state folder first; a unix socket path must stay under ~100 bytes (the connection's name
    is a 40-character hash), so a long state folder falls back to a per-user folder of /tmp that is checked."""
    from fichero_server.db.paths import server_state_dir

    own = server_state_dir() / "hpc-ssh"
    return [own] if len(str(own)) <= 50 else [Path(f"/tmp/fichero-ssh-{os.getuid()}")]


def control_dir() -> Path:
    """Where the one open connection's socket lives: made 0700, and refused if it is a symlink or another user owns
    it (a folder any local user could pre-create would let them sit in front of the connection)."""
    path = _control_candidates()[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise PermissionError(f"{path} is a symlink: refused")
    if _owner(st) != os.getuid():
        raise PermissionError(f"{path} is owned by another user: refused")
    os.chmod(path, 0o700)
    return path


def _keys_dir() -> Path:
    from fichero_server.db.paths import server_state_dir

    return server_state_dir() / "hpc-keys"


def _checked(cluster_id: str) -> str:
    if not _ID.match(cluster_id or ""):
        raise ValueError(f"not a cluster id: {cluster_id!r}")
    return cluster_id


def cluster_key_path(cluster_id: str) -> Path:
    return _keys_dir() / _checked(cluster_id) / "id_ed25519"


def store_cluster_key(cluster_id: str, private_key: str) -> Path:
    """Write the private key the app pushed (mode 0600, in a 0700 folder)."""
    path = cluster_key_path(cluster_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(private_key if private_key.endswith("\n") else private_key + "\n")
    return path


class KeyExists(RuntimeError):
    """A key is already made for this cluster; replacing it silently would orphan the one in CCDB."""


def make_cluster_key(cluster_id: str) -> str:
    """Make the cluster's Ed25519 pair with the system `ssh-keygen`; the private half stays in the engine's folder
    (0600), the public half is returned to be added in CCDB (`compute.secret.fichero-makes-the-key`)."""
    import subprocess

    path = cluster_key_path(cluster_id)
    if path.exists():
        raise KeyExists(f"{cluster_id} already has a key: show its public half, or remove it first")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    done = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"fichero-{cluster_id}", "-f", str(path)],
                          capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise RuntimeError(f"ssh-keygen failed: {done.stderr.strip()[:200]}")
    os.chmod(path, 0o600)
    return public_key(cluster_id) or ""


def public_key(cluster_id: str) -> str | None:
    """The public half, to show again; None when no key is made."""
    pub = cluster_key_path(cluster_id).with_name("id_ed25519.pub")
    return pub.read_text().strip() if pub.exists() else None


def remove_cluster_key(cluster_id: str) -> None:
    path = cluster_key_path(cluster_id)
    path.with_name("id_ed25519.pub").unlink(missing_ok=True)
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass
