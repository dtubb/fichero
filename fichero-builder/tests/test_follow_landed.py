"""local.loop.follows-landed-code: 2026-11-25 16:41-18:05 every check refused "harness.toml [check]: unknown keys ['swift_tests']"
(alerts 1902-1909): a landing added the key, the loop re-pinned the new rules, and its own checkout still ran the older code."""
from __future__ import annotations

import re
import subprocess
import tomllib
import types
from dataclasses import fields
from pathlib import Path

import pytest

from fichero_builder import check_tool, journal, queue

MSG_1642 = "rules file refused: harness.toml: harness.toml [check]: unknown keys ['swift_tests']"


def g(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    eng, live = tmp_path / "engine", tmp_path / "live"
    eng.mkdir()
    g(eng, "init", "-q", "-b", "integration")
    g(eng, "config", "user.email", "t@t"), g(eng, "config", "user.name", "t")
    rules = f'[check]\nengine_repo = "{eng}"\n[land]\nbranch = "integration"\n'
    (eng / "harness.toml").write_text(rules)
    (eng / "fichero-builder" / "fichero_builder").mkdir(parents=True)
    (eng / "fichero-builder" / "fichero_builder" / "x.py").write_text("old = 1\n")
    g(eng, "add", "."), g(eng, "commit", "-qm", "a")
    g(tmp_path, "clone", "-q", str(eng), str(live))
    g(live, "checkout", "-q", "--detach")
    (eng / "harness.toml").write_text(rules.replace("[land]", "future_key = 1\n[land]"))  # the landing adds a [check] key this code does not know
    (eng / "fichero-builder" / "fichero_builder" / "x.py").write_text("new = 2\n")
    g(eng, "commit", "-qam", "b: a new [check] key")
    return eng, live, rules


def _alerts():
    return [r for r in journal.read() if r["event"] == "alert"]


def test_with_follow_on_the_loop_checkout_goes_to_the_landed_tip_and_keeps_its_own_rules(repos):
    eng, live, rules = repos
    mine = rules + "[loop]\nfollow_landed = true\n"
    (live / "harness.toml").write_text(mine)  # the loop's own edits
    assert queue.follow_landed(live, out=lambda s: None).startswith("followed")
    assert g(live, "rev-parse", "HEAD") == g(eng, "rev-parse", "integration")
    assert (live / "fichero-builder" / "fichero_builder" / "x.py").read_text() == "new = 2\n", "the new code is on disk: the code-mark re-exec runs it"
    assert (live / "harness.toml").read_text() == mine
    assert [r["state"] for r in journal.read() if r["event"] == "loop"] == ["followed"] and not _alerts()
    assert queue.follow_landed(live, out=lambda s: None) == "", "once per tip"


def test_with_follow_off_rules_this_code_refuses_are_one_alert_naming_the_cause(repos):
    eng, live, _ = repos
    assert "unknown keys ['future_key']" in queue.follow_landed(live, out=lambda s: None)
    (a,) = _alerts()
    assert a["what"].startswith(f"the loop runs older code than the landed rules at {g(eng, 'rev-parse', 'integration')[:9]}")
    assert "follow_landed" in a["what"] and g(live, "rev-parse", "HEAD") != g(eng, "rev-parse", "integration"), "not updated"
    queue.follow_landed(live, out=lambda s: None)
    assert len(_alerts()) == 1, "one alert per tip"


def test_a_checkout_with_other_local_changes_is_not_updated_and_says_so(repos):
    eng, live, rules = repos
    (live / "harness.toml").write_text(rules + "[loop]\nfollow_landed = true\n")
    (live / "fichero-builder" / "fichero_builder" / "x.py").write_text("a person's edit\n")
    assert "local changes" in queue.follow_landed(live, out=lambda s: None)
    assert (live / "fichero-builder" / "fichero_builder" / "x.py").read_text() == "a person's edit\n"


def test_an_unknown_check_key_that_the_pinned_package_declares_names_older_code_as_the_cause(tmp_path):
    """The 16:42 refusal said only "unknown keys": the pinned copy's own package declared the key."""
    (tmp_path / "harness.toml").write_text('[check]\nfuture_key = ["xcodebuild"]\n')
    pkg = tmp_path / "fichero-builder" / "fichero_builder"
    pkg.mkdir(parents=True)
    (pkg / "check_tool.py").write_text("class Config:\n    future_key: tuple = ()\n")
    with pytest.raises(ValueError) as e:
        check_tool.load(tmp_path)
    assert str(e.value).startswith("harness.toml [check]: unknown keys ['future_key']: a NEWER builder knows them")
    (pkg / "check_tool.py").write_text("class Config:\n    other: int = 0\n")
    with pytest.raises(ValueError, match=r"unknown keys \['future_key'\]$"):
        check_tool.load(tmp_path)
    assert queue.RULES_NEWER.search(MSG_1642), "the re-exec onto the new code retries a step blocked by the 16:42 refusal"


MSG_2130 = "harness.toml [check].auto: unknown rules ['red-on-base-pure-move'] (known: [...])"


def test_after_a_follow_the_loop_re_execs_at_once_with_chains_running_and_only_a_dev_build_holds_it(repos):
    """2026-11-25 21:2x-21:39, alerts 1938-1948: the loop followed 7ab1780 and waited for a quiet tick that nine busy lanes never
    gave; every check meanwhile refused "[check].auto: unknown rules ['red-on-base-pure-move']". The chains' steps go again from
    queue.json, so after a follow only a dev build's thread holds the re-exec; and a step blocked on that refusal is retried."""
    eng, live, rules = repos
    (live / "harness.toml").write_text(rules + "[loop]\nfollow_landed = true\n")
    assert queue.follow_landed(live, out=lambda s: None).startswith("followed")
    mark = ("older code",)  # code_mark reads the running package: the followed checkout's code differs from it
    busy = types.SimpleNamespace(done=lambda: False)
    chains = {"pool": object(), **{f"lane{i}": busy for i in range(9)}}
    assert not queue.restart_due(mark, live, chains), "without a follow: a running chain still holds it, as before"
    assert queue.restart_due(mark, live, chains, followed=True), "after a follow: at once, nine chains running"
    assert not queue.restart_due(mark, live, chains, [types.SimpleNamespace(is_alive=lambda: True)], followed=True), "a dev build holds it"
    assert queue.RULES_NEWER.search(MSG_2130), "the re-exec retries the steps those refusals blocked"


def test_verify_after_a_landing_runs_in_a_clean_tree_of_the_land_tip_never_the_loops_checkout(repos):
    """2026-11-25 21:37, alert 1950: verify-all after a landing ran in the loop's own checkout (its local harness.toml) and four
    guards and a test went red there that are green on a clean tree of the landed 7ab1780."""
    eng, live, rules = repos
    (live / "harness.toml").write_text(rules + "local_only = 1\n")
    seen = {}

    def run(argv, **k):
        tree = argv[argv.index("--root") + 1]
        seen.update(tree=tree, rules=(Path(tree) / "harness.toml").read_text(), head=g(tree, "rev-parse", "HEAD"), status=g(tree, "status", "--porcelain"))
        return types.SimpleNamespace(returncode=0, stdout="VERIFIED\n", stderr="")
    assert queue.verify_landed(eng, "integration", live, run=run) == (0, "VERIFIED\n")
    assert seen["head"] == g(eng, "rev-parse", "integration") and seen["status"] == "", "the land branch's tip, clean"
    assert "local_only" not in seen["rules"] and "future_key" in seen["rules"], "the landed rules, never the loop's local copy"
    assert str(live) not in seen["tree"] and not Path(seen["tree"]).exists(), "its own tree, removed after"
    assert "verify-landed-" not in g(eng, "worktree", "list")
    rc, out = queue.verify_landed(eng, "no-such-branch", live, run=run)
    assert rc == 1 and out.startswith("NOT VERIFIED")


def test_the_committed_rules_file_loads_and_every_auto_rule_the_code_reads_is_registered():
    """2026-11-25 21:40-21:58: 7f54c6a read "red-on-base-pure-move" in cfg.auto and 7ab1780 listed it in harness.toml, but nothing
    registered it in AUTO_RULES, so the parser refused [check].auto and every check stopped (registered by hand in 30f9d63)."""
    root = Path(__file__).resolve().parents[2]
    c = tomllib.loads((root / "harness.toml").read_text()).get("check", {})
    assert not set(c.get("auto", ())) - set(check_tool.AUTO_RULES), "every [check].auto name is a registered rule"
    assert not set(c) - {f.name for f in fields(check_tool.Config)} - {"test_env"}, "every [check] key is a Config field"
    check_tool.load(root)  # and the parser itself accepts the committed file
    src = "\n".join(p.read_text() for p in (root / "fichero-builder" / "fichero_builder").glob("*.py"))
    read = set(re.findall(r'"([a-z0-9-]+)" (?:not )?in [a-z_.]*auto\b', src))
    assert read and not read - set(check_tool.AUTO_RULES), f"rules the code reads that the parser refuses: {sorted(read - set(check_tool.AUTO_RULES))}"
