"""The ceiling run's 25 USD cap (#6978, `hands.ceiling.cap-is-enforced-by-the-script`). A fake provider: nothing is spent."""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from fichero_server import llm
from fichero_server.llm import EgressRefusedError, LLMConfig, egress, usage

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("blind_hands_ceiling", REPO_ROOT / "scripts" / "blind_hands" / "ceiling.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)

CLOUD = LLMConfig(provider="openai", model="gpt-test", api_key="sk-test")
PAGES = ["h-p2", "h-p3", "h-p4"]
# 10 USD a page by estimate; the fake provider reports 1000 tokens in and 500 out, which these rates price at 9 USD
PRICES = {"openai/gpt-test": {"estimated_usd_per_page": 10.0, "input_usd_per_token": 0.004, "output_usd_per_token": 0.01}}


@pytest.fixture
def run(tmp_path, monkeypatch):
    """`run(prompt=..., config=...)` reads the three-page hand; `run.requests` lists what reached the fake provider."""
    made: list = []

    class _Answer:
        content = "the reading"
        usage_metadata = {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}
        response_metadata: dict = {}

    class _Model:
        async def ainvoke(self, messages, *a, **k):
            made.append(messages)
            return _Answer()

    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")
    egress._CACHE.clear()
    llm._LLM_RESULT_CACHE.clear()
    monkeypatch.setattr(llm, "_build_langchain_model", lambda config: _Model())
    # the engine's own spending cap refuses a model its registry does not price
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5})

    hand = {"id": "h", "script": "caroline", "period": "12th c.", "licence": "CC-BY-4.0", "may_leave_this_mac": True,
            "pool": ["h-p1"], "held_out": PAGES, "manuscripts": {"h-p1": "msA", **{p: "msB" for p in PAGES}}}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 0, "page_list_sha256": c.manifest.page_list_digest([hand]), "hands": [hand]}))
    (tmp_path / "Scratch.fichero" / "recipe").mkdir(parents=True)
    (tmp_path / "Scratch.fichero" / "recipe" / "setup.yaml").write_text("cloud_allowed: true\n", encoding="utf-8")
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps(PRICES))
    monkeypatch.setattr(c, "PRICES", prices)
    monkeypatch.setattr(c, "LEDGER", tmp_path / "ledger.json")

    def _run(prompt="Read this page", config=CLOUD):
        return c.read_hand("h", {p: f"data:image/png;base64,{p}" for p in PAGES}, project=tmp_path / "Scratch.fichero",
                           config=config, prompt=prompt, manifest_path=manifest)

    _run.requests = made
    _run.ledger = lambda: json.loads((tmp_path / "ledger.json").read_text())
    return _run


def test_the_cap_is_25_usd_and_no_argument_names_it_or_the_ledger():
    assert c.CAP_USD == 25
    assert not {"cap", "cap_usd", "ledger", "prices"} & set(inspect.signature(c.read_hand).parameters)


def test_the_request_that_would_pass_the_cap_is_not_made(run):
    # 9 + 9 actual, then 18 + 10 estimated > 25
    with pytest.raises(SystemExit) as stopped:
        run()
    assert str(stopped.value) == "stopped at the cap: 2 of 3 pages read"
    assert len(run.requests) == 2
    assert [e["page"] for e in run.ledger()] == ["h-p2", "h-p3"]


def test_the_providers_cost_replaces_the_estimate_in_the_ledger(run):
    with pytest.raises(SystemExit):
        run()
    assert [(e["usd"], e["estimated"]) for e in run.ledger()] == [(9.0, False), (9.0, False)]


def test_a_second_start_reuses_the_pages_read_and_makes_no_request(run):
    with pytest.raises(SystemExit):
        run()
    del run.requests[:]
    with pytest.raises(SystemExit) as stopped:
        run()
    assert str(stopped.value) == "stopped at the cap: 2 of 3 pages read"
    assert run.requests == []
    assert len(run.ledger()) == 2


def test_a_second_start_with_a_full_ledger_makes_no_request(run):
    with pytest.raises(SystemExit):
        run()
    del run.requests[:]
    # another prompt is another reading, so nothing is reused; the earlier run's 18 USD still counts
    with pytest.raises(SystemExit) as stopped:
        run(prompt="Read it again")
    assert str(stopped.value) == "stopped at the cap: 0 of 3 pages read"
    assert run.requests == []


def test_an_estimate_left_by_a_run_that_died_still_counts(run):
    c.LEDGER.write_text(json.dumps([{"key": "k", "page": "x", "model": "openai/gpt-test", "usd": 20.0,
                                     "estimated": True, "reading": None}]))
    with pytest.raises(SystemExit) as stopped:
        run()
    assert str(stopped.value) == "stopped at the cap: 0 of 3 pages read"
    assert run.requests == []


def test_an_unpriced_model_refuses_with_no_request_made(run):
    with pytest.raises(c.CeilingRefused, match="openai/gpt-other"):
        run(config=LLMConfig(provider="openai", model="gpt-other", api_key="sk-test"))
    assert run.requests == []
    assert not c.LEDGER.exists()


def test_a_request_the_egress_gate_refuses_leaves_no_estimate_in_the_ledger(run, tmp_path):
    (tmp_path / "Scratch.fichero" / "recipe" / "setup.yaml").write_text("cloud_allowed: false\n", encoding="utf-8")
    with pytest.raises(EgressRefusedError):
        run()
    assert run.requests == []
    assert run.ledger() == []


def test_the_committed_price_table_loads():
    assert isinstance(json.loads(c.PRICES.read_text()), dict)
