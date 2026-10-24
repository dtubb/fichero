"""`runtime.cloud-extractors.pages-together` (#5955): the steps that read each page with a model (names, claims, tables, diary
entries) ask for their pages together, up to the step's width, and write them in page order. A fake provider with 200 ms of
latency stands for the cloud; 40 pages at width 10 take about 0.8 s, not 8 s."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from fichero_server.workflows.tools._together import ahead, extract_width

LATENCY = 0.2


@pytest.fixture(autouse=True)
def _width(monkeypatch):
    monkeypatch.setenv("FICHERO_EXTRACT_MAX_IN_FLIGHT", "10")
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


# -- the helper ---------------------------------------------------------------------------------------------------------
def test_forty_calls_at_width_ten_take_a_fifth_of_the_time_and_come_back_in_order():
    in_flight, peak = 0, 0

    async def call(n):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(LATENCY)
        in_flight -= 1
        return n * 2

    async def run():
        return [(n, got) async for n, got in ahead(range(40), call, 10)]

    began = time.monotonic()
    got = asyncio.run(run())
    assert got == [(n, n * 2) for n in range(40)], "results out of page order"
    assert time.monotonic() - began < 2.0, "40 x 200 ms at width 10 should be about 0.8 s"
    assert peak <= 10, "more than the width in flight"


def test_a_call_that_fails_fails_at_its_own_page_and_the_rest_are_cancelled():
    started = []

    async def call(n):
        started.append(n)
        if n == 3:
            raise RuntimeError("quota")
        await asyncio.sleep(LATENCY)
        return n

    async def run():
        seen = []
        try:
            async for n, _ in ahead(range(30), call, 5):
                seen.append(n)
        except RuntimeError:
            pass
        return seen

    assert asyncio.run(run()) == [0, 1, 2]
    assert max(started) <= 8, "the window ran on after the failure"


def test_the_items_are_read_lazily_only_as_far_as_the_window_needs():
    pulled = []

    def items():
        for n in range(100):
            pulled.append(n)
            yield n

    async def call(n):
        return n

    async def run():
        async for n, _ in ahead(items(), call, 4):
            if n == 2:
                break

    asyncio.run(run())
    assert max(pulled) <= 7


def test_the_width_is_the_environment_or_the_cloud_width_for_a_hosted_model(monkeypatch):
    assert extract_width(None) == 10
    monkeypatch.delenv("FICHERO_EXTRACT_MAX_IN_FLIGHT")
    monkeypatch.setattr("fichero_server.workflows.builder._is_remote_model", lambda config: True)
    assert extract_width(object()) == 10
    monkeypatch.setattr("fichero_server.workflows.builder._is_remote_model", lambda config: False)
    assert extract_width(object()) == 3


# -- the steps ----------------------------------------------------------------------------------------------------------
def _library(tmp_path: Path, name: str, pages: int):
    from tests.integration._seedlib import seed

    from fichero_server.db import db_manager
    from fichero_server.models import DocType, Document, FileType

    library_path = tmp_path / f"{name}.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    for i in range(pages):
        db.save(Document(id=f"d{i:02d}", name=f"p{i:02d}.txt", doc_type=DocType.file, file_type=FileType.text,
                         page_content=f"Pedro Ruiz firmó la escritura en Quibdó en 18{i:02d}."))
    return library_path, db


def _inputs(library_path, pages, task):
    ids = [f"d{i:02d}" for i in range(pages)]
    return {"documents": [{"id": i} for i in ids]}, {"library_path": str(library_path), "selected_doc_ids": ids, "task_id": task}


def test_extract_entities_asks_forty_pages_together_and_writes_them_in_page_order(tmp_path, monkeypatch):
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.language_policy import parse_policy
    from fichero_server.workflows.tools import extract_entities_only as ent
    from fichero_server.workflows.tools.extract_all import _EntitiesOnly

    library_path, _db = _library(tmp_path, "ent", 40)
    monkeypatch.setattr(ent, "configured_policy", lambda: parse_policy(None))
    asked, written = [], []

    async def fake(**kwargs):
        asked.append(kwargs["prompt"])
        await asyncio.sleep(LATENCY)
        return _EntitiesOnly()

    async def progress(callback, event, *rest, **kw):
        if event == "file_start":
            written.append(rest[1])

    monkeypatch.setattr(ent, "chat_structured_with_fallback", fake)
    monkeypatch.setattr(ent, "emit_progress_event", progress)
    documents, state = _inputs(library_path, 40, "ent-together")
    began = time.monotonic()
    result = asyncio.run(ent.extract_entities_only(documents, state, LLMConfig(provider="fake", model="fake-model")))
    assert result["summary"]["documents_processed"] == 40
    assert len(asked) == 40
    assert time.monotonic() - began < 2.0, "pages were asked one after another"
    assert written == [f"Extract Entities p{i:02d}.txt" for i in range(40)], "write order changed"


def test_extract_svo_asks_the_dates_of_forty_pages_together_and_writes_them_in_page_order(tmp_path, monkeypatch):
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.language_policy import parse_policy
    from fichero_server.workflows.tools import extract_svo_only as svo

    library_path, _db = _library(tmp_path, "svo", 40)
    monkeypatch.setattr(svo, "configured_policy", lambda: parse_policy(None))
    written = []

    inflight, peak = 0, 0

    async def fake(**kwargs):
        nonlocal inflight, peak
        schema = kwargs["schema"]
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(LATENCY)
        inflight -= 1
        return schema(items=[{"date": "1842", "date_normalized": "1842", "verb": "dated", "object": "the deed",
                              "source_text": "en 1842"}])

    real_write = svo._write_kg_rows

    def record(db, section, items, doc_id, **kw):
        written.append(doc_id)
        return real_write(db, section, items, doc_id, **kw)

    monkeypatch.setattr(svo, "chat_structured_with_fallback", fake)
    monkeypatch.setattr(svo, "_write_kg_rows", record)
    documents, state = _inputs(library_path, 40, "svo-together")
    result = asyncio.run(svo.extract_svo_only(documents, state, LLMConfig(provider="fake", model="fake-model")))
    assert result["summary"]["claims_extracted"] == 40
    # Together is how many were in flight at once, not how long the machine took (a loaded gate stretched the wall time to 4.8 s).
    assert peak >= 8, f"pages were asked one after another (peak in flight {peak})"
    assert written == [f"d{i:02d}" for i in range(40)], "write order changed"


def _table_run(monkeypatch, units, stop_after=None):
    from fichero_server.recipes import table

    asked = []

    async def fake(prompt, schema, config, system=None, use_case=None):
        asked.append(prompt)
        await asyncio.sleep(LATENCY)
        if "boom" in prompt:
            raise RuntimeError("model said no")
        return prompt

    landed = []
    monkeypatch.setattr(table, "chat_structured_with_fallback", fake)
    monkeypatch.setattr(table, "prompt", lambda fields, text: text)
    monkeypatch.setattr(table, "_text", lambda db, unit: unit.text)
    monkeypatch.setattr(table, "_fields_of", lambda db, prototype: {"a": object()})
    monkeypatch.setattr(table, "answer_schema", lambda fields: None)
    monkeypatch.setattr(table, "units", lambda db, documents, prototype: units)
    monkeypatch.setattr(table, "_land", lambda db, unit, answer, **kw: landed.append(unit.name))
    stop = None if stop_after is None else (lambda: len(asked) >= stop_after)
    account = table.extract(None, [], prototype="p", provider="fake", model="m", run_id=None, step=None, stop=stop)
    return account, asked, landed


def _units(n):
    from types import SimpleNamespace

    return [SimpleNamespace(name=f"u{i:02d}", text=f"unit {i}") for i in range(n)]


def test_the_table_step_asks_its_units_together_and_lands_them_in_unit_order(monkeypatch):
    units = _units(40)
    units[7].text = "boom"
    units[9].text = ""
    began = time.monotonic()
    account, asked, landed = _table_run(monkeypatch, units)
    assert time.monotonic() - began < 2.0
    assert landed == [u.name for i, u in enumerate(units) if i not in (7, 9)], "landing order changed"
    assert (account["asked"], account["failed"], account["without_text"]) == (39, 1, 1)
    assert account["errors"] == ["u07: model said no"]


def test_ahead_starts_no_call_once_stop_is_asked_and_still_hands_back_the_ones_in_flight():
    """Stop is asked before EVERY new call, not only by the consumer: the window must not refill after Stop, or one more page
    leaves this Mac (## 891)."""
    started: list[int] = []
    stopped = False

    async def call(n):
        started.append(n)
        await asyncio.sleep(0.01)
        return n

    async def go():
        nonlocal stopped
        got = []
        async for n, _ in ahead(range(6), call, 2, stop=lambda: stopped):
            got.append(n)
            stopped = True  # the person pressed Stop while the first page was being written
        return got

    got = asyncio.run(go())
    assert started == [0, 1], f"a call started after Stop: {started}"
    assert got == [0, 1]  # the two in flight come back, in order, for the consumer to see Stop itself


def test_a_stop_sends_no_new_call_to_the_model(monkeypatch):
    account, asked, landed = _table_run(monkeypatch, _units(40), stop_after=12)
    assert 12 <= len(asked) <= 12 + 10, "calls went out after the stop beyond those already in flight"
    assert len(landed) < 40


@pytest.mark.xfail(reason="#5955: several pages in ONE call (the ruling: 20 pages make 2 to 4 calls) is not built; today one page per call",
                   strict=True)
def test_twenty_pages_make_two_to_four_calls(monkeypatch):
    account, asked, landed = _table_run(monkeypatch, _units(20))
    assert 2 <= len(asked) <= 4


def test_the_diary_step_asks_forty_pages_together_and_splits_them_in_page_order(monkeypatch):
    from types import SimpleNamespace

    from fichero_server.workflows.tools import diary_entries as diary

    applied = []

    async def ask(page, llm_config, prompt):
        await asyncio.sleep(LATENCY)
        if page.id == "p05":
            raise ValueError("page p05 says no")
        return SimpleNamespace(entries=[])

    async def split(db, page, llm_config, *, prototype_key=None, prompt=None, result=None):
        applied.append((page.id, result is not None))
        return []

    monkeypatch.setattr(diary, "_ask_for_split", ask)
    monkeypatch.setattr(diary, "split_page_into_entries", split)
    pages = [SimpleNamespace(id=f"p{i:02d}", page_content="texto", name=f"p{i:02d}") for i in range(40)]
    began = time.monotonic()
    created, totals, errors, lines = asyncio.run(diary.split_pages_into_entries(None, pages, object()))
    assert time.monotonic() - began < 2.0
    assert [p for p, _ in applied] == [f"p{i:02d}" for i in range(40) if i != 5], "order changed"
    assert all(had for _p, had in applied), "a page was asked again inline"
    assert errors == ["page p05 says no"]
