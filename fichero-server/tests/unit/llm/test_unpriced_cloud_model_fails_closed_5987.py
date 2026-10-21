"""`ai.where.project-cloud-spend-cap` + `ai.where.accept-unpriced-cloud-model` (#5987): a cloud call to a model with no listed price
is refused at the call unless the project accepted that provider + model; the refusal is plain words with the way out in fields,
and it is one typed error that stops a page loop once; a reply that would not parse is still billed."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig, spend, usage

MYSTERY = LLMConfig(provider="acme", model="mystery", api_key="k")
OTHER = LLMConfig(provider="other", model="mystery", api_key="k")


@pytest.fixture(autouse=True)
def _nothing_is_priced(monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": None)
    spend._RESERVED.clear()

    @contextlib.asynccontextmanager
    async def lane(config, *, library=None, subject=None):
        yield

    monkeypatch.setattr(llm, "_model_call_slot", lane)


def _project(tmp_path: Path) -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n")
    return str(tmp_path / "P.fichero")


async def _call(library, config):
    async with llm.model_call_slot(config, library=library):
        pass


def test_refused_unless_accepted_and_the_yes_is_for_that_provider_and_model_only(tmp_path):
    library = _project(tmp_path)
    with pytest.raises(spend.CloudModelUnpriced):
        asyncio.run(_call(library, MYSTERY))
    spend.set_accepted(library, "acme", "mystery", True)
    asyncio.run(_call(library, MYSTERY))
    with pytest.raises(spend.CloudModelUnpriced):  # the same model id under another provider
        asyncio.run(_call(library, OTHER))
    spend.set_accepted(library, "acme", "mystery", False)
    with pytest.raises(spend.CloudModelUnpriced):
        asyncio.run(_call(library, MYSTERY))


def test_the_refusal_speaks_plainly_and_carries_the_way_out_as_fields(tmp_path):
    library = _project(tmp_path)
    with pytest.raises(spend.CloudModelUnpriced) as refused:
        asyncio.run(_call(library, MYSTERY))
    words = str(refused.value)
    assert "mystery" in words and "accept" in words.lower() and "Press Start" not in words
    assert "cloud.accept_unpriced" not in words and "/api/" not in words
    err = refused.value
    assert (err.action, err.route, err.provider, err.model) == (
        "cloud.accept_unpriced", "/api/recipes/cloud/accept-unpriced", "acme", "mystery")


def test_accepting_makes_no_set_up_and_a_model_on_this_mac_needs_no_yes(tmp_path):
    library = str(tmp_path / "bare.fichero")
    spend.set_accepted(library, "acme", "mystery", True)
    assert spend.accepted_models(library) == ["acme/mystery"]
    assert not (Path(library) / "recipe" / "setup.yaml").exists()
    asyncio.run(_call(_project(tmp_path / "x"), LLMConfig(provider="ollama", model="mystery")))  # free: not held


def test_both_refusals_end_a_page_loop_once_not_once_a_page():
    assert issubclass(spend.CloudSpendRefusedError, spend.RefusedForTheRun)
    assert issubclass(spend.CloudModelUnpriced, spend.RefusedForTheRun)
    from fichero_server.workflows.tools.vision_base import _refusal_of

    assert _refusal_of(spend.CloudSpendRefusedError("x")) == {"refusal": {"locale": None, "source": "run"}}
    assert _refusal_of(spend.CloudModelUnpriced("x")) == {"refusal": {"locale": None, "source": "run"}}
    assert _refusal_of(RuntimeError("x")) == {}
