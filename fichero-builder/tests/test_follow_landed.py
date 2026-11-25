"""local.loop.follows-landed-code: 2026-11-25 16:41-18:05 every check refused "harness.toml [check]: unknown keys ['swift_tests']"
(alerts 1902-1909): a landing added the key, the loop re-pinned the new rules, and its own checkout still ran the older code."""
from __future__ import annotations

import subprocess

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
