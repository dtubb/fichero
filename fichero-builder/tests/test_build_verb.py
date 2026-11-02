"""dev-workflows.tool.build: `builder build --dev` wraps the project's own DMG script so nobody re-derives the procedure: the dev
tier, no version stamp, no notarizing, one journal row, the DMG's path and pass or fail printed. A fake script."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import build, journal


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    r = tmp_path / "root"
    (r / "scripts").mkdir(parents=True)
    (r / "fichero" / "Configs").mkdir(parents=True)
    (r / "fichero" / "Configs" / "Version.xcconfig").write_text("MARKETING_VERSION = 2026.11.1\n")
    (r / "harness.toml").write_text("[check]\n")
    script = r / "scripts" / "build-release-dmg.sh"
    script.write_text(f"""#!{sys.executable}
import json, os, sys
keep = ("FICHERO_RELEASE_TIER", "FICHERO_RELEASE_VERSION", "FICHERO_DMG_PATH", "PATH")
open(os.environ["FICHERO_DMG_PATH"] + ".seen", "w").write(json.dumps({{"argv": sys.argv[1:], "env": {{k: os.environ.get(k) for k in keep}}, "cwd": os.getcwd()}}))
print("building")
if os.path.exists("{r}/fail"):
    sys.exit(7)
if not os.path.exists("{r}/no-dmg"):
    open(os.environ["FICHERO_DMG_PATH"], "w").write("dmg")
""")
    script.chmod(0o755)
    (r / "build" / "releases").mkdir(parents=True)
    (r / ".gitignore").write_text("build/\nfail\nno-dmg\n")
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"]):
        subprocess.run(["git", "-C", str(r), *args], check=True)
    return r


def go(root, *extra):
    return cli.main(["build", *extra, "--root", str(root), "--state", str(root.parent / "s")])


def row():
    return [r for r in journal.read() if r["event"] == "build"]


def test_dev_runs_the_projects_script_for_the_dev_tier_without_a_stamp_or_notarizing_and_prints_the_dmg(root, capsys):
    assert go(root, "--dev") == 0
    dmg = root / "build" / "releases" / "Fichero-dev.dmg"
    seen = json.loads((dmg.parent / "Fichero-dev.dmg.seen").read_text())
    assert seen["argv"] == [], "no --notarize-app: a local test build never waits on Apple"
    assert seen["env"]["FICHERO_RELEASE_TIER"] == "dev" and seen["env"]["FICHERO_DMG_PATH"] == str(dmg)
    assert seen["env"]["FICHERO_RELEASE_VERSION"] == "2026.11.1", "the current version: the script's auto-stamp would edit the tree"
    assert seen["env"]["PATH"].split(os.pathsep)[0] == os.path.dirname(sys.executable), "the engine preflight's bare python3 finds the venv"
    assert f"PASSED {dmg}" in capsys.readouterr().out
    r = row()
    assert len(r) == 1 and r[0]["ok"] is True and r[0]["tier"] == "dev" and r[0]["dmg"] == str(dmg) and len(r[0]["sha"]) == 40 and r[0]["dirty"] is False


def test_a_red_script_fails_with_the_log_and_the_row_says_so(root, capsys):
    (root / "fail").write_text("")
    assert go(root, "--dev") == 1
    out = capsys.readouterr().out
    assert "FAILED" in out and "exit 7" in out and "building" in out, "the tail of the log"
    assert row()[0]["ok"] is False and row()[0]["rc"] == 7
    assert "building" in open(row()[0]["log"]).read()


def test_a_green_script_that_leaves_no_new_dmg_is_a_failure(root, capsys):
    (root / "no-dmg").write_text("")
    stale = root / "build" / "releases" / "Fichero-dev.dmg"
    stale.write_text("old")
    os.utime(stale, (1, 1))
    assert go(root, "--dev") == 1
    assert "no new DMG" in capsys.readouterr().out and row()[0]["ok"] is False


def test_without_dev_it_refuses_a_full_release_needs_the_owner(root, capsys):
    assert go(root) == 1
    assert "owner" in capsys.readouterr().out
    assert not (root / "build" / "releases" / "Fichero-dev.dmg").exists() and not row()


def test_the_jail_user_may_not_build(root, monkeypatch, capsys):
    """A build signs with the owner's identity and quits nothing of a worker's: workers never build."""
    monkeypatch.setattr(build, "_as_jail_user", lambda r: True)
    assert go(root, "--dev") == 1
    assert "worker" in capsys.readouterr().out and not row()


def test_a_missing_script_or_version_is_a_refusal_never_a_traceback(root, capsys):
    (root / "fichero" / "Configs" / "Version.xcconfig").write_text("OTHER = 1\n")
    assert go(root, "--dev") == 1
    assert "MARKETING_VERSION" in capsys.readouterr().out
    (root / "fichero" / "Configs" / "Version.xcconfig").write_text("MARKETING_VERSION = 1\n")
    (root / "scripts" / "build-release-dmg.sh").unlink()
    assert go(root, "--dev") == 1
    assert "build-release-dmg.sh" in capsys.readouterr().out
