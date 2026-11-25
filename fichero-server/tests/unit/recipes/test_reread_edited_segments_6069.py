"""An edited segment is read again by itself (`segment-actions.automatic-rerun-after-an-edit`, #6069).

WHY: a person moves, resizes or redraws a line; the words it carries were read from the old shape. The step that
read it runs again on that line alone with the same local model; a paid cloud model is never run unasked, and the
line is marked as out of date instead.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import json

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _save,
    engine,
    pages,
)
from tests.unit.recipes.test_run_step_on_segments_6069 import _readings, _three_lines
from tests.unit.recipes.test_step_rerun_on_folder import STEPS

URL = "/api/recipes/project/reread-edited"


def _read_once(client, line, tmp_path):
    _save(client, _recipe(tmp_path, *STEPS))
    r = client.post("/api/recipes/project/start", json={"steps": ["read"], "segments": [line.id]})
    assert r.status_code == 200, r.text
    assert _finished(client, r.json()["started"]["job_id"])["state"] == "done"


def _make_reading_by(db, line, provider_model):
    """A machine's reading on the line, as a `transcribe` step with this model leaves it."""
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.knowledge import ProvenanceKind

    db.save(ContentRepresentation(document_id=line.document_id, segment_id=line.id, kind="transcription", content="old words",
                                  source_anchor=line.anchor, provenance_kind=ProvenanceKind.workflow,
                                  producer_tool="transcribe", producer_model=provider_model))


def test_an_edited_line_is_read_again_alone_with_its_local_model(client, db, pages, tmp_path, engine):
    first, second, _ = _three_lines(db, pages)
    _read_once(client, first, tmp_path)
    before = len(_readings(client, first.id))
    engine.read.clear()

    r = client.post(URL, json={"segment_ids": [first.id]})

    assert r.status_code == 200, r.text
    [started] = r.json()["started"]
    assert started["segment_id"] == first.id
    assert _finished(client, started["job_id"])["state"] == "done"
    assert len(_readings(client, first.id)) == before + 1, "the line was not read again beside its first reading"
    assert len(engine.read) == 1, "only the edited line is read"
    assert len({i["producer_model"] for i in _readings(client, first.id)}) == 1, "the second reading came from another model"
    assert _readings(client, second.id) == []


def test_the_run_in_activity_names_the_segment(client, db, pages, tmp_path, engine):
    line, _, _ = _three_lines(db, pages)
    _read_once(client, line, tmp_path)

    [started] = client.post(URL, json={"segment_ids": [line.id]}).json()["started"]
    _finished(client, started["job_id"])

    from fichero_server.execution import jobs
    from fichero_server.recipes import runner

    name, _pages = runner.name_and_pages(db, started["job_id"])
    detail = json.loads(jobs.read_job(db, started["job_id"])["detail"])
    assert detail["reread_of"] == line.id
    assert name.startswith("Read again"), name
    assert name == f"Read again: line on {pages[0].name}", name


def test_a_line_read_by_a_cloud_model_is_never_read_again_unasked(client, db, pages, tmp_path, engine):
    line, _, _ = _three_lines(db, pages)
    _save(client, _recipe(tmp_path, *STEPS))
    _make_reading_by(db, line, "openai/gpt-5")
    engine.read.clear()

    r = client.post(URL, json={"segment_ids": [line.id]})

    assert r.status_code == 200, r.text
    assert r.json()["started"] == []
    assert [s["segment_id"] for s in r.json()["stale"]] == [line.id], "the line is not marked out of date"
    assert engine.read == [], "a cloud model was called"


def test_a_line_nothing_read_is_left_alone(client, db, pages, tmp_path, engine):
    line, _, _ = _three_lines(db, pages)
    _save(client, _recipe(tmp_path, *STEPS))

    r = client.post(URL, json={"segment_ids": [line.id]})

    assert r.status_code == 200, r.text
    assert r.json() == {"started": [], "stale": [], "skipped": [{"segment_id": line.id, "why": "no reading of it came from a step"}]}


def test_a_second_edit_while_the_first_re_read_waits_does_not_queue_another(client, db, pages, tmp_path, engine):
    line, _, _ = _three_lines(db, pages)
    _read_once(client, line, tmp_path)
    from fichero_server.execution import jobs

    jobs.set_paused(True)
    first = client.post(URL, json={"segment_ids": [line.id]}).json()
    second = client.post(URL, json={"segment_ids": [line.id]}).json()

    assert len(first["started"]) == 1
    assert second["started"] == [] and second["skipped"][0]["why"].startswith("already being read again")
