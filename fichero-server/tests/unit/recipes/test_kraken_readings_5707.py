"""A Kraken reading of a page's lines keeps its reader's certainty, is written once, and the newest is what the line
shows (#5707), tested to the spec: `source.onboard.auto.blank-pages-not-read` (#5694's bar) and
`source.model.one-line-pass` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the operator's real run (integration 88b81f01e): Find Regions kept Kraken's lines, Read read onto them, and every
reading was stored with `machine_confidence` null (so #5694's bar never fired: 1,085 "people" from noise); one
reading was stored twice, 40 ms apart; and after a re-read the line still showed the old reading. On the real
scheduler, Kraken stubbed at its runtime (the segmenter and the line reader).
"""

from __future__ import annotations

import time

from fichero_server.llm import kraken_runtime
from fichero_server.models import ContentRepresentation, DocType, Document, FileType
from tests.unit.mcp.test_onboarding_journey_through_mcp import _call, agent  # noqa: F401  (fixture)
from tests.unit.mcp.test_reading_journey_through_mcp import assert_no_download
from tests.unit.mcp.test_reading_journey_through_mcp import engine as _engine  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import _png
from tests.unit.recipes.test_regions_one_pass_5689 import PAYLOAD

RECIPE = {"fichero_recipe": 1, "id": "t/kraken-reads", "version": "0.1.0", "title": "Kraken reads", "steps": [
    {"id": "regions", "job": "find-regions", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
]}


def _finish(agent, run_id):  # noqa: F811
    deadline, status = time.monotonic() + 120, {}
    while time.monotonic() < deadline:
        status = _call(agent, "fichero_recipes_run_status", {"job_id": run_id})
        if status["state"] in ("done", "failed", "cancelled"):
            return status
        time.sleep(0.3)
    return status


def test_a_kraken_reading_keeps_its_certainty_is_written_once_and_the_newest_shows(  # noqa: F811
        agent, client, db, tmp_path, test_package, _engine, monkeypatch):
    """source.read.kraken-confidence-kept: each line's certainty stays on its reading, a reading is written once."""
    from fichero_server.api.routes.document.segment_readings import document_text
    from fichero_server.workflows.default_workflows import seed_default_workflows

    said = {"text": "Yten dixo el testigo", "sure": 0.31}

    def read_given_lines(image_path, model_path, lines, **kw):
        return [kraken_runtime.ReadLine(said["text"], confidence=said["sure"]) for _ in lines]

    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: PAYLOAD)
    monkeypatch.setattr(kraken_runtime, "read_given_lines", read_given_lines)
    seed_default_workflows(db)
    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    page = Document(name="p0.png", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id,
                    path=str(_png(tmp_path / "p0.png")))
    db.save(page)
    _call(agent, "fichero_use_library", {"path": str(test_package)})
    _call(agent, "fichero_recipes_save_project_setup",
          {"answers": {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"]}, "recipe": RECIPE})
    status = _finish(agent, _call(agent, "fichero_recipes_start_project", {})["started"]["job_id"])
    assert status["state"] == "done", status

    readings = [r for r in db.query(ContentRepresentation, document_id=page.id) if r.segment_id]
    assert readings, "Read wrote its readings onto the lines Find Regions kept"
    per_line: dict[str, int] = {}
    for r in readings:
        per_line[r.segment_id] = per_line.get(r.segment_id, 0) + 1
    assert set(per_line.values()) == {1}, f"each line read once is one reading: {per_line}"
    assert {r.machine_confidence for r in readings} == {0.31}, "the reader's certainty is kept"

    # Read again, with a different reading: the line shows the newest.
    said.update(text="Item dijo el testigo", sure=0.88)
    again = _call(agent, "fichero_recipes_start_project", {"redo": ["read"]})["started"]["job_id"]
    assert _finish(agent, again)["state"] == "done"
    assert_no_download(db)
    assert "Item dijo el testigo" in document_text(db, page.id).text
    assert "Yten dixo" not in document_text(db, page.id).text
    # As an agent lists the page's lines (the operator's `segments list-document`): the newest too.
    listed = client.get(f"/api/segments/document/{page.id}").json()
    lines = [s for s in listed["segments"] if s.get("kind") == "line"]
    assert lines and all(s.get("text") == "Item dijo el testigo" for s in lines), [s.get("text") for s in lines]


def test_the_same_reading_written_twice_is_kept_once(db, tmp_path):
    """The 00:40 reading stored twice, 40 ms apart: a write of a reading the line already has from the same result
    is no second reading."""
    from fichero_server.llm.working_lines import write_readings
    from fichero_server.models import Segment
    from tests.unit.training.test_kraken_training_set import _page

    folder = Document(name="F", doc_type=DocType.folder)
    db.save(folder)
    page = _page(db, tmp_path, "1_Hoja", folder)
    line = next(s for s in db.query(Segment, document_id=page.id) if s.kind == "line" and not s.deleted_at)
    before = len(db.query(ContentRepresentation, document_id=page.id))
    for _ in range(2):
        write_readings(db, document_id=page.id, readings=[(line.id, "una línea", 0.5)], artifact_id="art-1",
                       run_id="read-1")
    assert len(db.query(ContentRepresentation, document_id=page.id)) == before + 1


def test_after_a_re_read_of_kraken_s_own_pass_the_line_shows_the_newest_reading(  # noqa: F811
        agent, client, db, tmp_path, test_package, _engine, monkeypatch):
    """The operator's page 42 (`MCP Night 1`, line e7805818): Kraken found and read the lines in one go (its own
    pass, 00:40), a redo of Read wrote a newer reading onto those lines (05:53) and it counted, but the page's line
    list still served the pass's 00:40 words."""
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    page = Document(name="p0.png", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id,
                    path=str(_png(tmp_path / "p0.png")))
    db.save(page)
    recipe = {**RECIPE, "steps": RECIPE["steps"][1:]}  # lines and read: Kraken's own pass first
    _call(agent, "fichero_use_library", {"path": str(test_package)})
    _call(agent, "fichero_recipes_save_project_setup",
          {"answers": {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"]}, "recipe": recipe})
    assert _finish(agent, _call(agent, "fichero_recipes_start_project", {})["started"]["job_id"])["state"] == "done"

    monkeypatch.setattr(kraken_runtime, "read_given_lines", lambda image_path, model_path, lines, **kw: [
        kraken_runtime.ReadLine("Item dijo el testigo", confidence=0.9) for _ in lines])
    again = _call(agent, "fichero_recipes_start_project", {"redo": ["read"]})["started"]["job_id"]
    assert _finish(agent, again)["state"] == "done"
    assert_no_download(db)

    lines = [s for s in client.get(f"/api/segments/document/{page.id}").json()["segments"] if s["kind"] == "line"]
    assert lines and {s["text"] for s in lines} == {"Item dijo el testigo"}, [s["text"] for s in lines]
    # The line's readings: the pass's own words (its result's provisional reading, and the stored reading made of it,
    # side by side by design) and the newer one, which counts.
    answer = client.get(f"/api/segments/{lines[0]['id']}/readings").json()
    counting = answer["counting"]["transcription"]["representation_id"]
    assert next(r["content"] for r in answer["items"] if r["id"] == counting) == "Item dijo el testigo"
