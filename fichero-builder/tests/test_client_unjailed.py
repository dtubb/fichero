"""builder.client.jail-optional, .empty-rungs, .land-boundary-default, .scripts-from-the-root, .brief-template: what a second
client (a prose repo, one lane, owner-run) needs to run at all. Fichero's own rules file keeps every one of today's refusals."""
import getpass
import subprocess
import tomllib
from pathlib import Path

import pytest

from fichero_builder import brief_tool, check_tool, client, jail, journal, land_tool, milestone, start_tool

ROOT = Path(__file__).resolve().parents[2]

CHECK = ('[check]\npython = "/usr/bin/python3"\nguard_glob = "scripts/check_*.py"\nmin_guards = 1\n'
         'ready = []\ncontract_guards = []\ncheck_paths = []\ncontract_paths = []\npytest_config = ""\n')
LAND = '[land]\nbranch = "draft"\n'


def rules(tmp_path, text: str) -> Path:
    (tmp_path / "harness.toml").write_text(text)
    return tmp_path


def unjailed(tmp_path, extra: str = "") -> Path:
    (tmp_path / "work").mkdir(exist_ok=True)
    return rules(tmp_path, f'[jail]\nenabled = false\nworkroot = "{tmp_path / "work"}"\n' + CHECK + LAND + extra)


# --- (a) the jail: off only when said so -----------------------------------------------------------------------------------

def test_an_absent_jail_still_refuses_everywhere(tmp_path):
    rules(tmp_path, CHECK + LAND)
    assert any("has no [jail]: nothing runs unjailed" in p for p in check_tool.rules_problems(tmp_path))
    assert any("has no [jail]" in p for p in start_tool.refusals(tmp_path, jail.load(tmp_path)))


def test_jail_enabled_false_runs_as_the_invoking_user_with_no_probe(tmp_path):
    root = unjailed(tmp_path)
    j = jail.load(root)
    assert j is not None and j.enabled is False and j.user == getpass.getuser()
    assert check_tool.rules_problems(root) == []
    assert j.is_self() and j.probe() == [] and j.require() is None
    assert start_tool.refusals(root, j) == []


def test_unjailed_still_needs_a_workroot_and_a_bad_enabled_value_refuses(tmp_path):
    rules(tmp_path, '[jail]\nenabled = false\n' + CHECK + LAND)
    assert any("[jail].workroot is not set" in p for p in check_tool.rules_problems(tmp_path))
    rules(tmp_path, '[jail]\nenabled = "no"\n' + CHECK + LAND)
    with pytest.raises(ValueError, match="enabled must be true or false"):
        jail.load(tmp_path)


def test_the_sudo_stand_in_runs_the_command_as_the_caller(tmp_path):
    j = jail.load(unjailed(tmp_path))
    r = subprocess.run([j.sudo, "-n", "-H", "-u", j.user, "sh", "-c", "id -un"], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == getpass.getuser()
    r = subprocess.run(j.argv(["/bin/sh", "-c", "echo ok"], cwd=tmp_path), capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok"


def test_every_unjailed_ladder_run_writes_one_row(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    root = unjailed(tmp_path)
    monkeypatch.setattr(check_tool, "_run_ladder", lambda *a, **k: {"ok": True, "rungs": []})
    monkeypatch.setattr(check_tool, "sweep_cancels", lambda: None)
    check_tool.run_ladder(root, "a" * 40, "b" * 40, root)
    rows = [r for r in journal.read() if r["event"] == "unjailed"]
    assert len(rows) == 1 and rows[0]["what"] == "check" and rows[0]["user"] == getpass.getuser()


def test_a_jailed_rules_file_writes_no_unjailed_row(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    jail.note_unjailed(jail.Jail(user="someone"), "check")
    jail.note_unjailed(None, "check")
    assert not [r for r in journal.read() if r["event"] == "unjailed"]


def test_unjailed_an_engine_repo_inside_a_home_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    root = unjailed(tmp_path, "")
    text = (root / "harness.toml").read_text().replace("[check]\n", f'[check]\nengine_repo = "{tmp_path / "repo"}"\n')
    (root / "harness.toml").write_text(text)
    assert check_tool.rules_problems(root) == [] and jail.load(root).probe() == []


def test_fichero_s_own_rules_file_keeps_its_jail():
    j = jail.load(ROOT)
    assert j is not None and j.enabled and j.user and j.deny_read


# --- (b) empty keys: declared empty is a NOT RUN row, left out still refuses -------------------------------------------------

@pytest.mark.parametrize("key", check_tool.EMPTY_OK)
def test_a_left_out_key_still_refuses(tmp_path, key):
    text = "\n".join(ln for ln in (unjailed(tmp_path) / "harness.toml").read_text().splitlines() if not ln.startswith(key + " "))
    rules(tmp_path, text + "\n")
    assert f"harness.toml [check].{key} is not declared" in check_tool.rules_problems(tmp_path)


def test_an_empty_ready_and_contract_are_not_run_rows_naming_why(tmp_path):
    cfg = check_tool.load(unjailed(tmp_path))
    r = check_tool.ready(tmp_path, cfg)
    assert r["ok"] and r["not_run"] and "[check].ready is empty" in r["stdout_tail"] and check_tool.rung_not_run(r)
    c = check_tool.contract_current(tmp_path, ["a.md"], cfg)
    assert c["not_run"] and "contract_guards is empty" in c["stdout_tail"]
    c2 = check_tool.contract_current(tmp_path, ["a.md"], check_tool.Config(contract_guards=("g.py",)))
    assert c2["not_run"] and "contract_paths is empty" in c2["stdout_tail"]


def test_empty_check_paths_add_one_not_run_row_and_set_ones_add_none(tmp_path):
    rows = check_tool.unpinned_rows(check_tool.load(unjailed(tmp_path)))
    assert len(rows) == 1 and rows[0]["name"] == "pinned-paths" and rows[0]["not_run"] and "check_paths is empty" in rows[0]["stdout_tail"]
    assert check_tool.unpinned_rows(check_tool.load(ROOT)) == []


def test_an_empty_pytest_config_runs_pytest_with_its_own_search(tmp_path):
    argv = check_tool.pytest_argv(tmp_path, ["t/test_x.py"], check_tool.Config(python="/usr/bin/python3"))
    with_config = check_tool.pytest_argv(tmp_path, ["t/test_x.py"], check_tool.Config(python="/usr/bin/python3", pytest_config="pytest.ini"))
    assert "pytest.ini" not in " ".join(argv) and "pytest.ini" in " ".join(with_config)


# --- (e) the land boundary -------------------------------------------------------------------------------------------------

def test_the_default_boundary_is_today_s_list():
    today = tomllib.loads((ROOT / "harness.toml").read_text())["land"]["boundary"]
    assert list(land_tool.DEFAULT_BOUNDARY) == today


def test_a_left_out_boundary_is_the_default_and_an_empty_one_refuses(tmp_path):
    root = unjailed(tmp_path)
    assert not [p for p in check_tool.rules_problems(root) if "boundary" in p]
    rules(tmp_path, (root / "harness.toml").read_text().replace(LAND, '[land]\nbranch = "draft"\nboundary = []\n'))
    assert any("[land].boundary is empty" in p for p in check_tool.rules_problems(tmp_path))


def test_the_gate_uses_the_default_boundary_when_none_is_set(tmp_path, monkeypatch):
    root = unjailed(tmp_path)
    seen = {}
    monkeypatch.setattr(land_tool, "resolve_branch", lambda repo, b: "base")
    monkeypatch.setattr(land_tool, "_git", lambda *a: "head")
    monkeypatch.setattr(land_tool, "unreviewed", lambda *a: [])
    monkeypatch.setattr(land_tool, "boundary", lambda repo, base, head, patterns: seen.setdefault("p", patterns) and [])
    ok, _ = land_tool.gate("repo", "head", root, "v", tmp_path / "log")
    assert ok and seen["p"] == list(land_tool.DEFAULT_BOUNDARY)


# --- (c) scripts from the client's root ------------------------------------------------------------------------------------

def test_the_build_order_guard_comes_from_the_client_root_when_it_has_one(tmp_path):
    assert milestone.guard_for(None) == milestone.GUARD
    rules(tmp_path, '[harness]\nscripts_dir = "tools"\n')
    assert milestone.guard_for(tmp_path) == milestone.GUARD  # the client's folder lacks it: the package's
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / milestone.GUARD.name).write_text("def _parse_build_order(t):\n    return {'stages': [{'steps': [{'number': '9.9'}]}]}\n")
    assert milestone.guard_for(tmp_path) == tmp_path / "tools" / milestone.GUARD.name
    (tmp_path / "s.md").write_text("x")
    assert milestone.build_order(tmp_path / "s.md", root=tmp_path) == [{"number": "9.9"}]


def test_start_scripts_come_from_the_client_root(tmp_path):
    rules(tmp_path, '[harness]\nscripts_dir = "tools"\n')
    assert client.script(tmp_path, "harness_policy_hook.py", start_tool._HOOK) == tmp_path / "tools" / "harness_policy_hook.py"
    assert start_tool._hook_cmd(tmp_path, "w", "s").split()[1] == str(tmp_path / "tools" / "harness_policy_hook.py")


# --- (f) the brief template ------------------------------------------------------------------------------------------------

ISSUE = {"number": 7, "title": "Chapter two", "body": "Tighten the opening.", "authorAssociation": "OWNER", "comments": []}


def test_the_default_brief_keeps_its_code_words(tmp_path):
    text = brief_tool.cluster([ISSUE], repo=str(tmp_path), branch="b", base="abc")
    assert "Test first, see it fail" in text and "Fixes #N" in text and "(base abc)" in text


def test_a_brief_template_replaces_the_code_words(tmp_path):
    (tmp_path / "brief.md").write_text("Edit the prose for {numbers} on {branch}. Print DONE <sha> when done.\n")
    rules(tmp_path, '[brief]\ntemplate = "brief.md"\n')
    assert check_tool.load(tmp_path) is not None  # a known [brief] key
    text = brief_tool.cluster_for(tmp_path)([ISSUE], repo=str(tmp_path), branch="b", base="abc")
    assert "Test first" not in text and "Fixes #N" not in text and "Edit the prose for #7 on b." in text and "(base abc)" in text
    assert "Tighten the opening." in text


def test_a_missing_template_file_refuses(tmp_path):
    rules(tmp_path, '[brief]\ntemplate = "nope.md"\n')
    with pytest.raises(ValueError, match="is not a file"):
        brief_tool.template_text(tmp_path)
