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
    (bin_ / "claude").write_text(f"#!/bin/sh\ncat >/dev/null\necho 'looks fine'\necho '{reply}'\n")
    (bin_ / "claude").chmod(0o755)
    store = tmp_path / "verdicts.json"
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "r"), base, "HEAD", "--verdicts", str(store)],
                       env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}, capture_output=True, text=True)
    return r, store


def test_a_final_ready_line_writes_one_verdict_per_commit(tmp_path):
    r, store = _run(tmp_path, "READY")
    assert r.returncode == 0, r.stderr
    v = json.loads(store.read_text())
    assert len(v) == 1 and next(iter(v.values()))["verdict"] == "READY"


def test_anything_but_a_final_ready_writes_nothing(tmp_path):
    r, store = _run(tmp_path, "NOT READY: no test")
    assert r.returncode == 1 and not store.exists()
