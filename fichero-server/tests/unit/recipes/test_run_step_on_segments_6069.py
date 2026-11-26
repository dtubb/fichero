"""Run one recipe step on the selected segments (`segment-actions.run-step-on-selection`, #6069).

WHY: the person selects two lines on a page and runs Read on just them. The context menu makes one call,
`POST /api/recipes/project/start` with `steps` and `segments`; only those lines are read, each run is a new
reading on the line (never over the person's), and a step that works on pages is refused in words.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _save,
    engine,
    pages,
)
from tests.unit.recipes.test_step_rerun_on_folder import STEPS

CHECK = {"id": "check", "job": "check", "settings": {"layer": "claims"},
         "model": {"cloud": "openai", "model": "gpt-5"}, "runs_on": "cloud:openai"}


def _line(db, doc, rect):
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.knowledge import ProvenanceKind
    from fichero_server.models.segments import Segment, bbox_and_tile_from_anchor

    anchor = SourceAnchor(document_id=doc.id, rect=list(rect))
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    row = Segment(document_id=doc.id, pass_id=f"pass-{doc.id}", kind="line", anchor=anchor, bbox_x=x, bbox_y=y,
                  bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{doc.id}:line", provenance_kind=ProvenanceKind.workflow)
    db.save(row)
    return row


def _readings(client, segment_id):
    r = client.get(f"/api/segments/{segment_id}/readings", params={"kind": "transcription"})
    assert r.status_code == 200, r.text
    return [i for i in r.json()["items"] if not i["provisional"]]


def _three_lines(db, pages):
    return [_line(db, pages[0], (0.0, y, 1.0, 0.2)) for y in (0.05, 0.4, 0.75)]


def test_read_runs_on_two_selected_lines_and_not_on_the_third(client, db, pages, tmp_path, engine):
    first, second, third = _three_lines(db, pages)
    _save(client, _recipe(tmp_path, *STEPS))

    r = client.post("/api/recipes/project/start", json={"steps": ["read"], "segments": [first.id, second.id]})

    assert r.status_code == 200, r.text
    run = _finished(client, r.json()["started"]["job_id"])
    assert run["state"] == "done", run
    assert [s["steps"] for s in run["steps"]] == [["read"]], "the run is that one step"
    assert len(_readings(client, first.id)) == 1 and len(_readings(client, second.id)) == 1
    assert _readings(client, third.id) == [], "the line that was not selected was read"
    assert client.get(f"/api/documents/{pages[0].id}").json().get("page_content") in (None, ""), "the page's text was written"
    assert len(engine.read) == 2, "each selected line is read from its own picture, and nothing else is"


def test_each_run_is_a_new_reading_and_the_earlier_one_stays(client, db, pages, tmp_path, engine):
    line, _, _ = _three_lines(db, pages)
    _save(client, _recipe(tmp_path, *STEPS))
    for _ in range(2):
        r = client.post("/api/recipes/project/start", json={"steps": ["read"], "segments": [line.id]})
        assert r.status_code == 200, r.text
        assert _finished(client, r.json()["started"]["job_id"])["state"] == "done"

    assert len(_readings(client, line.id)) == 2, "the second run overwrote the first reading"


def test_a_step_that_works_on_pages_is_refused_on_a_line_in_words(client, db, pages, tmp_path):
    line, _, _ = _three_lines(db, pages)
    _save(client, _recipe(tmp_path, *STEPS, CHECK))

    r = client.post("/api/recipes/project/start", json={"steps": ["check"], "segments": [line.id]})

    assert r.status_code == 422 and "runs on pages, not on a line" in r.text, r.text


def test_a_segment_that_is_not_in_the_project_is_refused(client, db, pages, tmp_path):
    _save(client, _recipe(tmp_path, *STEPS))
    r = client.post("/api/recipes/project/start", json={"steps": ["read"], "segments": ["no-such-segment"]})
    assert r.status_code == 422 and "no-such-segment" in r.text, r.text


def test_segments_and_a_folder_are_not_both_taken(client, db, pages, tmp_path):
    line, _, _ = _three_lines(db, pages)
    _save(client, _recipe(tmp_path, *STEPS))
    r = client.post("/api/recipes/project/start", json={"steps": ["read"], "segments": [line.id], "documents": [pages[0].id]})
    assert r.status_code == 422, r.text
