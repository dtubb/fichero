"""Every stage of a recipe run resumes after a Stop: nothing already done is done again, and the run ends done
(owner release condition 2026-10-24, review ## 1134; `source.recipe.done-is-not-redone`, `source.recipe.read-resumes-per-line`).

One parametrized test over the stages: Find Lines, Leave Out, Read, Names, Correct, Translate, Catalogue. The run is held on the
stage's FIRST unit (a page, a line's page, a folder) by a Gate around the stage's own per-unit work; Stop is pressed there; the
Gate lets go and the run ends cancelled. Started again, the stage does only the units the stopped run had not finished (its calls
the second time equal the units not done), and the run ends done with every unit done. A second test loses the engine the way
a death leaves the row (the worker ends, the row stays running) for Read and Catalogue, the two paid stages. A last test checks a
page stopped half-read reads on from its unread lines only.

Through the public surface with the real scheduler, as test_start_stop_restart_resumes does. Only the models are stubs.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from fichero_server.execution import jobs
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    CLOUD,
    _finished,
    _recipe,
    _run_status,
    _start,
    _wait,
    engine,
    pages,
)
from tests.unit.recipes.test_stop_reaches_inline_steps_5609 import LINES, READ, _save, _stop
from tests.unit.workflows.test_one_line_pass_read_many import _kraken_reads, _lines, _passes, _transcribe, page  # noqa: F401  (fixture)

LEAVE = {"id": "leave", "job": "leave-out", "model": {"builtin": "leave-out-rules"}}
NAMES = {"id": "names", "job": "find-names-tag-words"}
CORRECT = {"id": "correct", "job": "correct", "model": CLOUD, "runs_on": "cloud:openai"}
TRANSLATE = {"id": "translate", "job": "translate-transliterate-normalise", "model": CLOUD, "runs_on": "cloud:openai",
             "settings": {"target": ["regularised"]}}
CATALOGUE = {"id": "catalogue", "job": "describe-for-the-catalogue", "model": CLOUD, "runs_on": "cloud:openai"}
WRITTEN = "Yten dixo el testigo"


class Hold:
    """Wraps `module.name`: the first call waits (saying it entered) until let go; every call is kept as its unit."""

    def __init__(self, monkeypatch, module, name, unit_of):
        self.entered, self.release, self.units = threading.Event(), threading.Event(), []
        real = getattr(module, name)
        gate = self

        async def _wait_async():
            import asyncio

            await asyncio.to_thread(gate.release.wait, 30)

        if _is_coroutine(real):
            async def held(*args, **kwargs):
                gate.units.append(unit_of(args, kwargs))
                if len(gate.units) == 1:
                    gate.entered.set()
                    await _wait_async()
                return await real(*args, **kwargs)
        else:
            def held(*args, **kwargs):
                gate.units.append(unit_of(args, kwargs))
                if len(gate.units) == 1:
                    gate.entered.set()
                    assert gate.release.wait(30), "the test never let the stage go"
                return real(*args, **kwargs)

        monkeypatch.setattr(module, name, held)


def _is_coroutine(fn) -> bool:
    import inspect

    return inspect.iscoroutinefunction(fn)


def _page_names(db, ids) -> set[str]:
    from fichero_server.models import Document

    return {db.get(Document, i).name for i in ids}


def _all_pages(db) -> list[str]:
    from fichero_server.recipes.done import pages_for

    return pages_for(db, {}, None)


def _done_pages(db, job: str, card: dict | None = None) -> set[str]:
    """The pages (by name) the stage's own record says it has done."""
    from fichero_server.recipes import done

    return _page_names(db, [p for p in _all_pages(db) if done.is_done(db, {"job": job, **(card or {})}, p)])


def _stage_cases():
    """(id, recipe steps, the module and function that do one unit, which unit a call is, the units a stopped run has done)."""
    from fichero_server.llm import kraken_runtime
    from fichero_server.recipes import leave_out
    from fichero_server.workflows.tools import extract_entities_only

    import fichero_server.llm as llm

    def image(args, kwargs):
        return Path(args[0]).name

    return {
        "find-lines": dict(steps=[LINES], target=(kraken_runtime, "segment_to_geometry"), unit_of=image,
                           done=lambda db: _done_pages(db, "find-lines")),
        "leave-out": dict(steps=[LINES, LEAVE], target=(leave_out, "decide"), unit_of=None,
                          done=lambda db: _done_pages(db, "leave-out")),
        "read": dict(steps=[LINES, READ], target=(kraken_runtime, "recognize_to_geometry"), unit_of=image,
                     done=lambda db: _done_pages(db, "read-a-line")),
        "names": dict(steps=[LINES, READ, NAMES], target=(extract_entities_only, "resolve_language"), unit_of=None,
                      done=lambda db: _done_pages(db, "find-names-tag-words")),
        "correct": dict(steps=[LINES, READ, CORRECT], target=(llm, "vision"), unit_of=None,
                        done=lambda db: _done_pages(db, "correct", {"model_override": CLOUD["model"]})),
        "translate": dict(steps=[LINES, READ, TRANSLATE], target=(llm, "vision"), unit_of=None,
                          done=lambda db: _done_pages(db, "translate-transliterate-normalise",
                                                      {"model_override": CLOUD["model"],
                                                       "tool_config": {"analyze": {"reading_kind": "transcription",
                                                                                   "reading_level": "regularised"}}})),
    }


@pytest.fixture(autouse=True)
def _memory_is_not_the_question(monkeypatch):
    """The stub reader loads nothing: the memory guard (`throttle.memory_short`) must not hold it on a busy test Mac."""
    monkeypatch.setattr("fichero_server.execution.throttle.memory_short", lambda **kw: None)


@pytest.fixture
def stubs(monkeypatch, engine):
    """The segmenter on its own (Find Lines alone has no reader), and the vision model every step that looks at a page asks."""
    import fichero_server.llm as llm
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(kraken_runtime, "segment_to_geometry",
                        lambda image_path, **kw: engine.recognize(image_path, None))

    async def vision(images, prompt, config, **kw):
        return WRITTEN

    monkeypatch.setattr(llm, "vision", vision)
    return engine


def _hold_and_stop(client, gate) -> None:
    job_id = _start(client)
    assert gate.entered.wait(60), _run_status(client, job_id)
    assert _stop(client, job_id) == "stopping"
    gate.release.set()
    assert _finished(client, job_id)["state"] == "cancelled"


@pytest.mark.parametrize("stage", ["correct", "translate"])
def test_a_stage_stopped_on_its_first_unit_resumes_and_redoes_nothing(stage, client, db, pages, tmp_path, stubs, monkeypatch,
                                                                      with_material):
    case = _stage_cases()[stage]
    module, name = case["target"]
    unit_of = case["unit_of"] or (lambda args, kwargs: len(args) + len(kwargs))  # a call: counted, not named
    gate = Hold(monkeypatch, module, name, unit_of)
    _save(client, _recipe(tmp_path, *case["steps"]))
    try:
        _hold_and_stop(client, gate)
    finally:
        gate.release.set()
    done_first = case["done"](db)
    calls_first = len(gate.units)
    assert calls_first >= 1
    assert done_first < set(_page_names(db, _all_pages(db))), f"{stage}: the Stop came after every page: nothing to resume"

    run = _finished(client, _start(client))

    assert run["state"] == "done", run
    every = _page_names(db, _all_pages(db))
    assert case["done"](db) == every, f"{stage}: pages not done after the second Start: {every - case['done'](db)}"
    again = len(gate.units) - calls_first
    # Pages done by the stopped run are not asked again; a page it had started and not finished is.
    assert again <= len(every - done_first) * _calls_a_unit(stage), (
        f"{stage}: the second Start made {again} calls for {len(every - done_first)} pages not done; done first: {done_first}")


def _calls_a_unit(stage: str) -> int:
    """The calls a page may take when it is done: a review asks once per lens; Translate once."""
    return 3 if stage == "correct" else 1  # the review asks once per lens


def _folders(db, pages):
    """The two photographs each in a folder of its own, the folders in one: three folders to describe."""
    from fichero_server.models import DocType, Document

    top = Document(name="Top", doc_type=DocType.folder)
    db.save(top)
    for i, photograph in enumerate(pages):
        box = Document(name=f"Box {i}", doc_type=DocType.folder, parent_id=top.id)
        db.save(box)
        photograph.parent_id = box.id
        db.save(photograph)
    return top


def _described(db) -> set[str]:
    from fichero_server.models import DocType, Document
    from fichero_server.recipes import catalogue_step

    return {f.name for f in db.query(Document) if f.doc_type == DocType.folder and catalogue_step._latest(db, f.id) is not None}


def _catalogue_run(client, db, pages, tmp_path, monkeypatch, *, lose_the_engine: bool):
    import fichero_server.llm as llm

    _folders(db, pages)
    asked: list[str] = []
    real_holder = {}

    async def describe(material, config=None, system=None, permissive_guardrails=False):
        asked.append(material.split("\n", 1)[0])
        if len(asked) == 1:
            if lose_the_engine:
                raise _EngineDied()
            gate.entered.set()
            assert await __import__("asyncio").to_thread(gate.release.wait, 30), "the test never let the stage go"
        return "Title: A box.\nScope and content: Letters."

    gate = type("G", (), {"entered": threading.Event(), "release": threading.Event()})()
    monkeypatch.setattr(llm, "chat_with_fallback", describe)
    del real_holder
    _save(client, _recipe(tmp_path, LINES, READ, CATALOGUE))
    return asked, gate


class _EngineDied(BaseException):
    """The worker ends as the engine's death ends it: nothing in the run gets to write its row."""


def test_catalogue_stopped_on_its_first_folder_describes_only_the_rest_after_a_restart(client, db, pages, tmp_path, stubs,
                                                                                         monkeypatch, with_material):
    asked, gate = _catalogue_run(client, db, pages, tmp_path, monkeypatch, lose_the_engine=False)
    try:
        _hold_and_stop(client, gate)
    finally:
        gate.release.set()
    done_first, calls_first = _described(db), len(asked)
    assert calls_first >= 1 and len(done_first) < 3, (done_first, calls_first)

    run = _finished(client, _start(client))

    assert run["state"] == "done", run
    assert _described(db) == {"Top", "Box 0", "Box 1"}
    assert len(asked) - calls_first == 3 - len(done_first), f"folders asked again: {asked[calls_first:]} (done first: {done_first})"


def test_catalogue_lost_with_the_engine_then_resumed_describes_each_folder_once(client, db, pages, tmp_path, stubs, monkeypatch,
                                                                                with_material):
    asked, _gate = _catalogue_run(client, db, pages, tmp_path, monkeypatch, lose_the_engine=True)
    job_id = _start(client)
    assert _wait(lambda: len(asked) >= 1), _run_status(client, job_id)
    done_first = _described(db)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ? AND state IN ('running', 'failed')", [job_id])
    jobs.resume(db)
    r = client.post(f"/api/activity/jobs/{job_id}/retry")
    assert r.status_code in (200, 409), r.text
    run = _finished(client, job_id)

    assert run["state"] == "done", run
    assert _described(db) == {"Top", "Box 0", "Box 1"}
    again = asked[1:]
    assert len(again) == 3 - len(done_first) and len(set(again)) == len(again), f"asked after the restart: {again}"


def test_read_lost_with_the_engine_then_started_again_reads_each_page_once(client, db, pages, tmp_path, stubs, monkeypatch,
                                                                             with_material):
    from fichero_server.llm import kraken_runtime

    real = kraken_runtime.recognize_to_geometry
    calls: list[str] = []

    def dies_on_the_first_page(image_path, *args, **kwargs):
        calls.append(Path(image_path).name)
        if len(calls) == 1:  # the engine dies in the first page's read
            raise _EngineDied()
        return real(image_path, *args, **kwargs)

    pages_in_the_run = len(_all_pages(db))
    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", dies_on_the_first_page)
    _save(client, _recipe(tmp_path, LINES, READ))
    job_id = _start(client)
    assert _wait(lambda: len(calls) >= 1), _run_status(client, job_id)
    from fichero_server.execution import runner as execution_runner
    from fichero_server.workflows.run_account import mark_interrupted_runs

    execution_runner._running_workflows.clear()  # the engine's memory of its workflow runs went with it
    mark_interrupted_runs(db)  # what opening the project does first: the run the dead engine left is marked interrupted
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ? AND state IN ('running', 'failed')", [job_id])
    jobs.resume(db)
    r = client.post(f"/api/activity/jobs/{job_id}/retry")
    assert r.status_code in (200, 409), r.text
    # A workflow run the engine's death cut off ends as interrupted, with its pages not done kept: the run says so and Start again
    # reads those pages (`activity.durable.interrupted-run-offers-the-rest`).
    assert _finished(client, job_id)["state"] in ("failed", "done")
    again = _start(client)
    run = _finished(client, again)

    assert run["state"] == "done", run
    after = calls[1:]  # the first call died before it read: that page is read again, once; every other page once
    assert len(after) == len(set(after)) == pages_in_the_run, f"pages read after the restart: {after}"


@pytest.mark.asyncio
async def test_a_page_stopped_half_read_reads_on_from_its_unread_lines_only(page, monkeypatch):
    """`source.recipe.read-resumes-per-line`: a page whose read stopped keeps the lines it read; Start again reads the rest, so a
    cloud reader is not paid twice for a line. A redo (`read_all_lines`) reads every line again; another reader reads them all."""
    from fichero_server.llm.working_lines import unread_by, working_lines

    await _transcribe(page)  # the lines are found
    lines = _lines(page, _passes(page)[0].id)
    _kraken_reads(monkeypatch, ["el dicho escrivano", "vezino de la ciudad", "y lo firmo"])
    await _transcribe(page, kraken_model="kraken-mccatmus")
    page["db"].execute("DELETE FROM contentrepresentations WHERE segment_id = ?", [lines[2].id])  # the Stop came before line 3

    seen = _kraken_reads(monkeypatch, ["y lo firmo"])
    await _transcribe(page, kraken_model="kraken-mccatmus")
    assert [ln["id"] for ln in seen["lines"]] == [lines[2].id], "only the unread line is read"
    from fichero_server.models import Artifact

    newest = sorted((a for a in page["db"].query(Artifact, document_id=page["doc"].id, artifact_type="transcription")
                     if a.model == "kraken-mccatmus"), key=lambda a: a.created_at)[-1]
    assert (newest.content or "").splitlines() == ["el dicho escrivano", "vezino de la ciudad", "y lo firmo"], (
        "the resumed read's page artifact holds the whole page, not only the lines read this time")

    found = working_lines(page["db"], page["doc"].id)
    assert len(unread_by(page["db"], found, "another-reader").lines) == 3, "a reading by one reader is not another's"

    seen = _kraken_reads(monkeypatch, ["a", "b", "c"])
    await _transcribe(page, kraken_model="kraken-mccatmus", read_all_lines=True)
    assert len(seen["lines"]) == 3, "a redo reads every line again"
