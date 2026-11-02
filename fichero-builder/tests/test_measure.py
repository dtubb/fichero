"""dev-workflows.run.measure: `builder measure` ships a lane commit's engine source and script (git archive) to a test machine,
runs it with that machine's venv under its own TMPDIR, journals the JSON line and tells the lane's pane; a full disk refuses."""
from __future__ import annotations

import os
import subprocess
import sys

from fichero_builder import journal, measure, queue


def _world(tmp_path, monkeypatch, min_free=1):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    b = tmp_path / "bin"
    b.mkdir()
    (b / "ssh").write_text('#!/bin/sh\nwhile [ "$1" = "-o" ]; do shift 2; done\nshift\nexec sh -c "$1"\n')
    (b / "ssh").chmod(0o755)
    told = tmp_path / "told"
    (b / "tell").write_text(f'#!/bin/sh\necho "$1 $2" >> {told}\n')
    (b / "tell").chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}:{os.environ['PATH']}")
    gate = tmp_path / "gate"
    (gate / "venv" / "bin").mkdir(parents=True)
    os.symlink(sys.executable, gate / "venv" / "bin" / "python")
    lane = tmp_path / "lane"
    (lane / "fichero-server" / "src" / "pkg").mkdir(parents=True)
    (lane / "fichero-server" / "src" / "pkg" / "__init__.py").write_text("VALUE = 42\n")
    (lane / "measure.py").write_text("import json, os, tempfile, pkg\nprint('noise')\nprint(json.dumps({'value': pkg.VALUE, 'tmp': tempfile.gettempdir()}))\n")

    def g(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=lane, check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "main"), g("add", "."), g("commit", "-qm", "a step")
    (tmp_path / "harness.toml").write_text(f'[machines]\nimac = {{ ssh = "imac", dir = "{gate}", min_free_gb = {min_free} }}\n[loop]\ntell = "{b / "tell"}"\n')
    queue.add("lane-x", str(lane), "batch-1", str(tmp_path / "harness.toml"), [], kind="external", pane="%537")
    return gate, g, told


def test_measure_ships_the_commit_runs_it_there_journals_the_json_and_tells_the_pane(tmp_path, monkeypatch):
    gate, g, told = _world(tmp_path, monkeypatch)
    rc, out = measure.run(tmp_path, "lane-x", "imac", ["measure.py", "--pages", "3"])
    assert rc == 0 and '"value": 42' in out, out
    sha = g("rev-parse", "HEAD")
    assert (gate / "wt" / sha[:12] / "fichero-server" / "src" / "pkg").is_dir() and str(gate / "tmp") in out
    assert list((gate / "tmp").iterdir()) == [], "its tmp is emptied after"
    (r,) = [x for x in journal.read() if x["event"] == "measure"]
    assert r["sha"] == sha and r["rc"] == 0 and r["json"].startswith("{") and r["args"] == ["measure.py", "--pages", "3"]
    assert told.read_text().startswith("%537 MEASURE imac")


def test_a_machine_short_of_disk_refuses_before_shipping(tmp_path, monkeypatch):
    gate, g, told = _world(tmp_path, monkeypatch, min_free=10 ** 6)
    rc, out = measure.run(tmp_path, "lane-x", "imac", ["measure.py"])
    assert rc == 1 and "not shipped" in out and not (gate / "wt").exists()
    assert measure.run(tmp_path, "lane-x", "nope", ["measure.py"])[0] == 1


def test_the_measure_verb_takes_the_script_after_dashes(tmp_path, monkeypatch):
    from fichero_builder import __main__ as cli
    gate, g, told = _world(tmp_path, monkeypatch)
    assert cli.main(["measure", "--lane", "lane-x", "--machine", "imac", "--root", str(tmp_path), "--state", str(tmp_path / "s"),
                     "--", "-c", "import json; print(json.dumps({'ok': 1}))"]) == 0
    assert [x["json"] for x in journal.read() if x["event"] == "measure"] == ['{"ok": 1}']


def test_install_copies_the_newest_dev_dmg_installs_and_reports_the_app_and_engine(tmp_path, monkeypatch):
    """Owner 2026-11-02: 'Install on…' a test machine. A fake ssh stores the copy and answers the install script."""
    from fichero_builder import __main__ as cli
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    b = tmp_path / "bin"
    b.mkdir()
    got = tmp_path / "remote.dmg"
    (b / "ssh").write_text('#!/bin/sh\nwhile [ "$1" = "-o" ]; do shift 2; done\nshift\n'
                           'case "$1" in df*) echo 50;; *"cat >"*) cat > ' + str(got) + ';; '
                           '*hdiutil*) echo "APP Fichero Dev.app"; echo "RUNNING 123 /Applications/Fichero Dev.app/Contents/MacOS/Fichero"; '
                           'echo "ENGINE 456 fichero_server";; esac\n')
    (b / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}:{os.environ['PATH']}")
    (tmp_path / "harness.toml").write_text('[machines]\nm4 = { ssh = "m4", dir = "~/fichero-gate" }\n')
    assert measure.install(tmp_path, "m4")[0] == 1, "nothing built yet"
    dmg = tmp_path / "Fichero-dev.dmg"
    dmg.write_bytes(b"DMG" * 1000)
    journal.append("build", tier="dev", ok=True, dmg=str(dmg))
    assert cli.main(["install", "m4", "--root", str(tmp_path), "--state", str(tmp_path / "s")]) == 0
    assert got.read_bytes() == dmg.read_bytes(), "the DMG went over ssh whole"
    r = [x for x in journal.read() if x["event"] == "install"][-1]
    assert r["rc"] == 0 and r["app_running"] and r["engine_running"] and "Fichero Dev.app" in r["detail"]
