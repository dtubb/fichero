"""dev-workflows jail: workers and the ladder as a second macOS user; a missing user refuses (review 2 B3)."""

from __future__ import annotations

import os
import subprocess

import pytest

from fichero_server.workflows import jail as J


def _fake_sudo(tmp_path):
    """A `sudo` that drops -n/-u USER/-H and runs the rest as the current user, recording the user asked for."""
    s = tmp_path / "sudo"
    s.write_text('#!/bin/sh\necho "$3" >> "%s/asked"\nshift 4\nexec "$@"\n' % tmp_path)
    s.chmod(0o755)
    return str(s)


def test_a_missing_user_refuses_never_falls_back(tmp_path):
    with pytest.raises(J.JailMissing, match="does not exist"):
        J.Jail(user="no-such-user-xyz", sudo=_fake_sudo(tmp_path)).require()
    with pytest.raises(J.JailMissing, match="no jail"):
        J.Jail(user="").require()


def test_the_current_user_is_no_jail(tmp_path):
    me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    with pytest.raises(J.JailMissing, match="current user"):
        J.Jail(user=me, sudo=_fake_sudo(tmp_path)).require()


def test_sudo_failure_refuses(tmp_path):
    s = tmp_path / "sudo"
    s.write_text("#!/bin/sh\necho 'a password is required' >&2\nexit 1\n")
    s.chmod(0o755)
    with pytest.raises(J.JailMissing, match="sudoers"):
        J.Jail(user="root", sudo=str(s)).require()  # root exists and is not us (unless we are root)


def test_argv_runs_as_the_user_with_a_clean_env_and_cwd(tmp_path):
    j = J.Jail(user="root", sudo=_fake_sudo(tmp_path))
    out = subprocess.run(j.argv(["/bin/sh", "-c", 'echo "$A:$HOME:$(pwd)"'], cwd=tmp_path, env={"A": "1", "HOME": "/owner"}),
                         capture_output=True, text=True, env={"SECRET": "x"})
    assert (tmp_path / "asked").read_text().strip() == "root"
    a, home, cwd = out.stdout.strip().split(":")
    assert a == "1" and home != "/owner" and os.path.samefile(cwd, tmp_path)


def test_probe_flags_a_readable_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # the fake sudo runs as us; keep our own gh login out of it
    secret = tmp_path / "hosts.yml"
    secret.write_text("token")
    j = J.Jail(user="root", sudo=_fake_sudo(tmp_path), deny_read=(str(secret), str(tmp_path / "absent")))
    assert j.probe() == [f"{secret} is readable by root"]


def test_load_reads_the_jail_table(tmp_path):
    (tmp_path / "harness.toml").write_text('[jail]\nuser = "fbuild"\nworkroot = "/Users/Shared/fj"\ndeny_read = ["~/.ssh"]\n')
    j = J.load(tmp_path)
    assert (j.user, j.workroot, j.deny_read) == ("fbuild", "/Users/Shared/fj", ("~/.ssh",))
    assert J.load(tmp_path / "none") is None


def test_mkdtemp_is_world_writable_under_the_workroot(tmp_path):
    d = J.Jail(user="x", workroot=str(tmp_path)).mkdtemp("t-")
    assert d.startswith(str(tmp_path)) and os.stat(d).st_mode & 0o777 == 0o777


def test_probe_flags_a_gh_login(tmp_path, monkeypatch):
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text("#!/bin/sh\nexit 0\n")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{gh.parent}:/usr/bin:/bin")
    assert J.Jail(user="root", sudo=_fake_sudo(tmp_path)).probe() == ["root is signed in to gh"]
