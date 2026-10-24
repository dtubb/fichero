"""The local stages Find Lines, Leave Out and Names can be stopped mid-stage and started again: Start again does not
redo a page it already did, and the run ends done (owner release condition 2026-10-24; `source.recipe.done-is-not-redone`,
#5390; `activity.recipe-run.stop-reaches-its-step`). Modelled on test_start_stop_restart_resumes.

Each case runs the stage's per-page call through a seam (_Hold, no sleeps) that lets page 1 finish and holds the next page
on an event until Stop has been sent, then lets go, starts again and counts the stage's page calls over both runs: every
page exactly once, page 1 not redone, the rest run. Names, which checks Stop between pages inside its tool, also stops
before its last page.
  * Find Lines: the segmenter, one call a page; a page whose lines were found is not found again.
  * Leave Out: the rules, one call a page; a page it has been over is not gone over again (the run's detail records Leave
    Out's account, not the page).
  * Names: the NER provider, one call a page; a page it has been over is not gone over again even when it found no name.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import threading

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.recipes import leave_out
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _run_status,
    _start,
    engine,
    pages,
)
from tests.unit.recipes.test_stop_reaches_inline_steps_5609 import LINES, READ, _save, _stop

LEAVE_OUT = {"id": "leaveout", "job": "leave-out"}
NAMES = {"id": "names", "job": "find-names-tag-words", "model": {"spacy": "es_core_news_sm", "version": "bundled"}}
#: Six lines, so Leave Out has a median to judge by; none of them is left out.
SEGMENTATION = {"width": 1000, "height": 2000, "regions": [], "lines": [
    {"polygon": [[100, 100 + 200 * i], [900, 100 + 200 * i], [900, 160 + 200 * i], [100, 160 + 200 * i]],
     "baseline": [[100, 150 + 200 * i], [900, 150 + 200 * i]]} for i in range(6)]}


class _NoNames:
    """A NER provider that finds nothing: a page it has been over has no entity to show for it."""

    def __init__(self, counted):
        self.counted = counted

    async def extract(self, text, language=None, **kwargs):
        self.counted.held_call()  # looked up at call time: the Gate has replaced it
        return []


class _Hold:
    """The test seam: a stage's per-page call that lets page 1 finish and holds every later call on an event until the
    test has sent Stop. No sleeps: the run is stopped mid-stage with page 1 done and the rest not."""

    def __init__(self):
        self.entered = threading.Event()  # a page after the first has been asked for, and is held
        self.release = threading.Event()
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def call(self, page):
        with self._lock:
            self.calls.append(page)
            first = len(self.calls) == 1
        if first:
            return
        self.entered.set()
        assert self.release.wait(30), "the test never let the step go"


def _stage(monkeypatch, which):
    """(the recipe's steps, the hold on the stage's per-page call, the list of that call's pages)."""
    hold = _Hold()
    if which == "find-lines":
        def segment(image_path, **kwargs):
            hold.call(str(image_path))
            return SEGMENTATION

        monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
        monkeypatch.setattr(kraken_runtime, "segment_lines", segment)
        return [LINES], hold, hold.calls
    if which == "leave-out":
        monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
        monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **kwargs: SEGMENTATION)
        real = leave_out.decide

        def counted(lines, **kwargs):
            hold.call(lines[0]["id"] if lines else "-")
            return real(lines, **kwargs)

        monkeypatch.setattr(leave_out, "decide", counted)
        return [LINES, LEAVE_OUT], hold, hold.calls
    import types

    from fichero_server.workflows.ner import providers

    module = types.SimpleNamespace(held_call=lambda: hold.call("page"))
    monkeypatch.setattr(providers, "get_ner_provider", lambda name, model=None: _NoNames(module))
    return [LINES, READ, NAMES], hold, hold.calls


@pytest.mark.parametrize("stage", ["find-lines", "leave-out", "names"])
def test_a_local_stage_stopped_mid_stage_and_started_again_does_not_redo_a_page(
        stage, client, db, pages, tmp_path, engine, monkeypatch, with_material):
    steps, gate, calls = _stage(monkeypatch, stage)
    try:
        _save(client, _recipe(tmp_path, *steps))
        first = _start(client)
        assert gate.entered.wait(60), _run_status(client, first)
        assert _stop(client, first) == "stopping"
        gate.release.set()
        assert _finished(client, first)["state"] == "cancelled"
    finally:
        gate.release.set()
    before = len(calls)
    if stage == "names":
        assert before < 3, f"Stop did not reach inside Names: all {before} pages were gone over before it ended"
    assert before >= 2  # page 1 done, a later page asked for and held when Stop was sent

    run = _finished(client, _start(client))

    assert run["state"] == "done", run
    from fichero_server.models import Document, FileType

    images = [d for d in db.query(Document) if d.file_type == FileType.image]  # the two pages and the material's
    assert len(calls) == len(images), f"{stage}: the stage's page calls were {calls} for {len(images)} pages"
    if stage != "names":
        assert len(calls) == len(set(calls)), f"{stage}: a page was done twice: {calls}"
    # Names goes over its pages side by side and records no page id at its seam: its count is the check.


def test_a_new_find_lines_pass_is_judged_again_by_leave_out_and_no_other_page_is(
        client, db, pages, tmp_path, engine, monkeypatch, with_material):
    """Leave Out's done is tied to the pass it judged: a page whose lines were found again is judged again, the pages
    whose lines did not change are not."""
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.anchors import SourceAnchor

    steps, hold, calls = _stage(monkeypatch, "leave-out")
    hold.release.set()  # no Stop here: nothing is held
    _save(client, _recipe(tmp_path, *steps))
    assert _finished(client, _start(client))["state"] == "done"
    first = len(calls)
    assert first >= 2

    page = pages[0]
    machine = ActionContext(actor="kraken", run_id="find-again", library_path=None, is_bootstrap=True)
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": page.id, "name": "kraken"}, machine).result["id"]
    for i in range(6):
        registry.invoke(db, "segment.create", {
            "document_id": page.id, "pass_id": pass_id, "kind": "line",
            "anchor": SourceAnchor(document_id=page.id, rect=[0.1, 0.1 + 0.12 * i, 0.7, 0.05]).model_dump(mode="json"),
        }, machine)

    assert _finished(client, _start(client))["state"] == "done"
    assert len(calls) == first + 1, f"Leave Out judged {len(calls) - first} pages after one page's lines were found again"
