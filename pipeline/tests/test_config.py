"""pipeline.project-profile: one TOML per project; the runner's code names nothing project-specific."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline import ROOT, config


def test_runner_code_names_no_project_specifics():
    project = (config.PROJECTS / "current").read_text().strip()
    for p in (ROOT / "pipeline").glob("*.py"):
        if p.name == "__main__.py":
            continue  # the self-test's own grep names the project it greps for
        code = "".join(re.sub(r"#.*", "", line) for line in p.read_text().splitlines(True))
        assert project not in code.lower(), f"{p.name} names the project; move it to pipeline/projects/{project}.toml"


def test_example_writing_profile_loads_and_validates():
    cfg = config.load("example-writing")
    assert [r["name"] for r in cfg["ladder"]] == ["word-count", "citations", "proofread"]
    assert cfg["roles"]["coder"][0]["kind"] == "pi" and cfg["workers"]["caps"]["coders"] == 1


def test_current_profile_loads_with_every_required_section():
    cfg = config.load()
    for section, keys in config.REQUIRED.items():
        for k in keys:
            assert k in cfg[section], f"[{section}] {k}"
    assert any(r.get("kind") == "red-on-base" for r in cfg["ladder"])
    coders = cfg["roles"]["coder"]
    assert config.pi_model_id(coders[0]) == "anthropic/claude-sonnet-5-5", "the Anthropic API through Pi first (ruled 2026-10-25)"
    assert coders[1]["provider"] == "openrouter" and coders[1]["enabled"] is False, "Qwen stays configured but off"
    assert config.pi_model_id(cfg["roles"]["reviewer"][0]) == "anthropic/claude-sonnet-5-5", "owner: every worker is Sonnet or Haiku"
    assert config.pi_model_id(config.at_tier(cfg, coders[0], "small")) == "anthropic/claude-haiku-5-5", "the small tier"
    assert all(w.get("tier") for role in cfg["roles"].values() for w in role), "roles name a tier, not a model"
    assert all(w["kind"] == "pi" for role in cfg["roles"].values() for w in role), "no other worker kind on this branch"
    assert cfg["workers"]["cost_cap_usd"] == 5.0 and cfg["workers"]["daily_cap_usd"] == 8.0, "US$5 per session, US$8 per day (studio trial)"
    import json
    declared = {m["id"] for m in json.load(open(config.ROOT / "pipeline/pi-agent/models.json"))["providers"]["anthropic"]["models"]}
    assert {"claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"} <= declared, "Pi knows the models' context and price"


def test_missing_section_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "bad.toml").write_text("[repo]\nbase = 'x'\n")
    monkeypatch.setattr(config, "PROJECTS", tmp_path)
    with pytest.raises(ValueError, match=r"\[repo\] lacks worktrees"):
        config.load("bad")


def test_studio_trial_shares_nothing_with_the_live_runner():
    """The studio branch's runner has its own tmux session, branch names, state folder, Pi and agent dir, and lands nothing."""
    from pipeline import STATE
    cfg = config.load()
    assert cfg["workers"]["tmux_session"] == "studio" and cfg["repo"]["branch_prefix"] == "studio"
    assert cfg["run"]["auto_land"] is False and cfg["run"]["feed"] is False, "nothing lands, nothing is picked from GitHub"
    assert STATE.name == ROOT.name != "integration", "the journal lives under this checkout's own name"
    assert cfg["workers"]["agent_dir"] == "pipeline/pi-agent", "a copy inside this worktree"
    for k in ("pi_bin", "pi_adapter"):
        assert not Path(cfg["workers"][k]).is_absolute() and (ROOT / cfg["workers"][k]).exists(), f"{k} is Pi installed inside the worktree"


def test_stage_one_can_run_through_openrouter_pinned_to_the_anthropic_endpoint():
    import json
    cat = json.load(open(config.ROOT / "pipeline/pi-agent/models.json"))["providers"]["openrouter"]["models"]
    by = {m["id"]: m for m in cat}
    for mid in ("anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5", "qwen/qwen3-coder-next", "qwen/qwen3.8-27b"):
        r = by[mid]["compat"]["openRouterRouting"]
        assert r["allow_fallbacks"] is False and (r.get("only") or r.get("order")), f"{mid} is pinned to named endpoints"
    cfg = config.load()
    rv = cfg["roles"]["reviewer"][1]
    assert config.pi_model_id(rv) == "openrouter/anthropic/claude-sonnet-5.5" and rv["model"] in by
