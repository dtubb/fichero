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
    """A queue lane takes its model from this role. On plain `sonnet` a worker fills its real window long before an 85 % handoff of 1M."""
    import tomllib
    from pathlib import Path

    rules = tomllib.loads((Path(models.__file__).resolve().parents[2] / "harness.toml").read_text())
    assert rules["spend"]["window"] == 1000000 and "[1m]" in rules["models"]["builder"]["model"]
