"""pipeline.pipeline-as-data: the profile's steps validate before anything runs and route on exit code alone."""
from __future__ import annotations

import copy

import pytest

from pipeline import config, steps


def good():
    return copy.deepcopy(config.load("fichero")["steps"])


def test_the_profiles_pipeline_is_valid_and_routes_on_exit_code():
    st = good()
    assert steps.validate(st) == []
    assert steps.route(st, "checks", 0) == "review" and steps.route(st, "checks", 1) == "code"
    assert steps.route(st, "close", 0) == "end"
    assert steps.route(st, "brief", 7) == "brief", "a failure with no declared route stays at the step"


@pytest.mark.parametrize("edit, text", [
    (lambda s: s[2].update(on_fail="nowhere"), "not a step"),
    (lambda s: s[1].pop("max_iter"), "no max_iter"),
    (lambda s: s[2].pop("timeout_s"), "needs timeout_s"),
    (lambda s: s[3].update(**{"in": ["verdict"]}), "no earlier step writes"),
    (lambda s: s[0].update(kind="llm"), "kind must be"),
    (lambda s: s[2].update(on_ok="end", on_fail="end"), "unreachable"),
    (lambda s: s.append(dict(s[0])), "names repeat"),
])
def test_validate_refuses_a_broken_pipeline(edit, text):
    st = good()
    edit(st)
    assert any(text in e for e in steps.validate(st)), steps.validate(st)


def test_a_profile_with_a_broken_pipeline_refuses_to_load(tmp_path, monkeypatch):
    src = (config.PROJECTS / "example-writing.toml").read_text().replace('on_fail = "code"', 'on_fail = "nope"')
    monkeypatch.setattr(config, "PROJECTS", tmp_path)
    (tmp_path / "bad.toml").write_text(src)
    with pytest.raises(ValueError, match="steps: .*not a step"):
        config.load("bad")
