"""`designer.budget.run-cap` (#6295): a run's own cap is held beside the project's caps, the lowest deciding; it counts only what the
run spends, and it goes when the run ends."""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import LLMConfig, spend, usage

CONFIG = LLMConfig(provider="openai", model="gpt-test", api_key="k", max_tokens=1000)  # worst case $0.04


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {"input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5})
    spend._RESERVED.clear()
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    return str(tmp_path / "P.fichero")


def _call(library) -> None:
    async def go():
        async with spend.holding(CONFIG, library):
            pass

    asyncio.run(go())


def test_a_run_cap_below_what_the_project_leaves_refuses_at_the_run_cap(library):
    spend._book(library, 3.0)  # spent before the run: not the run's
    spend.set_run_cap(library, "job-1", 0.03)
    with pytest.raises(spend.CloudSpendRefusedError) as refused:
        _call(library)
    assert "this run's cloud spend is capped at $0.03" in str(refused.value)


def test_the_run_cap_counts_only_the_runs_own_spend(library):
    spend._book(library, 3.0)
    spend.set_run_cap(library, "job-1", 1.0)
    _call(library)  # 0.04 fits the run's $1.00 though $3.00 was booked before it: no refusal
    assert spend.run_cap(library)  # and the run's cap is still held


def test_the_project_cap_still_refuses_first_when_it_is_lower(library):
    (spend._recipe_dir(library) / "setup.yaml").write_text("cloud_project_cap_usd: 0.01\n")
    spend.set_run_cap(library, "job-1", 5.0)
    with pytest.raises(spend.CloudSpendRefusedError) as refused:
        _call(library)
    assert "in all" in str(refused.value)


def test_no_run_cap_means_the_project_caps_alone_and_the_cap_goes_with_its_run(library):
    _call(library)
    spend.set_run_cap(library, "job-1", 0.0)
    spend.clear_run_cap(library, "job-2")  # another run's end leaves it
    assert spend.run_cap(library)
    spend.clear_run_cap(library, "job-1")
    assert spend.run_cap(library) is None
    _call(library)


def test_the_run_cap_is_changed_in_place_and_a_run_without_one_refuses(library):
    assert not spend.change_run_cap(library, 5.0)  # no run holds a cap
    spend._book(library, 1.0)
    spend.set_run_cap(library, "job-1", 0.03)
    assert spend.change_run_cap(library, 2.0)
    held = spend.run_cap(library)
    assert held["cap_usd"] == 2.0 and held["job_id"] == "job-1" and held["from_usd"] == 1.0  # still counts from the run's start
    _call(library)  # 0.04 now fits


def test_the_cap_route_changes_the_run_cap_and_refuses_when_no_run_holds_one(client, db):
    from fichero_server.api.routes.system import recipes as routes

    library = str(routes._library(db))
    refused = client.put("/api/recipes/project/cloud-cap", json={"run_cap_usd": 3.0})
    assert refused.status_code == 422 and "No run is holding a cap" in refused.text
    spend.set_run_cap(library, "job-1", 1.0)
    ok = client.put("/api/recipes/project/cloud-cap", json={"run_cap_usd": 3.0})
    assert ok.status_code == 200 and ok.json()["run_cap_usd"] == 3.0 and ok.json()["audit_id"] is None
