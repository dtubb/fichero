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
    assert config.pi_model_id(cfg["roles"]["coder"][0]) == "openrouter/qwen/qwen3.8-27b"


def test_missing_section_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "bad.toml").write_text("[repo]\nbase = 'x'\n")
    monkeypatch.setattr(config, "PROJECTS", tmp_path)
    with pytest.raises(ValueError, match=r"\[repo\] lacks worktrees"):
        config.load("bad")
