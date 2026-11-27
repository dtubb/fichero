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
    off at 175000 tokens (owner 2026-11-02; the name is from the 1M era, kept for the weakened-tests count). The owner moved the
    role to `opus` on 2026-11-20 and back to plain `sonnet` on 2026-11-21 11:20: the test pins the owner's current `[models].builder`
    (a change of it is a change of this line), and a 1M variant fails it."""
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


def test_a_role_on_a_metered_provider_with_no_weekly_figure_is_a_question(tmp_path):
    """local.spend.metered-provider-needs-a-cap: the Qwen3-Coder-Next trial role (the spec's example) needs [spend.week_usd].openrouter."""
    from fichero_builder import watcher

    (tmp_path / "harness.toml").write_text('[models]\nproviders = ["claude-code", "openrouter"]\n'
                                           'qwen-trial = { provider = "openrouter", model = "qwen/qwen3-coder-next", context = 262144 }\n'
                                           '[spend]\nday_usd = 300\nmetered = ["openrouter"]\n[spend.week_usd]\nopenrouter = 25\n')
    cfg = models.load(tmp_path)
    assert models.for_role(cfg, "qwen-trial", watcher.load(tmp_path)) == models.Model("openrouter", "qwen/qwen3-coder-next", 262144)
    with pytest.raises(models.Question, match="no weekly cap"):
        models.for_role(cfg, "qwen-trial", watcher.parse({"day_usd": 300}))
    with pytest.raises(ValueError, match="needs a weekly cap"):
        watcher.parse({"day_usd": 300, "metered": ["openrouter"]})


QWEN_SPEND = {"day_usd": 300, "metered": ["openrouter"], "week_usd": {"openrouter": 25}}
QWEN_MODELS = {"providers": ["claude-code", "openrouter"], "builder": {"provider": "claude-code", "model": "sonnet"},
               "qwen-trial": {"provider": "openrouter", "model": "qwen/qwen3-coder-next", "context": 262144}}


def test_a_lane_on_a_pi_provider_role_starts_pi_with_the_owners_agent_dir_and_a_claude_role_does_not():
    """The Qwen3-Coder-Next trial (2026-11-25): the queue started every lane's worker as `--kind claude`; a lane whose [models] role
    is on openrouter starts `builder run --kind pi --provider openrouter --agent-dir <[models].pi_agent_dir>`."""
    from fichero_builder import queue

    assert queue.worker_kind(QWEN_MODELS, "") == ("claude", ())
    assert queue.worker_kind(QWEN_MODELS, "builder") == ("claude", ())
    with pytest.raises(RuntimeError, match="pi_agent_dir"):
        queue.worker_kind(QWEN_MODELS, "qwen-trial")
    mdl = {**QWEN_MODELS, "pi_agent_dir": "/Users/Shared/w/pi-agent"}
    assert queue.worker_kind(mdl, "qwen-trial") == ("pi", ("--provider", "openrouter", "--agent-dir", "/Users/Shared/w/pi-agent"))


@pytest.mark.parametrize("spent,starts", [(24.9, True), (25.0, False)])
def test_a_qwen_trial_run_parks_before_the_start_once_the_weeks_openrouter_rows_reach_25_usd(tmp_path, monkeypatch, spent, starts):
    """Dry run, no spend: the `builder run` a Qwen trial lane gets (kind pi, provider openrouter, its role, the feed's rules.json),
    with this week's openrouter cost rows at the cap, parks before Pi starts; under it, Pi is started."""
    from fichero_builder import __main__ as cli, journal, queue

    monkeypatch.setattr(cli, "state_dir", lambda root, state: tmp_path / "s")
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    journal.append("cost", task="qwen-trial-0", provider="openrouter", usd=spent)
    agent = tmp_path / "pi-agent"
    agent.mkdir()
    (agent / "models.json").write_text(json.dumps({"providers": {"openrouter": {"models": [
        {"id": "qwen/qwen3-coder-next", "cost": {"input": 0.2, "output": 0.8}}]}}}))
    mdl = {**QWEN_MODELS, "pi_agent_dir": str(agent)}
    (tmp_path / "rules.json").write_text(json.dumps({"spend": QWEN_SPEND, "models": mdl}))
    (tmp_path / "harness.toml").write_text("")
    (tmp_path / "b.txt").write_text("brief")
    started = []

    def no_spend(*a, **k):
        started.append(k.get("provider"))
        raise RuntimeError("dry run: Pi would start here")
    monkeypatch.setattr(pi_rpc, "start", no_spend)
    from fichero_builder import jail, start_tool
    monkeypatch.setattr(start_tool, "refusals", lambda *a: [])  # the start wall is the live config's, not this tmp root's
    monkeypatch.setattr(jail, "note_unjailed", lambda *a, **k: None)
    kind, pi = queue.worker_kind(mdl, "qwen-trial")
    argv = ["run", "--root", str(tmp_path), "--worktree", str(tmp_path), "--brief", str(tmp_path / "b.txt"), "--name", "qwen-trial",
            "--model", "qwen/qwen3-coder-next", "--kind", kind, "--role", "qwen-trial", "--rules", str(tmp_path / "rules.json"),
            "--scratch", str(tmp_path / "scratch"), *pi]
    if starts:
        with pytest.raises(RuntimeError, match="dry run"):
            cli.main(argv)
        assert started == ["openrouter"]
    else:
        assert cli.main(argv) == 0 and started == []
        assert any("this week's openrouter spend 25.00 USD reached the cap 25.00 before the start" in r.get("what", "") for r in journal.read())


def test_a_row_may_carry_an_effort_and_any_other_value_asks(tmp_path):
    (tmp_path / "harness.toml").write_text(TABLE.replace('model = "sonnet" }', 'model = "sonnet", effort = "low" }'))
    cfg = models.load(tmp_path)
    assert models.for_role(cfg, "builder").effort == "low"
    assert models.for_role(cfg, "reviewer").effort is None
    cfg["builder"]["effort"] = "max"
    with pytest.raises(models.Question, match="effort 'max'"):
        models.for_role(cfg, "builder")
