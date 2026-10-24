"""The local stages Find Lines, Leave Out and Names can be stopped mid-stage and started again: Start again does not
redo a page it already did, and the run ends done (owner release condition 2026-10-24; `source.recipe.done-is-not-redone`,
#5390; `activity.recipe-run.stop-reaches-its-step`). Modelled on test_start_stop_restart_resumes.

Each case holds its stage on its per-page call (a Gate), presses Stop, lets go, starts again and counts the stage's page
calls over both runs: every page exactly once.
  * Find Lines: the segmenter, one call a page; a page whose lines were found is not found again.
  * Leave Out: the rules, one call a page; a page it has been over is not gone over again (it leaves no line behind on a
    page with nothing to leave out, so the page itself records that it ran).
  * Names: the NER provider, one call a page; a page it has been over is not gone over again even when it found no name.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

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
from tests.unit.recipes.test_stop_reaches_inline_steps_5609 import LINES, READ, Gate, _save, _stop

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


def _stage(monkeypatch, which):
    """(the recipe's steps, the Gate on the stage's per-page call, the list of that call's pages)."""
    calls: list[str] = []
    if which == "find-lines":
        def segment(image_path, **kwargs):
            calls.append(str(image_path))
            return SEGMENTATION

        monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
        monkeypatch.setattr(kraken_runtime, "segment_lines", segment)
        return [LINES], Gate(monkeypatch, kraken_runtime, "segment_lines"), calls
    if which == "leave-out":
        monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
        monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **kwargs: SEGMENTATION)
        real = leave_out.decide

        def counted(lines, **kwargs):
            calls.append(lines[0]["id"] if lines else "-")
            return real(lines, **kwargs)

        monkeypatch.setattr(leave_out, "decide", counted)
        return [LINES, LEAVE_OUT], Gate(monkeypatch, leave_out, "decide"), calls
    import types

    from fichero_server.workflows.ner import providers

    module = types.SimpleNamespace(held_call=lambda: calls.append("page"))
    gate = Gate(monkeypatch, module, "held_call")
    monkeypatch.setattr(providers, "get_ner_provider", lambda name, model=None: _NoNames(module))
    return [LINES, READ, NAMES], gate, calls


LEAVE_OUT_STATUS = pytest.mark.xfail(strict=True, reason="a run with Leave Out cannot be read back: run_step stores its account at "
                                     "step['left_out'], the run status's list of pages (ValidationError); r1's blocker fix is coming")


@pytest.mark.parametrize("stage", ["find-lines", pytest.param("leave-out", marks=LEAVE_OUT_STATUS), "names"])
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
    assert before >= 1
    stopped_mid_stage = before < 3  # the two pages and the material's: Stop reached the stage before its last page
    # Find Lines runs its pages side by side, so every page can have started before Stop lands: only Leave Out, which
    # goes page by page and checks Stop between them, must stop short.

    run = _finished(client, _start(client))

    assert run["state"] == "done", run
    from fichero_server.models import Document, FileType

    images = [d for d in db.query(Document) if d.file_type == FileType.image]  # the two pages and the material's
    if stage == "leave-out":
        assert stopped_mid_stage, f"Stop did not reach Leave Out: {before} of {len(images)} pages were done before it ended"
    assert len(calls) == len(images), f"{stage}: the stage's page calls were {calls} for {len(images)} pages"
    if stage == "find-lines":
        assert len(calls) == len(set(calls)), f"a page's lines were found twice: {calls}"


@pytest.mark.xfail(strict=True, reason="Stop does not reach inside the Names tool: extract_entities_only runs every page of "
                   "its batch before the step ends (found 2026-10-24; the tool is r1's, the fix is to check the run's Stop "
                   "between pages). Restart still does not redo a page once the step finished.")
def test_names_stop_reaches_inside_the_stage(client, db, pages, tmp_path, engine, monkeypatch, with_material):
    steps, gate, calls = _stage(monkeypatch, "names")
    try:
        _save(client, _recipe(tmp_path, *steps))
        first = _start(client)
        assert gate.entered.wait(60), _run_status(client, first)
        assert _stop(client, first) == "stopping"
        gate.release.set()
        _finished(client, first)
    finally:
        gate.release.set()
    assert len(calls) < 3, f"all {len(calls)} pages were gone over after Stop"


@LEAVE_OUT_STATUS
def test_a_new_find_lines_pass_is_judged_again_by_leave_out_and_no_other_page_is(
        client, db, pages, tmp_path, engine, monkeypatch, with_material):
    """Leave Out's done is tied to the pass it judged: a page whose lines were found again is judged again, the pages
    whose lines did not change are not."""
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.anchors import SourceAnchor

    steps, _gate, calls = _stage(monkeypatch, "leave-out")
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
