"""`ai.where.cloud-spend-cap` (#5943): a project caps what its cloud calls may spend a month. A call's worst case is
reserved before it is sent and released with the real cost; over the cap it is refused in words, having sent nothing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig, spend, usage

PRICED = LLMConfig(provider="openai", model="gpt-test", api_key="k", max_tokens=1000)  # worst: 30k in + 1k out
IN_RATE, OUT_RATE = 1e-6, 1e-5
WORST = 30_000 * IN_RATE + 1_000 * OUT_RATE  # 0.04


@pytest.fixture(autouse=True)
def _fake_price_list(monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": (
        {"input_cost_per_token": IN_RATE, "output_cost_per_token": OUT_RATE} if model == "gpt-test" else None))
    spend._RESERVED.clear()


def _project(tmp_path: Path, cap) -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n" + ("" if cap is None else f"cloud_spend_cap_usd: {cap}\n"))
    return str(tmp_path / "P.fichero")


def _call(library: str, *, config=PRICED, tokens: tuple[int, int] | None = (1000, 100), fail=False):
    """One call through the slot: `tokens` is the usage the provider reports (None: it reports none)."""
    async def run():
        async with llm.model_call_slot(config, library=library):
            if tokens:
                llm._record_usage(config.provider, config.model, "chat", input_tokens=tokens[0],
                                  output_tokens=tokens[1], total_tokens=sum(tokens))
            if fail:
                raise RuntimeError("provider error")
    return asyncio.run(run())


def test_no_cap_is_no_limit_and_books_nothing(tmp_path):
    library = _project(tmp_path, None)
    _call(library)
    assert not (Path(library) / "recipe" / spend.LEDGER).exists()


def test_a_call_that_fits_books_what_the_provider_reported_and_releases_its_hold(tmp_path):
    library = _project(tmp_path, 1.0)
    _call(library, tokens=(1000, 100))
    assert spend.booked_usd(library) == pytest.approx(1000 * IN_RATE + 100 * OUT_RATE)
    assert spend._RESERVED[library] == pytest.approx(0.0)


def test_a_call_whose_worst_case_does_not_fit_is_refused_in_words_and_sends_nothing(tmp_path):
    library = _project(tmp_path, WORST / 2)
    sent = []
    with pytest.raises(spend.CloudSpendRefusedError) as refused:
        async def run():
            async with llm.model_call_slot(PRICED, library=library):
                sent.append(1)
        asyncio.run(run())
    assert sent == []
    assert "caps its cloud spend" in str(refused.value) and "not sent" in str(refused.value)


def test_a_cap_of_zero_refuses_every_priced_cloud_call(tmp_path):
    with pytest.raises(spend.CloudSpendRefusedError):
        _call(_project(tmp_path, 0))


def test_what_is_booked_counts_against_the_next_call(tmp_path):
    library = _project(tmp_path, WORST * 1.5)
    _call(library, tokens=(30_000, 1_000))  # books its full worst case
    with pytest.raises(spend.CloudSpendRefusedError):
        _call(library)


def test_calls_in_flight_hold_their_worst_case_so_two_at_once_cannot_both_pass(tmp_path):
    library = _project(tmp_path, WORST * 1.5)
    refused = []

    async def run():
        async with llm.model_call_slot(PRICED, library=library):  # holds 0.04 of 0.06
            llm._record_usage("openai", "gpt-test", "chat", input_tokens=10, output_tokens=10, total_tokens=20)
            try:
                async with llm.model_call_slot(PRICED, library=library):  # needs 0.04 more: does not fit
                    pass
            except spend.CloudSpendRefusedError:
                refused.append(1)
        async with llm.model_call_slot(PRICED, library=library):  # the first ended: its hold is released, 0.0002 booked
            llm._record_usage("openai", "gpt-test", "chat", input_tokens=10, output_tokens=10, total_tokens=20)
    asyncio.run(run())
    assert refused == [1]
    assert spend.booked_usd(library) == pytest.approx(2 * (10 * IN_RATE + 10 * OUT_RATE))


def test_a_failed_call_books_only_what_was_reported(tmp_path):
    library = _project(tmp_path, 1.0)
    with pytest.raises(RuntimeError):
        _call(library, tokens=None, fail=True)
    assert spend.booked_usd(library) == 0.0


def test_an_answer_with_no_usage_books_its_worst_case_never_free(tmp_path):
    library = _project(tmp_path, 1.0)
    _call(library, tokens=None)
    assert spend.booked_usd(library) == pytest.approx(WORST)


def test_a_model_with_no_listed_price_cannot_be_held_to_a_cap(tmp_path):
    config = LLMConfig(provider="openai", model="mystery", api_key="k")
    with pytest.raises(spend.CloudSpendRefusedError, match="no listed price"):
        _call(_project(tmp_path, 5.0), config=config)
    _call(_project(tmp_path / "other", None), config=config)  # with no cap it is only unpriced, as ever


def test_a_new_month_starts_from_zero(tmp_path):
    library = _project(tmp_path, 1.0)
    (Path(library) / "recipe" / spend.LEDGER).write_text(json.dumps({"month": "2000-01", "usd": 999.0}))
    assert spend.booked_usd(library) == 0.0
    _call(library)


def test_a_model_on_this_mac_spends_nothing_and_is_not_held(tmp_path):
    library = _project(tmp_path, 0)
    config = LLMConfig(provider="ollama", model="llama3.2", api_base="http://127.0.0.1:11434")
    _call(library, config=config, tokens=(10, 10))
    assert spend.booked_usd(library) == 0.0


def test_a_malformed_cap_is_no_cap(tmp_path):
    for bad in ("-1", "'ten'", "true"):
        folder = tmp_path / bad.strip("'-") / "P.fichero" / "recipe"
        folder.mkdir(parents=True)
        (folder / "setup.yaml").write_text(f"cloud_spend_cap_usd: {bad}\n")
        assert spend.cap_usd(str(folder.parent)) is None


def test_every_call_slot_is_the_one_that_holds_the_cap():
    assert llm._remote_llm_call_slot is llm.model_call_slot
