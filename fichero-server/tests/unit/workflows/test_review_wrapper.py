"""review wrapper: a verdict is written only for a final READY line, keyed per commit (#6116 Step 0.1 item 7)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "harness_review.py"


def _run(tmp_path, reply):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path / "r"), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    (tmp_path / "r").mkdir()
    g("init", "-q", "-b", "main")
    (tmp_path / "r" / "a.py").write_text("x = 1\n")
    g("add", "."), g("commit", "-q", "-m", "base")
    base = subprocess.run(["git", "-C", str(tmp_path / "r"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (tmp_path / "r" / "a.py").write_text("x = 2\n")
    g("commit", "-qam", "change")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "claude").write_text(f"#!/bin/sh\ncat >/dev/null\necho \"$PWD $*\" > {tmp_path}/seen\necho 'looks fine'\necho '{reply}'\n")
    (bin_ / "claude").chmod(0o755)
    g("branch", "landbr", base)
    pinned = tmp_path / "pinned"
    pinned.mkdir()
    (pinned / "harness.toml").write_text('[land]\nbranch = "landbr"\nboundary = ["zzz"]\n')
    d = tmp_path / "own"
    d.mkdir(mode=0o700)
    store = d / "verdicts.json"
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "r"), "HEAD", "--pinned", str(pinned), "--verdicts", str(store)],
                       env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}, capture_output=True, text=True)
    return r, store


def test_a_final_ready_line_writes_one_verdict_per_commit(tmp_path):
    r, store = _run(tmp_path, "READY")
    assert r.returncode == 0, r.stderr
    v = json.loads(store.read_text())
    assert len(v) == 1 and next(iter(v.values()))["verdict"] == "READY"  # one verdict for the whole range


def test_anything_but_a_final_ready_writes_nothing(tmp_path):
    r, store = _run(tmp_path, "NOT READY: no test")
    assert r.returncode == 1 and not store.exists()


def test_the_reviewer_is_restricted_without_mcp_and_runs_in_a_fresh_dir_under_home(tmp_path):  # review 4 B2
    r, _ = _run(tmp_path, "READY")
    cwd, _, flags = (tmp_path / "seen").read_text().partition(" ")
    for want in ("--restricted", "--strict-mcp-config", "--tools Read,Grep,Glob"):
        assert want in flags
    assert os.path.realpath(cwd).startswith(os.path.realpath(Path.home())) and "/r" not in cwd[-3:]
    assert str(tmp_path) not in cwd and not Path(cwd).exists()  # never the repo or workroot; removed after


def test_a_diff_over_the_cap_is_refused_not_truncated(tmp_path):  # review 4 B4
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path / "r"), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    (tmp_path / "r").mkdir()
    g("init", "-q", "-b", "main")
    (tmp_path / "r" / "a.py").write_text("x = 1\n")
    g("add", "."), g("commit", "-q", "-m", "base"), g("branch", "landbr")
    (tmp_path / "r" / "zz.txt").write_text("z" * 70000 + "\n")
    g("add", "."), g("commit", "-q", "-m", "big")
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "harness.toml").write_text('[land]\nbranch = "landbr"\n')
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "r"), "HEAD", "--pinned", str(tmp_path / "p"),
                        "--verdicts", str(tmp_path / "v.json"), "--print"], capture_output=True, text=True)
    assert r.returncode and "cap" in r.stderr
