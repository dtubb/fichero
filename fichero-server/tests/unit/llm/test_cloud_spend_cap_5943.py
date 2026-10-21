"""`ai.where.cloud-spend-cap` (#5943): EVERY project caps what its cloud calls may spend a month (US$10 unless Set Up says
more). A call's worst case is held from the moment it is about to be sent; a queued page holds nothing; a call that would not
fit what is already booked is refused in words and its run is asked to pause; a call that fits only once calls in flight end
waits for them."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import pytest

from fichero_server import llm
from fichero_server.execution import cancellation
from fichero_server.llm import LLMConfig, spend, usage
from fichero_server.workflows import node_context

PRICED = LLMConfig(provider="openai", model="gpt-test", api_key="k", max_tokens=1000)  # worst: 30k in + 1k out
IN_RATE, OUT_RATE = 1e-6, 1e-5
WORST = 30_000 * IN_RATE + 1_000 * OUT_RATE  # 0.04
SMALL = (1000, 100)  # tokens a real answer reports: 0.002


@pytest.fixture(autouse=True)
def _fake_price_list(monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": (
        {"input_cost_per_token": IN_RATE, "output_cost_per_token": OUT_RATE} if model == "gpt-test" else None))
    spend._RESERVED.clear()


def _lane(width: int):
    """A lane `width` wide in place of the job lane (it needs a library database): what a queued page waits on."""
    holder: dict = {}

    @contextlib.asynccontextmanager
    async def slot(config, *, library=None, subject=None):
        sem = holder.setdefault("sem", asyncio.Semaphore(width))
        async with sem:
            yield
    return slot


@pytest.fixture(autouse=True)
def _a_lane_two_wide(monkeypatch):
    monkeypatch.setattr(llm, "_model_call_slot", _lane(2))


def _project(tmp_path: Path, cap=None) -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n" + ("" if cap is None else f"cloud_spend_cap_usd: {cap}\n"))
    return str(tmp_path / "P.fichero")


def _book(library: str, usd: float) -> None:
    spend._book(library, usd)


async def _call(library: str, *, config=PRICED, tokens=SMALL, fail=False, sent=None, hold=0.0):
    async with llm.model_call_slot(config, library=library):
        if sent is not None:
            sent.append(1)
        if hold:
            await asyncio.sleep(hold)
        if tokens:
            llm._record_usage(config.provider, config.model, "chat", input_tokens=tokens[0],
                              output_tokens=tokens[1], total_tokens=sum(tokens))
        if fail:
            raise RuntimeError("provider error")


def run(coro):
    return asyncio.run(coro)


def test_every_project_has_a_cap_of_ten_dollars_unless_it_says_more(tmp_path):
    assert spend.cap_usd(_project(tmp_path / "a")) == 10.0
    assert spend.cap_usd(_project(tmp_path / "b", 250)) == 250.0
    assert spend.cap_usd(str(tmp_path / "none.fichero")) == 10.0  # no setup saved at all
    for bad in ("-1", "'ten'", "true"):
        folder = tmp_path / ("bad" + bad.strip("'-")) / "P.fichero" / "recipe"
        folder.mkdir(parents=True)
        (folder / "setup.yaml").write_text(f"cloud_spend_cap_usd: {bad}\n")
        assert spend.cap_usd(str(folder.parent)) == 10.0  # a malformed answer is the default, never no cap
    assert spend.cap_usd(None) is None


def test_a_call_books_what_the_provider_reported_and_releases_its_hold(tmp_path):
    library = _project(tmp_path)
    run(_call(library))
    assert spend.booked_usd(library) == pytest.approx(1000 * IN_RATE + 100 * OUT_RATE)
    assert spend._RESERVED[library] == pytest.approx(0.0)


def test_ten_queued_pages_under_a_cap_of_three_worst_cases_all_send(tmp_path):
    """The cap is held when a page is about to SEND, not while it waits: a run's queued pages are not refused for money
    nobody has spent (review 679)."""
    library = _project(tmp_path, WORST * 3)
    sent: list[int] = []

    async def pages():
        return await asyncio.gather(*[_call(library, sent=sent, hold=0.01) for _ in range(10)], return_exceptions=True)
    results = run(pages())
    assert [r for r in results if isinstance(r, Exception)] == []
    assert len(sent) == 10
    assert spend.booked_usd(library) == pytest.approx(10 * (1000 * IN_RATE + 100 * OUT_RATE))


def test_a_call_that_would_not_fit_what_is_booked_is_refused_in_words_and_sends_nothing(tmp_path):
    library = _project(tmp_path, 1.0)
    _book(library, 1.0 - WORST / 2)
    sent: list[int] = []
    with pytest.raises(spend.CloudSpendRefusedError) as refused:
        run(_call(library, sent=sent))
    assert sent == []
    words = str(refused.value)
    assert "capped at $1.00" in words and "not sent" in words and "Raise the cap" in words


def test_a_call_that_fits_only_once_calls_in_flight_end_waits_for_them(tmp_path):
    library = _project(tmp_path, WORST * 1.5)  # room for one worst case in flight, not two
    order: list[str] = []

    async def first():
        async with llm.model_call_slot(PRICED, library=library):
            order.append("first sends")
            await asyncio.sleep(0.5)
            llm._record_usage("openai", "gpt-test", "chat", input_tokens=10, output_tokens=10, total_tokens=20)
        order.append("first ends")

    async def second():
        await asyncio.sleep(0.1)  # starts while the first is in flight
        async with llm.model_call_slot(PRICED, library=library):
            order.append("second sends")
            llm._record_usage("openai", "gpt-test", "chat", input_tokens=10, output_tokens=10, total_tokens=20)

    async def both():
        await asyncio.gather(first(), second())
    run(both())
    assert order == ["first sends", "first ends", "second sends"]  # waited, was not refused


def test_a_cap_reached_asks_the_workflow_run_to_pause_and_says_why(tmp_path):
    library = _project(tmp_path, 1.0)
    _book(library, 1.0)

    async def under_a_run():
        node_context.set_current_node("n1", run_id="run-cap-1")
        await _call(library)
    try:
        with pytest.raises(spend.CloudSpendRefusedError, match="the run is pausing"):
            run(under_a_run())
        assert cancellation.pause_requested("run-cap-1")
    finally:
        cancellation.clear_pause("run-cap-1")


def test_a_failed_call_books_only_what_was_reported(tmp_path):
    library = _project(tmp_path)
    with pytest.raises(RuntimeError):
        run(_call(library, tokens=None, fail=True))
    assert spend.booked_usd(library) == 0.0


def test_an_answer_with_no_usage_books_its_worst_case_never_free(tmp_path):
    library = _project(tmp_path)
    run(_call(library, tokens=None))
    assert spend.booked_usd(library) == pytest.approx(WORST)


def test_a_call_cancelled_after_it_was_sent_books_its_worst_case(tmp_path):
    library = _project(tmp_path)

    async def cancelled():
        task = asyncio.ensure_future(_call(library, tokens=None, hold=5))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    run(cancelled())
    assert spend.booked_usd(library) == pytest.approx(WORST)
    assert spend._RESERVED[library] == pytest.approx(0.0)


def test_a_model_with_no_listed_price_accepted_by_the_project_is_held_at_an_assumed_price_never_free(tmp_path):
    library = _project(tmp_path)
    config = LLMConfig(provider="openai", model="mystery", api_key="k")
    spend.set_accepted(library, "openai", "mystery", True)
    run(_call(library, config=config, tokens=(10, 10)))
    assert spend.booked_usd(library) == pytest.approx(spend.UNPRICED_CALL_USD)  # counts against the cap, never free
    assert spend.assumed(library) == (1, pytest.approx(spend.UNPRICED_CALL_USD))  # and listed apart: which spend is assumed


def test_the_worst_case_output_is_the_models_catalogue_maximum_when_that_is_smaller(monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": IN_RATE, "output_cost_per_token": OUT_RATE, "max_output_tokens": 200})
    config = LLMConfig(provider="openai", model="gpt-test", api_key="k")  # max_tokens 8192
    assert spend.worst_case_usd(config) == pytest.approx(30_000 * IN_RATE + 200 * OUT_RATE)


def test_a_new_month_starts_from_zero(tmp_path):
    library = _project(tmp_path)
    (Path(library) / "recipe" / spend.LEDGER).write_text(json.dumps({"month": "2000-01", "usd": 999.0}))
    assert spend.booked_usd(library) == 0.0
    run(_call(library))


def test_a_model_on_this_mac_spends_nothing_and_is_not_held(tmp_path):
    library = _project(tmp_path, 0)
    config = LLMConfig(provider="ollama", model="llama3.2", api_base="http://127.0.0.1:11434")
    run(_call(library, config=config, tokens=(10, 10)))
    assert spend.booked_usd(library) == 0.0


def test_the_chat_books_the_answers_usage_not_its_worst_case():
    """Source pin (review 679 LOW 1, 2): the chat records its usage inside the slot, and a chat that names no model config
    is held by the cap too."""
    source = (Path(llm.__file__).parent.parent / "api" / "routes" / "system" / "chat.py").read_text(encoding="utf-8")
    slot = source.index('model_call_slot(config, library=ctx.library_path, subject="Chat")')
    assert source.index("record_call_usage(config, response)", slot) < source.index("return response", slot)
    assert "spend.holding(None, ctx.library_path)" in source


def test_every_call_slot_is_the_one_that_holds_the_cap():
    assert llm._remote_llm_call_slot is llm.model_call_slot
