"""pipeline.project-profile: one TOML per project; the runner's code names nothing project-specific."""
from __future__ import annotations

import re

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
    assert config.pi_model_id(cfg["roles"]["coder-small"][0]) == "anthropic/claude-haiku-5-5"
    assert all(w["kind"] == "pi" for role in cfg["roles"].values() for w in role), "no other worker kind on this branch"
    assert cfg["workers"]["cost_cap_usd"] == 5.0 and cfg["workers"]["daily_cap_usd"] == 25.0, "US$5 per session, US$25 per day"
    import json
    declared = {m["id"] for m in json.load(open(config.ROOT / "pipeline/pi-agent/models.json"))["providers"]["anthropic"]["models"]}
    assert {"claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"} <= declared, "Pi knows the models' context and price"


def test_missing_section_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "bad.toml").write_text("[repo]\nbase = 'x'\n")
    monkeypatch.setattr(config, "PROJECTS", tmp_path)
    with pytest.raises(ValueError, match=r"\[repo\] lacks worktrees"):
        config.load("bad")
