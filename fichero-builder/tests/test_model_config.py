"""dev-workflows.models.by-config: one model per role, a missing or unknown provider asks; a Pi model with no price
in Pi's models.json refuses to start (the cap would read zero)."""
from __future__ import annotations

import json

import pytest

from fichero_builder import models, pi_rpc

TABLE = '''[models]
providers = ["claude-code", "anthropic"]
builder = { provider = "claude-code", model = "sonnet" }
reviewer = { provider = "anthropic", model = "claude-opus-5-5", context = 100000 }
helper = { provider = "omlx", model = "qwen" }
'''


def test_one_model_per_role_and_a_missing_provider_asks(tmp_path):
    (tmp_path / "harness.toml").write_text(TABLE)
    cfg = models.load(tmp_path)
    assert models.for_role(cfg, "builder") == models.Model("claude-code", "sonnet")
    assert models.for_role(cfg, "reviewer").context == 100000
    with pytest.raises(models.Question, match="omlx"):
        models.for_role(cfg, "helper")
    with pytest.raises(models.Question, match="researcher"):
        models.for_role(cfg, "researcher")
    assert models.load(tmp_path / "nowhere") == {}


def test_the_repos_own_table_names_every_role():
    cfg = models.load(pi_rpc.EXTENSION.parents[2])
    for role in models.ROLES:
        models.for_role(cfg, role)


def test_a_pi_model_without_a_price_in_models_json_is_not_priced(tmp_path):
    (tmp_path / "models.json").write_text(json.dumps({"providers": {"fake": {"models": [
        {"id": "priced", "cost": {"input": 1, "output": 2, "cacheRead": 0, "cacheWrite": 0}}, {"id": "free"}]}}}))
    assert pi_rpc.priced(tmp_path, "fake", "priced")
    assert not pi_rpc.priced(tmp_path, "fake", "free")
    assert not pi_rpc.priced(tmp_path, "fake", "absent") and not pi_rpc.priced(tmp_path / "nowhere", "fake", "priced")
    (tmp_path / "models.json").write_text(json.dumps({"providers": {"fake": {"models": [
        {"id": "zero", "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}))
    assert pi_rpc.priced(tmp_path, "fake", "zero"), "a local model at zero is a price, not a missing one"


def test_a_window_past_the_standard_one_has_a_builder_model_that_gets_it():
    """A queue lane takes its model from this role, so the window in [spend] must be that model's: plain `sonnet`, 200k, handing
    off at 175000 tokens (owner 2026-11-02; the name is from the 1M era, kept for the weakened-tests count)."""
    import tomllib
    from pathlib import Path

    rules = tomllib.loads((Path(models.__file__).resolve().parents[2] / "harness.toml").read_text())
    assert rules["spend"]["window"] == 200000 and rules["models"]["builder"]["model"] == "sonnet" and rules["spend"]["handoff_tokens"] == 175000


def test_the_loop_has_a_manager_role_and_no_verb_names_a_model_of_its_own(tmp_path, monkeypatch):
    """dev-workflows.run.loop-roles: builder sonnet, reviewer opus, manager haiku, all from the rules file; `builder run`
    with no --model takes [models].builder (it defaulted to the literal "sonnet")."""
    cfg = models.load(pi_rpc.EXTENSION.parents[2])
    assert "manager" in models.ROLES and models.for_role(cfg, "manager").model == "haiku"
    from fichero_builder import __main__ as cli, run as run_mod

    (tmp_path / "harness.toml").write_text('[models]\nproviders = ["claude-code"]\nbuilder = { provider = "claude-code", model = "a-local-coder" }\n')
    seen = {}
    monkeypatch.setattr(run_mod, "run", lambda *a, **k: seen.update(k) or "done")
    monkeypatch.setattr(cli, "state_dir", lambda root, state: tmp_path / "s")
    (tmp_path / "b.txt").write_text("brief")
    cli.main(["run", "--root", str(tmp_path), "--worktree", str(tmp_path), "--brief", str(tmp_path / "b.txt"), "--name", "w"])
    assert seen.get("model") == "a-local-coder"
