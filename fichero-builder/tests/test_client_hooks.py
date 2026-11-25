"""builder.client.*: the harness.toml hooks a second client sets. Each has a test that the default is today's literal and one that
a set value is used."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from fichero_builder import check_tool, client, console, measure, policy_hook, profiles, work

ROOT = Path(__file__).resolve().parents[2]


def rules(tmp_path, text: str) -> Path:
    (tmp_path / "harness.toml").write_text(text)
    return tmp_path


def test_no_file_gives_every_default(tmp_path):
    assert client.land_repo(tmp_path) == "dtubb/fichero"
    assert client.land_branch(tmp_path) == "integration"
    assert client.release_branch(tmp_path) == "main"
    assert client.product(tmp_path) == "Fichero Builder"
    assert client.harness_name(tmp_path) == "fichero"
    assert client.state_env(tmp_path) == "FICHERO_BUILDER_STATE"
    assert client.label_prefix(tmp_path) == "local.builder"
    assert client.package_dir(tmp_path) == "fichero-builder/fichero_builder"
    assert client.scripts_dir(tmp_path) == ROOT / "scripts"


def test_set_values_are_used(tmp_path):
    rules(tmp_path, '[land]\nrepo = "me/words"\nbranch = "draft"\nrelease_branch = ""\n[policy]\nproduct = "Words"\n'
                    '[harness]\nname = "words"\nlabel_prefix = "local.words"\nscripts_dir = "/opt/h"\npackage_dir = "pkg/fb"\n')
    assert client.land_repo(tmp_path) == "me/words"
    assert client.land_branch(tmp_path) == "draft"
    assert client.release_branch(tmp_path) == ""
    assert client.product(tmp_path) == "Words"
    assert client.state_env(tmp_path) == "WORDS_BUILDER_STATE"
    assert client.label_prefix(tmp_path) == "local.words"
    assert client.scripts_dir(tmp_path) == Path("/opt/h")
    assert client.package_dir(tmp_path) == "pkg/fb"


def test_issue_reconcile_repo(tmp_path):
    from fichero_builder import issue_reconcile as ir
    assert ir.REPO == "dtubb/fichero" and ir.DEFAULT_REF == "origin/integration"
    old = ir.REPO, ir.DEFAULT_REF
    try:
        ir.configure(rules(tmp_path, '[land]\nrepo = "me/words"\nbranch = "draft"\n'))
        assert (ir.REPO, ir.DEFAULT_REF) == ("me/words", "origin/draft")
    finally:
        ir.REPO, ir.DEFAULT_REF = old


def test_spec_pipeline_repo(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("spec_pipeline_t", ROOT / "scripts" / "spec_pipeline.py")
    sp = importlib.util.module_from_spec(spec)
    sys.modules["spec_pipeline_t"] = sp
    spec.loader.exec_module(sp)
    assert sp.GH_REPO == "dtubb/fichero"
    assert sp.repo_of(tmp_path) == "dtubb/fichero"
    assert sp.repo_of(rules(tmp_path, '[land]\nrepo = "me/words"\n')) == "me/words"


def _record(monkeypatch):
    calls = []
    monkeypatch.setattr(console, "_git_text", lambda repo, *a: calls.append(a) or "")
    return calls


def test_git_reads_default_release_branch_is_main(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    console.git_reads(tmp_path, [], "integration")
    assert ("fetch", "-q", "origin", "integration", "main") in calls
    assert ("rev-list", "origin/main..origin/integration") in calls


def test_git_reads_set_release_branch_and_empty_disables(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    console.git_reads(rules(tmp_path, '[land]\nrelease_branch = "stable"\n'), [], "integration")
    assert ("rev-list", "origin/stable..origin/integration") in calls
    calls.clear()
    console.git_reads(rules(tmp_path, '[land]\nrelease_branch = ""\n'), [], "integration")
    assert ("fetch", "-q", "origin", "integration") in calls
    assert not any(a[0] == "rev-list" and "origin/main" in " ".join(a) for a in calls)


def test_release_view_uses_release_branch(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    console.release(tmp_path, "integration", pr=[], rows=[], issue=lambda n: {})
    assert ("log", "--format=%h %s", "origin/main..origin/integration") in calls
    calls.clear()
    out = console.release(rules(tmp_path, '[land]\nrelease_branch = ""\n'), "integration", pr=[], rows=[], issue=lambda n: {})
    assert out["ahead"] == 0 and not any("origin/main" in " ".join(a) for a in calls)


def test_trailer_product_default_and_set(tmp_path):
    msg = "s\n\nWritten-By: M using H using Fichero Builder\n"
    assert policy_hook.commit_msg_problems(msg, {}) == []
    assert policy_hook.commit_msg_problems(msg, {"product": "Words"})  # refused: the shape names another product
    assert policy_hook.commit_msg_problems("s\n\nWritten-By: M using H using Words\n", {"product": "Words"}) == []
    assert profiles.trailer("m", "h", tmp_path) == "Written-By: m using h using Fichero Builder"
    assert profiles.trailer("m", "h", rules(tmp_path, '[policy]\nproduct = "Words"\n')) == "Written-By: m using h using Words"


def test_a_harness_toml_in_the_start_directory_is_never_read(tmp_path):
    """A jailed worker owns its start directory: its harness.toml must not pick the scripts or the state."""
    code = "from fichero_builder import work, start_tool, run, journal; print(work.SCRIPTS); print(start_tool._HOOK); print(run.START); print(journal.STATE)"
    (tmp_path / "w").mkdir()
    rules(tmp_path / "w", '[harness]\nscripts_dir = "/opt/h"\nname = "words"\n')
    env = {"PYTHONPATH": str(ROOT / "fichero-builder"), "PATH": "/usr/bin:/bin", "XDG_STATE_HOME": str(tmp_path / "x"), "FICHERO_BUILDER_STATE": str(tmp_path / "s")}
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path / "w", capture_output=True, text=True, env=env).stdout.split("\n")
    assert out[:4] == [str(ROOT / "scripts"), str(ROOT / "scripts" / "harness_policy_hook.py"), str(ROOT / "scripts" / "harness_start.py"), str(tmp_path / "s")]
    assert client.scripts_dir() == ROOT / "scripts" and client.state_env() == "FICHERO_BUILDER_STATE"


def test_script_comes_from_the_named_root_only(tmp_path):
    default = Path("/d/harness_start.py")
    assert client.script(tmp_path, "harness_start.py", default) == default
    rules(tmp_path, '[harness]\nscripts_dir = "scripts-x"\n')
    assert client.script(tmp_path, "harness_start.py", default) == tmp_path / "scripts-x" / "harness_start.py"  # relative to the rules file's root
    rules(tmp_path, '[harness]\nscripts_dir = "/opt/h"\n')
    assert client.script(tmp_path, "harness_start.py", default) == Path("/opt/h/harness_start.py")


def test_check_config_accepts_the_new_keys(tmp_path):
    assert check_tool.load(tmp_path).rungs == () and check_tool.load(tmp_path).rung == ()
    cfg = check_tool.load(rules(tmp_path, '[land]\nrepo = "a/b"\nrelease_branch = ""\n[harness]\nname = "w"\n[check]\nrungs = ["guards"]\n'
                                          '[[check.rung]]\nname = "prose"\nargv = ["true"]\n'))
    assert cfg.rungs == ("guards",) and cfg.rung[0]["name"] == "prose"
    with pytest.raises(ValueError):
        check_tool.load(rules(tmp_path, '[check]\nrungz = []\n'))


def test_land_keys_are_known_to_the_rules_check(tmp_path):
    rules(tmp_path, '[land]\nrepo = "a/b"\nrelease_branch = ""\nbranch = "x"\nboundary = ["y"]\n')
    assert not [p for p in check_tool.rules_problems(tmp_path) if "unknown keys" in p]


def _fakes(log):
    return [(n, (lambda n=n: (log.append(n), {"ok": True})[1])) for n in check_tool.RUNGS]


def test_pick_rungs_default_is_every_rung_in_order(tmp_path):
    log = []
    picked = check_tool.pick_rungs(_fakes(log), check_tool.load(tmp_path), tmp_path)
    assert [n for n, _ in picked] == list(check_tool.RUNGS)


def test_pick_rungs_selects_reorders_and_adds_a_custom_argv(tmp_path):
    log = []
    cfg = check_tool.load(rules(tmp_path, '[check]\nrungs = ["guards", "prose", "ready"]\n[[check.rung]]\nname = "prose"\nargv = ["true"]\n'))
    picked = check_tool.pick_rungs(_fakes(log), cfg, tmp_path)
    assert [n for n, _ in picked] == ["guards", "prose", "ready"]
    assert picked[1][1]()["ok"] is True
    assert picked[2][1]()["ok"] and log == ["ready"]


def test_pick_rungs_refuses_an_unknown_name(tmp_path):
    cfg = check_tool.load(rules(tmp_path, '[check]\nrungs = ["nope"]\n'))
    with pytest.raises(ValueError, match="nope"):
        check_tool.pick_rungs(_fakes([]), cfg, tmp_path)


def test_measure_python_default_and_set(tmp_path):
    assert measure.default_python(tmp_path) == "/Users/Shared/fichero-worker/venv/bin/python"
    assert measure.default_python(rules(tmp_path, '[check]\npython = "/opt/py"\n')) == "/opt/py"


def test_pinned_package_path(tmp_path):
    pinned = tmp_path / "p"
    (pinned / "fichero-builder" / "fichero_builder").mkdir(parents=True)
    assert work.pinned_package(pinned) == pinned / "fichero-builder"
    (pinned / "pkg" / "fb").mkdir(parents=True)
    rules(pinned, '[harness]\npackage_dir = "pkg/fb"\n')
    assert work.pinned_package(pinned) == pinned / "pkg"
    assert work.pinned_package(tmp_path / "none") == Path(work.__file__).resolve().parents[1]


def test_ensure_pinned_missing_table_is_a_clear_refusal(tmp_path):
    for text in ("", '[check]\nengine_repo = "/r"\n', '[land]\npinned_dir = "/p"\n'):
        rules(tmp_path, text)
        with pytest.raises(ValueError, match=r"harness\.toml"):
            work.ensure_pinned(str(tmp_path), "(base abc1234)", "abc1234")


def test_label_prefix_names_the_plists(tmp_path):
    from fichero_builder import queue
    assert queue.agent_label("loop", tmp_path) == "local.builder.loop"
    assert queue.agent_label("loop", rules(tmp_path, '[harness]\nlabel_prefix = "local.words"\n')) == "local.words.loop"
