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

# /usr/bin/git is an xcrun shim: a new user's first call runs `xcodebuild -sdk macosx -find git` (minutes under load, looks hung).
_REAL_GITS = ("/Library/Developer/CommandLineTools/usr/bin/git", "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
              "/opt/homebrew/bin/git", "/usr/local/bin/git")


def real_git() -> str:
    """A git that is not the xcrun shim (first existing of the usual homes); bare "git" if none."""
    return next((g for g in _REAL_GITS if os.access(g, os.X_OK)), "git")


def _path_with_git(path: str) -> str:
    g = real_git()
    return path if g == "git" else os.path.dirname(g) + (":" + path if path else ":/usr/bin:/bin")


_CD_EXEC = 'cd "$1" && shift && exec "$@"'


class JailMissing(RuntimeError):
    """The configured user does not exist or sudo to it is not set up. Never fall back."""


@dataclass(frozen=True)
class Jail:
    user: str
    workroot: str = ""                 # shared dir (made by the owner, readable+writable by both) for trees and scratch
    deny_read: tuple = ()              # paths the user must NOT be able to read (the probe checks each)
    sudo: str = "sudo"
    owner_home: str = ""               # what `~` means in deny_read/floor when the probe runs AS the jail user (else its own home)
    floor: tuple | None = None         # paths always probed; None = the owner's home and libraries (tests with a same-uid stand-in pass ())
    _checked: list = field(default_factory=list, compare=False, repr=False, hash=False)

    def is_self(self) -> bool:
        """The process already runs as the jail user (a worker's own `check`): run directly, no sudo (review 3 B5)."""
        r = subprocess.run(["id", "-u", self.user], capture_output=True, text=True) if self.user else None
        return bool(r and r.returncode == 0 and int(r.stdout) == os.getuid())

    def require(self) -> None:
        """Refuse unless the user exists and we are that user or `sudo -n -u user` works."""
        if not self.user:
            raise JailMissing("no jail user configured")
        r = subprocess.run(["id", "-u", self.user], capture_output=True, text=True)
        if r.returncode:
            raise JailMissing(f"jail user {self.user!r} does not exist: the owner creates it (scripts/harness_setup_owner.sh)")
        if int(r.stdout) == os.getuid():
            return  # already the jail user: nothing to sudo
        t = subprocess.run([self.sudo, "-n", "-u", self.user, "-H", "true"], capture_output=True, text=True)
        if t.returncode:
            raise JailMissing(f"cannot sudo to {self.user!r} without a password (sudoers line missing?): {t.stderr.strip()[:200]}")
        if self.workroot and not os.access(self.workroot, os.W_OK | os.X_OK):
            raise JailMissing(f"workroot {self.workroot!r} is missing or not writable by the engine's user")

    def argv(self, argv: list[str], cwd=None, env: dict | None = None) -> list[str]:
        """`argv` as the jailed user: clean environment (only `env`), HOME the user's own, optional cwd."""
        env = {**(env or {}), "PATH": _path_with_git((env or {}).get("PATH", ""))}  # a real git first, never the xcrun shim
        e = [f"{k}={v}" for k, v in env.items() if k != "HOME"]
        home = env.get("HOME", "")
        if not (self.workroot and home.startswith(self.workroot.rstrip("/") + "/")):
            home = ""  # only a scratch dir inside the workroot may be HOME; anything else is the user's own
        inner = ["/bin/sh", "-c", _CD_EXEC, "sh", str(cwd) if cwd is not None else "/", *argv]  # never inherit the owner's cwd: the jail user cannot read it
        if self.is_self():
            return ["/usr/bin/env", "-i", f"HOME={home or os.environ.get('HOME', '')}", *e, *inner]
        # sudo -H sets the user's own HOME; env -i then drops everything else the caller had
        return [self.sudo, "-n", "-u", self.user, "-H", "/bin/sh", "-c", 'h=$1; shift; exec /usr/bin/env -i HOME="${h:-$HOME}" "$@"', "sh", home, *e, *inner]

    def mkdtemp(self, prefix: str) -> str:
        """A scratch dir the jailed user can write: under the workroot, mode 0777 (public data only lives here)."""
        d = tempfile.mkdtemp(prefix=prefix, dir=self.workroot or None)
        os.chmod(d, 0o777)
        return d

    def probe(self) -> list[str]:
        """The once-per-setup proof (M7): as the jailed user, every `deny_read` path is unreadable and `gh` has no login.
        Returns the failures (empty = the wall holds)."""
        bad = []
        # floor (review 3 B1): the owner's home and the real libraries are always probed, whatever the rules file lists
        home = self.owner_home or str(Path.home())
        floor = self.floor if self.floor is not None else (home,)
        for p in dict.fromkeys((*floor, *self.deny_read)):
            p = home + p[1:] if p.startswith("~") else p
            r = subprocess.run(self.argv(["/bin/sh", "-c", f"test -r {shlex.quote(p)}"], env={}),
                               capture_output=True)
            if r.returncode == 0:
                bad.append(f"{p} is readable by {self.user}")
        gh = subprocess.run(self.argv(["/bin/sh", "-c", "command -v gh >/dev/null && gh auth status"], env={"PATH": os.environ.get("PATH", "")}),
                            capture_output=True)
        if gh.returncode == 0:
            bad.append(f"{self.user} is signed in to gh")
        return bad


_KNOWN = {"user", "workroot", "deny_read", "sudo", "owner_home", "code_map"}


def load(root) -> Jail | None:
    """`[jail]` of `<root>/harness.toml`; none configured = None (callers decide whether that is allowed)."""
    import tomllib
    f = Path(root) / "harness.toml"
    c = tomllib.loads(f.read_text()).get("jail") if f.is_file() else None
    if not c:
        return None
    if unknown := sorted(set(c) - _KNOWN):  # fail closed: a misspelt key is not silently ignored
        raise ValueError(f"harness.toml [jail]: unknown keys {unknown}")
    return Jail(user=c.get("user", ""), workroot=c.get("workroot", ""), deny_read=tuple(c.get("deny_read", ())),
                sudo=c.get("sudo", "sudo"), owner_home=c.get("owner_home", ""))
