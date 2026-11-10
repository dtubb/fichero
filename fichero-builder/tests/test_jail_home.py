"""dev-workflows.run.jail-home (2026-11-03): a jailed test run gets a scratch HOME inside the workroot, never the jail user's real one,
so the real-state guard (#5530) cannot trip on `~/Library/Application Support/Fichero` when the check falls back to a local run."""
from __future__ import annotations

from pathlib import Path

from fichero_builder import check_tool
from fichero_builder.check_tool import Config
from fichero_builder.jail import Jail


def test_only_a_scratch_dir_in_the_workroot_becomes_the_jailed_home(tmp_path):
    j = Jail(user="nobody-here", workroot=str(tmp_path / "wr"), sudo="sudo")
    inside, outside = str(tmp_path / "wr" / "check-home-x"), str(tmp_path / "elsewhere")
    a = j.argv(["true"], env={"HOME": inside})
    b = j.argv(["true"], env={"HOME": outside})
    assert a[a.index("sh") + 1] == inside, "the scratch HOME is passed to the jailed shell"
    assert b[b.index("sh") + 1] == "", "a HOME outside the workroot is dropped: the user's own is used"


def test_the_rungs_home_is_made_in_the_jails_workroot(tmp_path, monkeypatch):
    j = Jail(user="u", workroot=str(tmp_path))
    monkeypatch.setattr(check_tool, "_JAIL", j)
    home = check_tool._env(tmp_path, Config())["HOME"]
    assert home.startswith(str(tmp_path.resolve())) or home.startswith(str(tmp_path)), home


def test_harness_start_keeps_the_worker_users_own_home():
    """#6466: the loop starts the worker with `sudo -H`, so HOME is the worker's own home: the token file, ~/.claude.json and the
    session files `builder run` watches are all there. A start script that moved HOME to the workroot put the session files where
    `builder run` never looks (2026-11-07: sessions under the workroot's .claude), so it never saw a DONE."""
    text = (Path(__file__).resolve().parents[2] / "scripts" / "harness_start.py").read_text()
    assert "use_worker_home" not in text and 'environ["HOME"]' not in text
    assert "find_claude(Path.home(), jail.workroot)" in text, "claude is looked for on PATH, then in the worker's own ~/.local/bin, then the workroot's"
