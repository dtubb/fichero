"""The second macOS user workers and the ladder run as (review 2 B3; owner ruling 2026-10-31).

The wall is the OS's: the jailed user has no GitHub credential, no ssh key and no read on the owner's home, and its
tmux socket is its own. The owner creates the user and one narrow sudoers line (`<owner> ALL=(<user>) NOPASSWD: ALL`
is enough on a single-owner Mac); a missing user REFUSES, it never falls back to running as the owner.
Stdlib only (the Builder may become its own app).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_CD_EXEC = 'cd "$1" && shift && exec "$@"'


class JailMissing(RuntimeError):
    """The configured user does not exist or sudo to it is not set up. Never fall back."""


@dataclass(frozen=True)
class Jail:
    user: str
    workroot: str = ""                 # shared dir (made by the owner, readable+writable by both) for trees and scratch
    deny_read: tuple = ()              # paths the user must NOT be able to read (the probe checks each)
    sudo: str = "sudo"
    _checked: list = field(default_factory=list, compare=False, repr=False, hash=False)

    def require(self) -> None:
        """Refuse unless the user exists, is not the current user, and `sudo -n -u user` works."""
        if not self.user:
            raise JailMissing("no jail user configured")
        r = subprocess.run(["id", "-u", self.user], capture_output=True, text=True)
        if r.returncode:
            raise JailMissing(f"jail user {self.user!r} does not exist: the owner creates it (sysadminctl -addUser)")
        if int(r.stdout) == os.getuid():
            raise JailMissing(f"jail user {self.user!r} is the current user: that is no jail")
        t = subprocess.run([self.sudo, "-n", "-u", self.user, "-H", "true"], capture_output=True, text=True)
        if t.returncode:
            raise JailMissing(f"cannot sudo to {self.user!r} without a password (sudoers line missing?): {t.stderr.strip()[:200]}")
        if self.workroot and not os.access(self.workroot, os.W_OK | os.X_OK):
            raise JailMissing(f"workroot {self.workroot!r} is missing or not writable by the engine's user")

    def argv(self, argv: list[str], cwd=None, env: dict | None = None) -> list[str]:
        """`argv` as the jailed user: clean environment (only `env`), HOME the user's own, optional cwd."""
        e = [f"{k}={v}" for k, v in (env or {}).items() if k != "HOME"]
        inner = argv if cwd is None else ["/bin/sh", "-c", _CD_EXEC, "sh", str(cwd), *argv]
        # sudo -H sets the user's own HOME; env -i then drops everything else the caller had
        return [self.sudo, "-n", "-u", self.user, "-H", "/bin/sh", "-c", 'exec /usr/bin/env -i HOME="$HOME" "$@"', "sh", *e, *inner]

    def mkdtemp(self, prefix: str) -> str:
        """A scratch dir the jailed user can write: under the workroot, mode 0777 (public data only lives here)."""
        d = tempfile.mkdtemp(prefix=prefix, dir=self.workroot or None)
        os.chmod(d, 0o777)
        return d

    def probe(self) -> list[str]:
        """The once-per-setup proof (M7): as the jailed user, every `deny_read` path is unreadable and `gh` has no login.
        Returns the failures (empty = the wall holds)."""
        bad = []
        for p in self.deny_read:
            r = subprocess.run(self.argv(["/bin/sh", "-c", f"test -r {shlex.quote(str(Path(p).expanduser()))}"], env={}),
                               capture_output=True)
            if r.returncode == 0:
                bad.append(f"{p} is readable by {self.user}")
        gh = subprocess.run(self.argv(["/bin/sh", "-c", "command -v gh >/dev/null && gh auth status"], env={"PATH": os.environ.get("PATH", "")}),
                            capture_output=True)
        if gh.returncode == 0:
            bad.append(f"{self.user} is signed in to gh")
        return bad


def load(root) -> Jail | None:
    """`[jail]` of `<root>/harness.toml`; none configured = None (callers decide whether that is allowed)."""
    import tomllib
    f = Path(root) / "harness.toml"
    c = tomllib.loads(f.read_text()).get("jail") if f.is_file() else None
    if not c:
        return None
    return Jail(user=c.get("user", ""), workroot=c.get("workroot", ""), deny_read=tuple(c.get("deny_read", ())),
                sudo=c.get("sudo", "sudo"))
