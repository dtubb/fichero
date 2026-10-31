"""The engine keeps, per task, the address of the current worker generation; a tell to a stale one is refused.

(dev-workflows.run.worker-address, #6116.) Rewritten at each handoff: the old generation's pane is no longer
the task's worker, so a message addressed to it must not reach the successor or the dead pane.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid

import pytest

from fichero_server.workflows import worker_process as wp

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None, reason="needs tmux")


@pytest.fixture
def tmux_session():
    name = f"wa_test_{uuid.uuid4().hex[:8]}"
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "200", "-y", "50"], check=True)
    yield name
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)


@pytest.fixture
def jail(tmp_path, monkeypatch):
    """A jail whose `sudo` is a stand-in that runs as us (same uid, so tmux and kill work); the user must still exist."""
    bin_ = tmp_path / "bin"  # only tmux: the dir tmux lives in may hold a gh the probe would rightly flag
    bin_.mkdir()
    if shutil.which("tmux"):
        (bin_ / "tmux").symlink_to(shutil.which("tmux"))
    monkeypatch.setenv("PATH", f"{bin_}:/usr/bin:/bin")
    sudo = tmp_path / "sudo"
    sudo.write_text('#!/bin/sh\nshift 4\nexec "$@"\n')
    sudo.chmod(0o755)
    from fichero_server.workflows.jail import Jail
    return Jail(user="root", sudo=str(sudo), workroot=str(tmp_path))


def _listener(tmp_path, name):
    got = tmp_path / f"{name}.txt"
    exe = tmp_path / f"claude-{name}"
    exe.write_text(f"#!/bin/sh\necho up-{name}\ncat > {got}\n")
    exe.chmod(0o755)
    return str(exe), got


def _until(pred, secs=15):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


def test_tell_reaches_only_the_current_generation(db, tmp_path, tmux_session, jail):
    exe1, got1 = _listener(tmp_path, "one")
    exe2, got2 = _listener(tmp_path, "two")
    j1 = wp.start(db, kind="claude", jail=jail, brief="x", workdir=tmp_path, timeout_s=60, tmux_session=tmux_session,
                  claude_bin=exe1, task="t1")
    assert wp.wait_for_line(j1, "up-one", 20)
    a1 = wp.address(db, "t1")
    assert a1["generation"] == 1 and a1["job_id"] == j1 and a1["pane"] and a1["kind"] == "claude"

    wp.tell(db, "t1", 1, "hello one")
    assert _until(lambda: got1.exists() and "hello one" in got1.read_text())

    # handoff: the successor is started for the same task; the address is rewritten
    j2 = wp.start(db, kind="claude", jail=jail, brief="x", workdir=tmp_path, timeout_s=60, tmux_session=tmux_session,
                  claude_bin=exe2, task="t1")
    assert wp.wait_for_line(j2, "up-two", 20)
    a2 = wp.address(db, "t1")
    assert a2["generation"] == 2 and a2["job_id"] == j2 and a2["pane"] != a1["pane"]

    with pytest.raises(wp.StaleWorker):
        wp.tell(db, "t1", 1, "late message")
    wp.tell(db, "t1", 2, "hello two")
    assert _until(lambda: got2.exists() and "hello two" in got2.read_text())
    assert "late message" not in got1.read_text() + got2.read_text()
    wp.stop(db, j1)
    wp.stop(db, j2)


def test_an_unknown_task_has_no_address_and_refuses_a_tell(db):
    assert wp.address(db, "nope") is None
    with pytest.raises(wp.StaleWorker):
        wp.tell(db, "nope", 1, "hi")
